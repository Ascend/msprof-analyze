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

import sqlite3
from pathlib import Path
from unittest.mock import patch

import pytest

from pt_snap_cli.core import DatabaseSchemaError, FocusNotConfiguredError, OverviewService
from pt_snap_cli.core.importing.import_metadata import ImportMetadataService

pytestmark = pytest.mark.usefixtures("owned_service_instances")


@pytest.fixture(autouse=True)
def _isolate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("PT_SNAP_DB_PATH", raising=False)
    with patch.object(Path, "home", return_value=tmp_path):
        yield


def _overview_db(path: Path) -> Path:
    conn = sqlite3.connect(str(path))
    conn.execute("CREATE TABLE dictionary (`table` TEXT, `column` TEXT, `key` TEXT, `value` TEXT)")
    for device_id, event_ids in {0: (1, 4, 9), 1: (10, 12)}.items():
        conn.execute(f"""
            CREATE TABLE trace_entry_{device_id} (
                id INTEGER PRIMARY KEY, action INTEGER, address INTEGER, size INTEGER,
                stream INTEGER, allocated INTEGER, active INTEGER, reserved INTEGER, callstack TEXT
            )
            """)
        conn.executemany(
            f"INSERT INTO trace_entry_{device_id} (id, action) VALUES (?, 4)",
            [(event_id,) for event_id in event_ids],
        )
    conn.commit()
    conn.close()
    return path


def test_overview_reports_devices_bounds_and_missing_metadata(tmp_path: Path) -> None:
    db_path = _overview_db(tmp_path / "overview.db")
    payload = OverviewService().overview_to_dict(OverviewService().inspect(db_path))

    assert payload["db_path"] == str(db_path.resolve())
    assert payload["focus_source"] == "explicit"
    assert payload["devices"] == [
        {"device_id": 0, "first_event_id": 1, "last_event_id": 9},
        {"device_id": 1, "first_event_id": 10, "last_event_id": 12},
    ]
    assert payload["import_metadata"]["status"] == "unavailable"
    assert payload["import_metadata"]["reason"] == "metadata_missing"


def test_overview_includes_available_import_metadata(tmp_path: Path) -> None:
    db_path = _overview_db(tmp_path / "with_meta.db")
    source = tmp_path / "snapshot.pkl"
    source.write_bytes(b"snapshot")
    service = ImportMetadataService()
    digest = service.calculate_sha256(source)
    service.write(db_path, service.build_metadata(source, digest, None))

    payload = OverviewService().overview_to_dict(OverviewService().inspect(db_path))
    assert payload["import_metadata"]["status"] == "available"
    assert payload["import_metadata"]["metadata"]["source_sha256"] == digest


def test_overview_requires_a_database() -> None:
    with pytest.raises(FocusNotConfiguredError):
        OverviewService().inspect()


def test_overview_empty_device_has_null_bounds(tmp_path: Path) -> None:
    db_path = tmp_path / "empty.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("CREATE TABLE dictionary (`table` TEXT, `column` TEXT, `key` TEXT, `value` TEXT)")
    conn.execute("CREATE TABLE trace_entry_0 (id INTEGER PRIMARY KEY)")
    conn.commit()
    conn.close()

    payload = OverviewService().overview_to_dict(OverviewService().inspect(db_path))
    assert payload["devices"] == [{"device_id": 0, "first_event_id": None, "last_event_id": None}]


def test_overview_missing_id_column_is_schema_error(tmp_path: Path) -> None:
    db_path = tmp_path / "no-id.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("CREATE TABLE dictionary (`table` TEXT, `column` TEXT, `key` TEXT, `value` TEXT)")
    conn.execute("CREATE TABLE trace_entry_0 (action INTEGER)")
    conn.commit()
    conn.close()

    with pytest.raises(DatabaseSchemaError):
        OverviewService().inspect(db_path)


def test_overview_skips_non_numeric_trace_entry_suffix(tmp_path: Path) -> None:
    db_path = tmp_path / "mixed.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("CREATE TABLE dictionary (`table` TEXT, `column` TEXT, `key` TEXT, `value` TEXT)")
    conn.execute("CREATE TABLE trace_entry_foo (id INTEGER PRIMARY KEY)")
    conn.execute("CREATE TABLE trace_entry_0 (id INTEGER PRIMARY KEY)")
    conn.execute("INSERT INTO trace_entry_0 (id) VALUES (3)")
    conn.commit()
    conn.close()

    payload = OverviewService().overview_to_dict(OverviewService().inspect(db_path))
    assert payload["devices"] == [{"device_id": 0, "first_event_id": 3, "last_event_id": 3}]
