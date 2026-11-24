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

"""Tests for the high-level SnapshotAnalyzer API."""

import json
import sqlite3
import tempfile
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

import pytest

from pt_snap_cli.api import FocusState, SnapshotAnalyzer
from pt_snap_cli.core import InvalidDeviceError


@pytest.fixture
def valid_db() -> Path:
    """Create a valid test database."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)

    conn = sqlite3.connect(str(db_path))
    conn.execute("""
        CREATE TABLE dictionary (
            `table` TEXT, `column` TEXT, `key` TEXT, `value` TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE trace_entry_0 (
            id INTEGER PRIMARY KEY, action INTEGER, address INTEGER,
            size INTEGER, stream INTEGER, allocated INTEGER,
            active INTEGER, reserved INTEGER, callstack TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE block_0 (
            id INTEGER PRIMARY KEY, address INTEGER, size INTEGER,
            requestedSize INTEGER, state INTEGER, allocEventId INTEGER,
            freeEventId INTEGER
        )
    """)
    conn.commit()
    conn.close()

    yield db_path
    db_path.unlink(missing_ok=True)


@pytest.fixture(autouse=True)
def _reset_registry():
    """Reset the query registry singleton between tests."""
    from pt_snap_cli.query.registry import QueryRegistry

    QueryRegistry.reset()


@pytest.fixture(autouse=True)
def _isolate_config(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Isolate focus resolution from the developer's machine.

    ``Config.resolve_focus()`` consults, in order, ``PT_SNAP_DB_PATH``, the
    nearest ancestor ``.pt-snap/focus.json`` of the current directory, and the
    global config under ``Path.home()``. All three must be neutralized; a
    ``.pt-snap/focus.json`` left in the repository root by ``pt-snap focus`` or
    ``pt-snap import`` would otherwise leak into every test here (#52, #117).
    """
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("PT_SNAP_DB_PATH", raising=False)
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setattr(Path, "home", lambda: home)


class TestFocusState:
    def test_focus_state_fields(self) -> None:
        state = FocusState(
            db_path="/tmp/test.db",
            device_id=0,
            source="explicit",
            available_devices=[0, 1],
        )
        assert state.db_path == "/tmp/test.db"
        assert state.device_id == 0
        assert state.source == "explicit"
        assert state.available_devices == [0, 1]

    def test_get_focus_reports_v1_callstack_layout(self, valid_db: Path) -> None:
        analyzer = SnapshotAnalyzer(db_path=valid_db)
        state = analyzer.get_focus()
        assert state.callstack_layout == "v1"
        assert state.callstack_layout_error is None

    def test_get_focus_reports_conflicting_callstack_layout(self, tmp_path: Path) -> None:
        db_path = tmp_path / "conflict.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute("CREATE TABLE dictionary (`table` TEXT, `column` TEXT, `key` TEXT, `value` TEXT)")
        conn.execute("CREATE TABLE trace_entry_0 (id INTEGER PRIMARY KEY, callstack TEXT, callstackId INTEGER)")
        conn.commit()
        conn.close()

        state = SnapshotAnalyzer(db_path=db_path).get_focus()
        assert state.available_devices == [0]
        assert state.callstack_layout is None
        assert state.callstack_layout_error is not None
        assert "both callstack and callstackId" in state.callstack_layout_error


class TestSnapshotAnalyzerWithDB:
    def test_get_focus_with_explicit_db(self, valid_db: Path) -> None:
        analyzer = SnapshotAnalyzer(db_path=valid_db)
        state = analyzer.get_focus()
        assert state.db_path == str(valid_db)
        assert state.source == "explicit"
        assert 0 in state.available_devices
        assert state.callstack_layout == "v1"

    def test_set_focus_changes_db(self, valid_db: Path, tmp_path: Path) -> None:
        """Create a second DB and switch focus."""
        second_db = tmp_path / "second.db"
        conn = sqlite3.connect(str(second_db))
        conn.execute("CREATE TABLE dictionary (`table` TEXT, `column` TEXT, `key` TEXT, `value` TEXT)")
        conn.execute("CREATE TABLE trace_entry_1 (id INTEGER PRIMARY KEY)")
        conn.commit()
        conn.close()

        analyzer = SnapshotAnalyzer(db_path=valid_db)
        assert analyzer.get_focus().db_path == str(valid_db)

        state = analyzer.set_focus(db_path=str(second_db), device_id=1)
        assert state.db_path == str(second_db)
        assert state.device_id == 1

        second_db.unlink(missing_ok=True)

    def test_set_focus_invalid_db(self) -> None:
        analyzer = SnapshotAnalyzer()
        with pytest.raises(FileNotFoundError):
            analyzer.set_focus(db_path="/nonexistent/path/db.sqlite")

    def test_set_focus_rejects_invalid_device_without_mutating_state(self, valid_db: Path) -> None:
        analyzer = SnapshotAnalyzer(db_path=valid_db, device_id=0)

        with pytest.raises(InvalidDeviceError, match="Device 99 not found"):
            analyzer.set_focus(db_path=str(valid_db), device_id=99)

        state = analyzer.get_focus()
        assert state.db_path == str(valid_db)
        assert state.device_id == 0

    def test_set_focus_validates_device_only_update(self, valid_db: Path) -> None:
        analyzer = SnapshotAnalyzer(db_path=valid_db)

        state = analyzer.set_focus(device_id=0)

        assert state.device_id == 0
        with pytest.raises(InvalidDeviceError, match="Device 1 not found"):
            analyzer.set_focus(device_id=1)

    def test_set_focus_new_database_clears_unspecified_device(self, valid_db: Path, tmp_path: Path) -> None:
        second_db = tmp_path / "device-one.db"
        with closing(sqlite3.connect(second_db)) as conn:
            conn.execute("CREATE TABLE dictionary (`table` TEXT, `column` TEXT, `key` TEXT, `value` TEXT)")
            conn.execute("CREATE TABLE trace_entry_1 (id INTEGER PRIMARY KEY)")
        analyzer = SnapshotAnalyzer(db_path=valid_db, device_id=0)

        state = analyzer.set_focus(db_path=str(second_db))

        assert state.db_path == str(second_db)
        assert state.device_id is None
        assert state.available_devices == [1]

    def test_set_focus_device_requires_database(self) -> None:
        analyzer = SnapshotAnalyzer()

        with pytest.raises(RuntimeError, match="Set db_path"):
            analyzer.set_focus(device_id=0)

    def test_isolated_environment_has_no_inherited_focus(self) -> None:
        """The autouse fixture must hide any focus file above the repository (#52, #117)."""
        state = SnapshotAnalyzer().get_focus()

        assert state.source == "none"
        assert state.db_path is None

    def test_list_templates(self) -> None:
        analyzer = SnapshotAnalyzer()
        templates = analyzer.list_templates()
        assert isinstance(templates, list)
        assert len(templates) > 0

    def test_list_templates_by_category(self) -> None:
        analyzer = SnapshotAnalyzer()
        result = analyzer.list_templates(category="basic")
        assert isinstance(result, list)

    def test_get_template_info_exists(self) -> None:
        analyzer = SnapshotAnalyzer()
        info = analyzer.get_template_info("leak_detection")
        assert info is not None
        assert info["name"] == "leak_detection"
        assert "description" in info
        assert info["semantics_version"] == 1
        assert info["interpretation_limits"]
        json.dumps(info)
        alloc = next(column for column in info["output_schema"] if column["column"] == "allocEventId")
        assert alloc["units"] == "event_id"
        assert alloc["sentinel"] == -1

    def test_get_template_info_legacy_template_omits_semantics(self) -> None:
        analyzer = SnapshotAnalyzer()
        info = analyzer.get_template_info("allocation")
        assert info is not None
        assert info["semantics_version"] is None
        assert info["interpretation_limits"] == []
        assert info["output_schema"][0] == {"column": "id", "type": "int"}

    def test_get_template_info_not_found(self) -> None:
        analyzer = SnapshotAnalyzer()
        info = analyzer.get_template_info("nonexistent_template_xyz")
        assert info is None

    def test_get_template_info_propagates_unexpected_failure(self) -> None:
        analyzer = SnapshotAnalyzer()

        with patch.object(
            analyzer._query_service,
            "get_template_info",
            side_effect=RuntimeError("registry failed"),
        ):
            with pytest.raises(RuntimeError, match="registry failed"):
                analyzer.get_template_info("leak_detection")

    def test_execute_query_requires_focus(self) -> None:
        analyzer = SnapshotAnalyzer()
        # Mock resolve_focus to return no configured DB
        from pt_snap_cli.config import ResolvedFocus

        with patch.object(analyzer._config, "resolve_focus") as mock_resolve:
            mock_resolve.return_value = ResolvedFocus(None, "none", None, None)
            with pytest.raises(RuntimeError, match="No database configured"):
                analyzer.execute_query("leak_detection")

    def test_execute_query_with_focus(self, valid_db: Path) -> None:
        with SnapshotAnalyzer(db_path=valid_db) as analyzer:
            result = analyzer.execute_query("leak_detection", max_rows=10)
        assert "total" in result
        assert "returned" in result
        assert "device_id" in result
        assert "rows" in result
        assert "has_more" in result
        assert "truncated" in result
        assert "total_is_exact" in result
        assert result["template"] == "leak_detection"
        assert result["semantics_version"] == 1
        assert isinstance(result["rows"], list)

    def test_execute_query_max_rows_zero(self, valid_db: Path) -> None:
        """max_rows=0 returns all rows."""
        with SnapshotAnalyzer(db_path=valid_db) as analyzer:
            result = analyzer.execute_query("leak_detection", max_rows=0)
        # leak_detection on empty table returns 0 rows
        assert result["total"] == 0
        assert result["returned"] == 0

    def test_get_database_metadata_unavailable(self, valid_db: Path) -> None:
        analyzer = SnapshotAnalyzer(db_path=valid_db)

        result = analyzer.get_database_metadata()

        assert result["status"] == "unavailable"
        assert result["reason"] == "metadata_missing"

    def test_get_database_metadata_available(self, valid_db: Path) -> None:
        from dataclasses import replace

        from pt_snap_cli.core.importing.import_metadata import ImportMetadataService

        source = valid_db.parent / "snapshot.pkl"
        source.write_bytes(b"snapshot")
        service = ImportMetadataService()
        digest = service.calculate_sha256(source)
        service.write(
            valid_db,
            replace(service.build_metadata(source, digest, None), import_format_version=1),
        )
        analyzer = SnapshotAnalyzer(db_path=valid_db)

        result = analyzer.get_database_metadata()

        assert result["status"] == "available"
        assert result["metadata"]["source_sha256"] == digest
        source.unlink()

    def test_list_capabilities(self) -> None:
        payload = SnapshotAnalyzer().list_capabilities()
        assert "cli_version" in payload
        names = {item["name"] for item in payload["templates"]}
        assert "leak_detection" in names
        assert "preexisting_live" in names
        assert "freed_block_lifetime" in names
        assert "skills" not in payload

    def test_get_database_overview(self, valid_db: Path) -> None:
        with SnapshotAnalyzer(db_path=valid_db) as analyzer:
            payload = analyzer.get_database_overview()
        assert payload["db_path"] == str(valid_db.resolve())
        assert payload["devices"] == [{"device_id": 0, "first_event_id": None, "last_event_id": None}]
        assert payload["import_metadata"]["status"] == "unavailable"

    def test_get_database_overview_requires_focus(self) -> None:
        with pytest.raises(RuntimeError, match="No database configured"):
            SnapshotAnalyzer().get_database_overview()

    def test_get_database_overview_invalid_focus_file(self, tmp_path: Path) -> None:
        focus_dir = tmp_path / ".pt-snap"
        focus_dir.mkdir()
        (focus_dir / "focus.json").write_text("not-json", encoding="utf-8")
        with pytest.raises(ValueError):
            SnapshotAnalyzer().get_database_overview()
