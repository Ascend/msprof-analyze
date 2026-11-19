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

"""Standalone structured v3 must not alter native-v2 or compatible-v1 imports."""

import json
import pickle
import sqlite3
from contextlib import closing
from pathlib import Path

import pytest

from pt_snap_cli.core.common.errors import ImportExecutionError
from pt_snap_cli.core.common.models import ImportOptions
from pt_snap_cli.core.dataset.native_dataset_contract import NATIVE_FORMAT
from pt_snap_cli.core.importing import import_metadata
from pt_snap_cli.core.importing.import_service import ImportService
from pt_snap_cli.snapshot.tools.adaptors import snapshot2db
from test.snapshot.test_sharded_replay import lifecycle_data, write_source

FRAME_TABLES = {"frame", "callstack_frame", "callstack_frame_manifest"}


@pytest.fixture(autouse=True)
def isolate(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.delenv("PT_SNAP_DB_PATH", raising=False)


def source(tmp_path):
    data = lifecycle_data()
    events = [event for event in data["device_traces"][0] if event["action"] != "oom"]
    data["device_traces"][0] = events
    events[0]["frames"] = [{"filename": "x", "line": 1, "name": "f\ny:2 g"}]
    events[1]["frames"] = [
        {"filename": "y", "line": 2, "name": "g"},
        {"filename": "x", "line": 1, "name": "f"},
    ]
    events[2]["frames"] = []
    return write_source(tmp_path, data)


def tables(conn):
    return {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}


@pytest.mark.parametrize("fmt,version", [("single-db", 3), (NATIVE_FORMAT, 2), ("msinsight", 1)])
def test_import_formats_keep_their_own_metadata_schema_and_cache(tmp_path, monkeypatch, fmt, version):
    options = ImportOptions(
        source(tmp_path),
        tmp_path / fmt,
        set_focus=False,
        format=fmt,
        events_per_slice=None if fmt == "single-db" else 100,
    )
    service = ImportService()
    result = service.import_snapshot(options)
    assert result.metadata.import_format_version == version
    members = [result.db_path] if version == 3 else list(result.db_path.rglob("*.db"))
    assert members
    for member in members:
        with closing(sqlite3.connect(member)) as conn:
            assert conn.execute("SELECT import_format_version FROM pt_snap_metadata").fetchone() == (version,)
            assert tables(conn) & FRAME_TABLES == (FRAME_TABLES if version == 3 else set())
            if version == 3:
                rows = conn.execute(
                    "SELECT t.id, m.frameCount FROM trace_entry_0 t "
                    "JOIN callstack_frame_manifest m ON m.callstackId=t.callstackId "
                    "WHERE t.id IN (0,1,2) ORDER BY t.id"
                ).fetchall()
                assert rows == [(0, 1), (1, 2), (2, 0)]
                counts = conn.execute(
                    "SELECT (SELECT COUNT(*) FROM callstack), (SELECT COUNT(*) FROM callstack_frame_manifest)"
                ).fetchone()
                assert counts[0] == counts[1]
            if version in (2, 3):
                rows = conn.execute(
                    "SELECT t.callstackId, c.callstack FROM trace_entry_0 t "
                    "JOIN callstack c ON c.id=t.callstackId WHERE t.id IN (0,1) ORDER BY t.id"
                ).fetchall()
                assert rows[0][1] == rows[1][1]
                assert (rows[0][0] == rows[1][0]) is (version == 2)
    if version == 2:
        manifest = json.loads((result.db_path / "manifest.json").read_text())
        assert manifest["identity"]["importFormatVersion"] == 2
        assert manifest["metadata"]["import_format_version"] == 2

    def fail(*args, **kwargs):
        pytest.fail("reusable cache loaded or replayed source")

    monkeypatch.setattr(service._backend, "dump_to_db", fail)
    monkeypatch.setattr(service._dataset_backend.replay, "stage", fail)
    monkeypatch.setattr(service._msinsight_backend.replay, "stage", fail)
    if version != 3:
        monkeypatch.setattr(import_metadata, "IMPORT_FORMAT_VERSION", 99)
    cached = service.import_snapshot(options)
    assert cached.reused and cached.metadata == result.metadata


def test_standalone_v2_cache_is_rebuilt_to_structured_v3(tmp_path):
    options = ImportOptions(source(tmp_path), tmp_path / "standalone", set_focus=False)
    service = ImportService()
    first = service.import_snapshot(options)
    with closing(sqlite3.connect(first.db_path)) as conn, conn:
        conn.execute("UPDATE pt_snap_metadata SET import_format_version=2")
        for table in FRAME_TABLES:
            conn.execute(f"DROP TABLE {table}")
    rebuilt = service.import_snapshot(options)
    assert not rebuilt.reused
    assert rebuilt.cache_miss_reason == "import_format_changed"
    assert rebuilt.metadata.import_format_version == 3
    with closing(sqlite3.connect(rebuilt.db_path)) as conn:
        assert FRAME_TABLES <= tables(conn)
    assert service.import_snapshot(options).reused


@pytest.mark.parametrize("line", [True, 1.0, "1"])
def test_invalid_structured_frame_rejects_standalone_but_preserves_native(tmp_path, line):
    data = lifecycle_data()
    data["device_traces"][0][0]["frames"][0]["line"] = line
    path = write_source(tmp_path, data)
    service = ImportService()
    native = service.import_snapshot(ImportOptions(path, tmp_path / "native", set_focus=False, events_per_slice=100))
    assert native.metadata.import_format_version == 2
    options = ImportOptions(path, tmp_path / "standalone", set_focus=False)
    with pytest.raises(ImportExecutionError, match="Structured frames require"):
        service.import_snapshot(options)
    assert not service._backend.target_db_path(path, options.output_dir).exists()


def test_native_handler_default_never_creates_standalone_frame_tables(tmp_path):
    handler = snapshot2db.SnapshotDbHandler(str(tmp_path / "native.db"), [0])
    try:
        assert not (tables(handler.db.conn) & FRAME_TABLES)
    finally:
        handler.close()


def test_malformed_structured_reimport_preserves_existing_database(tmp_path):
    options = ImportOptions(source(tmp_path), tmp_path / "standalone", set_focus=False)
    service = ImportService()
    first = service.import_snapshot(options)
    before = first.db_path.read_bytes()
    data = lifecycle_data()
    data["device_traces"][0][0]["frames"][0]["line"] = True
    options.snapshot_file.write_bytes(pickle.dumps(data))
    with pytest.raises(ImportExecutionError, match="Structured frames require"):
        service.import_snapshot(options)
    assert first.db_path.read_bytes() == before
    assert list(first.db_path.parent.iterdir()) == [first.db_path]
