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

from __future__ import annotations

import sqlite3
from contextlib import closing
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from pt_snap_cli.core.common.models import ImportMetadata
from pt_snap_cli.core.importing.import_metadata import (
    IMPORT_FORMAT_VERSION,
    METADATA_SCHEMA_VERSION,
    ImportMetadataService,
)


def _create_snapshot_db(path: Path) -> Path:
    with closing(sqlite3.connect(path)) as conn, conn:
        conn.execute("CREATE TABLE dictionary (`table` TEXT, `column` TEXT, `key` TEXT, `value` TEXT)")
        conn.execute("CREATE TABLE trace_entry_0 (id INTEGER PRIMARY KEY)")
        conn.execute("CREATE TABLE block_0 (id INTEGER PRIMARY KEY)")
    return path


def _metadata(**overrides: object) -> ImportMetadata:
    values: dict[str, object] = {
        "metadata_schema_version": METADATA_SCHEMA_VERSION,
        "import_format_version": IMPORT_FORMAT_VERSION,
        "source_sha256": "a" * 64,
        "source_size": 123,
        "source_name": "snapshot.pkl",
        "requested_device": None,
        "importer_name": "pt-snap-cli",
        "importer_version": "1.2.3",
        "completed_at": "2026-07-18T10:00:00+00:00",
    }
    values.update(overrides)
    return ImportMetadata(**values)  # type: ignore[arg-type]


def test_import_metadata_is_frozen() -> None:
    metadata = _metadata()
    with pytest.raises(FrozenInstanceError):
        metadata.source_name = "other.pkl"  # type: ignore[misc]


def test_calculate_sha256_reads_complete_file(tmp_path: Path) -> None:
    source = tmp_path / "snapshot.pkl"
    source.write_bytes(b"abc")

    assert ImportMetadataService().calculate_sha256(source) == (
        "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
    )


def test_write_and_inspect_metadata(tmp_path: Path) -> None:
    db_path = _create_snapshot_db(tmp_path / "snapshot.db")
    service = ImportMetadataService()
    metadata = _metadata()

    service.write(db_path, metadata)
    inspection = service.inspect(db_path)

    assert inspection.status == "available"
    assert inspection.reason is None
    assert inspection.metadata == metadata


def test_write_closes_database_connection(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from unittest.mock import MagicMock

    import pt_snap_cli.core.importing.import_metadata as metadata_module

    db_path = _create_snapshot_db(tmp_path / "snapshot.db")
    connection = sqlite3.connect(db_path)
    tracked_connection = MagicMock(wraps=connection)
    tracked_connection.__enter__.return_value = tracked_connection
    tracked_connection.__exit__.side_effect = connection.__exit__
    monkeypatch.setattr(metadata_module.sqlite3, "connect", lambda path: tracked_connection)

    ImportMetadataService().write(db_path, _metadata())

    tracked_connection.close.assert_called_once_with()


def test_inspect_reports_missing_metadata(tmp_path: Path) -> None:
    db_path = _create_snapshot_db(tmp_path / "legacy.db")

    inspection = ImportMetadataService().inspect(db_path)

    assert inspection.status == "unavailable"
    assert inspection.reason == "metadata_missing"


def test_inspect_reports_invalid_metadata_columns(tmp_path: Path) -> None:
    db_path = _create_snapshot_db(tmp_path / "invalid.db")
    with closing(sqlite3.connect(db_path)) as conn, conn:
        conn.execute("CREATE TABLE pt_snap_metadata (id INTEGER)")
        conn.execute("INSERT INTO pt_snap_metadata VALUES (1)")

    inspection = ImportMetadataService().inspect(db_path)

    assert inspection.status == "invalid"
    assert inspection.reason == "metadata_invalid"


def test_inspect_reports_unsupported_metadata_version(tmp_path: Path) -> None:
    db_path = _create_snapshot_db(tmp_path / "future.db")
    service = ImportMetadataService()
    service.write(db_path, _metadata())
    with closing(sqlite3.connect(db_path)) as conn, conn:
        conn.execute("UPDATE pt_snap_metadata SET metadata_schema_version = 999")

    inspection = service.inspect(db_path)

    assert inspection.status == "invalid"
    assert inspection.reason == "metadata_version_unsupported"


def test_inspect_rejects_non_utc_completed_at(tmp_path: Path) -> None:
    db_path = _create_snapshot_db(tmp_path / "non-utc.db")
    service = ImportMetadataService()
    service.write(db_path, _metadata())
    with closing(sqlite3.connect(db_path)) as conn, conn:
        conn.execute("UPDATE pt_snap_metadata SET completed_at = '2026-07-18T18:00:00+08:00'")

    inspection = service.inspect(db_path)

    assert inspection.status == "invalid"
    assert inspection.reason == "metadata_invalid"


def test_inspect_rejects_duplicate_metadata_rows(tmp_path: Path) -> None:
    db_path = _create_snapshot_db(tmp_path / "duplicate.db")
    with closing(sqlite3.connect(db_path)) as conn, conn:
        conn.execute("""
            CREATE TABLE pt_snap_metadata (
                id INTEGER,
                metadata_schema_version INTEGER,
                import_format_version INTEGER,
                source_sha256 TEXT,
                source_size INTEGER,
                source_name TEXT,
                requested_device INTEGER,
                importer_name TEXT,
                importer_version TEXT,
                completed_at TEXT
            )
        """)
        values = (
            METADATA_SCHEMA_VERSION,
            IMPORT_FORMAT_VERSION,
            "a" * 64,
            123,
            "snapshot.pkl",
            None,
            "pt-snap-cli",
            "1.2.3",
            "2026-07-18T10:00:00+00:00",
        )
        conn.execute("INSERT INTO pt_snap_metadata VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?, ?)", values)
        conn.execute("INSERT INTO pt_snap_metadata VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?, ?)", values)

    inspection = ImportMetadataService().inspect(db_path)

    assert inspection.status == "invalid"
    assert inspection.reason == "metadata_invalid"


@pytest.mark.parametrize(
    ("source_sha256", "device", "expected_reason"),
    [
        ("b" * 64, None, "source_changed"),
        ("a" * 64, 0, "device_changed"),
    ],
)
def test_cache_decision_invalidations(
    tmp_path: Path,
    source_sha256: str,
    device: int | None,
    expected_reason: str,
) -> None:
    db_path = _create_snapshot_db(tmp_path / "snapshot.db")
    service = ImportMetadataService()
    service.write(db_path, _metadata())

    decision = service.evaluate_cache(db_path, source_sha256, device)

    assert decision.reused is False
    assert decision.reason == expected_reason


def test_cache_hit_ignores_importer_version(tmp_path: Path) -> None:
    db_path = _create_snapshot_db(tmp_path / "snapshot.db")
    service = ImportMetadataService()
    service.write(db_path, _metadata(importer_version="old-version"))

    decision = service.evaluate_cache(db_path, "a" * 64, None)

    assert decision.reused is True
    assert decision.reason is None


def test_same_size_source_change_invalidates_cache(tmp_path: Path) -> None:
    first_source = tmp_path / "first.pkl"
    second_source = tmp_path / "second.pkl"
    first_source.write_bytes(b"abc")
    second_source.write_bytes(b"xyz")
    db_path = _create_snapshot_db(tmp_path / "snapshot.db")
    service = ImportMetadataService()
    first_hash = service.calculate_sha256(first_source)
    second_hash = service.calculate_sha256(second_source)
    service.write(db_path, _metadata(source_sha256=first_hash, source_size=3))

    decision = service.evaluate_cache(db_path, second_hash, None)

    assert first_source.stat().st_size == second_source.stat().st_size
    assert decision.reused is False
    assert decision.reason == "source_changed"


@pytest.mark.parametrize("requested_device", [None, 1])
def test_exact_device_selection_invalidates_cache(requested_device: int | None, tmp_path: Path) -> None:
    db_path = _create_snapshot_db(tmp_path / "snapshot.db")
    service = ImportMetadataService()
    service.write(db_path, _metadata(requested_device=0))

    decision = service.evaluate_cache(db_path, "a" * 64, requested_device)

    assert decision.reused is False
    assert decision.reason == "device_changed"


def test_force_bypasses_compatible_cache(tmp_path: Path) -> None:
    db_path = _create_snapshot_db(tmp_path / "snapshot.db")
    service = ImportMetadataService()
    service.write(db_path, _metadata())

    decision = service.evaluate_cache(db_path, "a" * 64, None, force=True)

    assert decision.reused is False
    assert decision.reason == "forced"


def test_force_missing_database_reports_database_missing(tmp_path: Path) -> None:
    decision = ImportMetadataService().evaluate_cache(tmp_path / "missing.db", "a" * 64, None, force=True)

    assert decision.reused is False
    assert decision.reason == "database_missing"


def test_import_format_change_invalidates_cache(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    import pt_snap_cli.core.importing.import_metadata as metadata_module

    db_path = _create_snapshot_db(tmp_path / "snapshot.db")
    service = ImportMetadataService()
    service.write(db_path, _metadata())
    monkeypatch.setattr(metadata_module, "IMPORT_FORMAT_VERSION", IMPORT_FORMAT_VERSION + 1)

    decision = service.evaluate_cache(db_path, "a" * 64, None)

    assert decision.reused is False
    assert decision.reason == "import_format_changed"
