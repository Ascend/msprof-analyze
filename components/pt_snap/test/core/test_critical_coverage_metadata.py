# -------------------------------------------------------------------------
# This file is part of the MindStudio project.
# Copyright (c) 2026 Huawei Technologies Co.,Ltd.
#
# MindStudio is licensed under Mulan PSL v2.
# You can use this software according to the terms and conditions of the Mulan PSL v2.
# You may obtain a copy of Mulan PSL v2 at:
#
#          http://license.coscl.org.cn/MulanPSL2
#
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND,
# EITHER EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT,
# MERCHANTABILITY OR FIT FOR A PARTICULAR PURPOSE.
# See the Mulan PSL v2 for more details.
# -------------------------------------------------------------------------

"""Malformed metadata must not become a cache hit or replace valid metadata."""

import sqlite3
from contextlib import closing, contextmanager
from dataclasses import asdict, replace
from types import SimpleNamespace

import pytest

import pt_snap_cli.core.importing.import_metadata as metadata_module
from pt_snap_cli.core.common.errors import (
    DatabaseMissingError,
    DatabaseSchemaError,
    ImportMetadataError,
)
from pt_snap_cli.core.common.models import ImportMetadata
from pt_snap_cli.core.importing.import_metadata import ImportMetadataService
from pt_snap_cli.core.importing.import_metadata_contract import (
    metadata_from_mapping,
    required_int,
    required_str,
    validate_import_metadata,
)


def metadata(**changes):
    original = ImportMetadata(
        metadata_module.METADATA_SCHEMA_VERSION,
        metadata_module.IMPORT_FORMAT_VERSION,
        "a" * 64,
        12,
        "snapshot.pkl",
        None,
        "pt-snap-cli",
        "1",
        "2026-11-01T00:00:00+00:00",
    )
    return replace(original, **changes)


def create_database(path):
    with closing(sqlite3.connect(path)) as conn, conn:
        conn.execute('CREATE TABLE dictionary ("table" TEXT, "column" TEXT, "key" TEXT, "value" TEXT)')
        conn.execute("CREATE TABLE trace_entry_0 (id INTEGER PRIMARY KEY)")
    return path


@pytest.mark.parametrize("value", [True, False, 1.0, "1", None])
def test_metadata_integer_contract_rejects_coercion(value):
    with pytest.raises(TypeError, match="integer"):
        required_int(value)
    assert required_int(0) == 0


@pytest.mark.parametrize("value", ["", 0, None, b"name"])
def test_metadata_string_contract_requires_nonempty_text(value):
    with pytest.raises(TypeError, match="non-empty"):
        required_str(value)
    assert required_str("snapshot.pkl") == "snapshot.pkl"


@pytest.mark.parametrize(
    "changes",
    [
        {"metadata_schema_version": 0},
        {"import_format_version": 0},
        {"source_sha256": "A" * 64},
        {"source_sha256": "a" * 63},
        {"source_size": -1},
        {"source_name": ""},
        {"requested_device": -1},
        {"importer_name": ""},
        {"importer_version": ""},
        {"completed_at": "2026-11-01T00:00:00"},
        {"completed_at": "2026-11-01T01:00:00+01:00"},
        {"completed_at": "invalid"},
    ],
)
def test_invalid_values_are_rejected_before_metadata_publication(tmp_path, changes):
    path = create_database(tmp_path / "snapshot.db")
    service = ImportMetadataService()
    original = metadata()
    service.write(path, original)
    before = path.read_bytes()
    invalid = metadata(**changes)

    with pytest.raises(ValueError):
        validate_import_metadata(invalid)
    with pytest.raises(ImportMetadataError, match="invalid import metadata"):
        service.write(path, invalid)

    assert path.read_bytes() == before
    assert service.inspect(path).metadata == original


@pytest.mark.parametrize("device", [None, 0, 7])
def test_mapping_preserves_exact_device_and_utc_metadata(device):
    original = metadata(requested_device=device)
    assert metadata_from_mapping(asdict(original)) == original


@pytest.mark.parametrize("field", ["metadata_schema_version", "source_size", "requested_device"])
def test_mapping_rejects_boolean_integer_fields(field):
    row = asdict(metadata())
    row[field] = True
    with pytest.raises(TypeError, match="integer"):
        metadata_from_mapping(row)


@pytest.mark.parametrize("operation", ["hash", "stat"])
def test_source_io_errors_are_metadata_errors_without_creating_source(tmp_path, operation):
    missing = tmp_path / "missing.pkl"
    service = ImportMetadataService()
    with pytest.raises(ImportMetadataError) as caught:
        if operation == "hash":
            service.calculate_sha256(missing)
        else:
            service.build_metadata(missing, "a" * 64, None)
    assert isinstance(caught.value.__cause__, FileNotFoundError)
    assert not missing.exists()


@pytest.mark.parametrize("kind", ["missing", "wrong-schema", "not-sqlite"])
def test_invalid_databases_never_become_cache_hits(tmp_path, kind):
    path = tmp_path / "snapshot.db"
    if kind == "wrong-schema":
        with closing(sqlite3.connect(path)) as conn, conn:
            conn.execute("CREATE TABLE unrelated (value INTEGER)")
    elif kind == "not-sqlite":
        path.write_bytes(b"not sqlite")
    original = path.read_bytes() if path.exists() else None
    service = ImportMetadataService()
    error = DatabaseMissingError if kind == "missing" else DatabaseSchemaError
    with pytest.raises(error):
        service.inspect(path)
    decision = service.evaluate_cache(path, "a" * 64, None)
    assert decision.reused is False
    assert decision.reason == ("database_missing" if kind == "missing" else "database_invalid")
    assert (path.read_bytes() if path.exists() else None) == original


def test_metadata_query_failure_is_invalid_and_closes_reader(tmp_path, monkeypatch):
    path = create_database(tmp_path / "snapshot.db")
    service = ImportMetadataService()
    service.write(path, metadata())
    before = path.read_bytes()
    closed = []

    class BrokenContext:
        @contextmanager
        def connect(self):
            try:
                yield self
            finally:
                closed.append(True)

        def execute(self, *args):
            raise sqlite3.DatabaseError("reader failure")

    monkeypatch.setattr(metadata_module, "Context", lambda path: BrokenContext())
    inspection = service.inspect(path)
    assert (inspection.status, inspection.reason, inspection.metadata) == (
        "invalid",
        "metadata_invalid",
        None,
    )
    assert closed == [True]
    assert path.read_bytes() == before


def test_metadata_write_open_failure_is_normalized_without_creating_output(tmp_path):
    path = tmp_path / "missing-parent" / "snapshot.db"
    with pytest.raises(ImportMetadataError, match="Cannot write import metadata") as caught:
        ImportMetadataService().write(path, metadata())
    assert isinstance(caught.value.__cause__, sqlite3.DatabaseError)
    assert not path.exists()
    assert not path.parent.exists()


@pytest.mark.parametrize("raw", [b"not-json", b'{"ptSnap":{}}', None])
def test_dataset_metadata_corruption_is_invalid_not_reusable(tmp_path, monkeypatch, raw):
    manifest = tmp_path / "manifest.json"
    if raw is not None:
        manifest.write_bytes(raw)
    dataset = SimpleNamespace(root=tmp_path, validation=SimpleNamespace(manifest=object()))
    monkeypatch.setattr(metadata_module.DatasetResolver, "inspect", lambda self, path: dataset)

    def invalid_owned_cache(path):
        raise ValueError("producer metadata corrupt")

    monkeypatch.setattr(metadata_module, "inspect_owned_cache", invalid_owned_cache)
    inspection = ImportMetadataService().inspect(tmp_path)
    assert (inspection.status, inspection.reason, inspection.metadata) == (
        "invalid",
        "metadata_invalid",
        None,
    )
    assert (manifest.read_bytes() if manifest.exists() else None) == raw


def test_unattested_dataset_metadata_is_explicitly_unavailable(tmp_path, monkeypatch):
    (tmp_path / "manifest.json").write_bytes(b"{}")
    dataset = SimpleNamespace(root=tmp_path, validation=SimpleNamespace(manifest=object()))
    monkeypatch.setattr(metadata_module.DatasetResolver, "inspect", lambda self, path: dataset)
    inspection = ImportMetadataService().inspect(tmp_path)
    assert (inspection.status, inspection.reason) == ("unavailable", "metadata_missing")
