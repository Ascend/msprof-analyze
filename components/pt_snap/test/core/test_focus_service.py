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

import json
import sqlite3
from pathlib import Path
from unittest.mock import patch

import pytest

from pt_snap_cli.config import Config
from pt_snap_cli.core import (
    DatabaseMissingError,
    FocusNotConfiguredError,
    FocusService,
    InvalidDeviceError,
)


@pytest.fixture(autouse=True)
def mock_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("PT_SNAP_DB_PATH", raising=False)
    with patch.object(Path, "home", return_value=tmp_path):
        yield


@pytest.fixture
def sample_db(tmp_path: Path) -> Path:
    db_path = tmp_path / "sample.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("CREATE TABLE dictionary (`table` TEXT, `column` TEXT, `key` TEXT, `value` TEXT)")
    conn.execute("CREATE TABLE trace_entry_0 (id INTEGER PRIMARY KEY, size INTEGER)")
    conn.execute("CREATE TABLE trace_entry_1 (id INTEGER PRIMARY KEY, size INTEGER)")
    conn.commit()
    conn.close()
    return db_path


class TestFocusService:
    def test_get_focus_uses_project_focus(self, sample_db: Path) -> None:
        config = Config()
        config.write_project_focus(sample_db, device_id=0)

        state = FocusService(config).get_focus()

        assert state.db_path == sample_db.resolve()
        assert state.device_id == 0
        assert state.source == "project"
        assert state.available_devices == [0, 1]

    def test_get_focus_with_missing_db_keeps_state(self, tmp_path: Path) -> None:
        focus_dir = tmp_path / ".pt-snap"
        focus_dir.mkdir()
        (focus_dir / "focus.json").write_text(json.dumps({"db_path": str(tmp_path / "missing.db"), "device_id": 0}))

        state = FocusService().get_focus()

        assert state.db_path == tmp_path / "missing.db"
        assert state.device_id == 0
        assert state.available_devices == []

    def test_set_project_focus_with_device_zero(self, sample_db: Path) -> None:
        state = FocusService().set_project_focus(sample_db, device_id=0)

        assert state.device_id == 0
        assert state.available_devices == [0, 1]
        focus_data = json.loads((Path.cwd() / ".pt-snap" / "focus.json").read_text())
        assert focus_data["device_id"] == 0

    def test_set_device_updates_project_focus(self, sample_db: Path) -> None:
        config = Config()
        config.write_project_focus(sample_db)

        state = FocusService(config).set_device(0)

        assert state.device_id == 0
        focus_data = json.loads((Path.cwd() / ".pt-snap" / "focus.json").read_text())
        assert focus_data["device_id"] == 0

    def test_set_device_without_focus_fails(self) -> None:
        with pytest.raises(FocusNotConfiguredError):
            FocusService().set_device(0)

    def test_set_device_with_missing_db_fails(self, tmp_path: Path) -> None:
        focus_dir = tmp_path / ".pt-snap"
        focus_dir.mkdir()
        (focus_dir / "focus.json").write_text(json.dumps({"db_path": str(tmp_path / "missing.db")}))

        with pytest.raises(DatabaseMissingError):
            FocusService().set_device(0)

    def test_set_device_invalid_device_fails(self, sample_db: Path) -> None:
        config = Config()
        config.write_project_focus(sample_db)

        with pytest.raises(InvalidDeviceError):
            FocusService(config).set_device(99)

    def test_validate_session_db_returns_devices(self, sample_db: Path) -> None:
        state = FocusService().validate_session_db(sample_db, device_id=1)

        assert state.db_path == sample_db.resolve()
        assert state.device_id == 1
        assert state.available_devices == [0, 1]
        assert not (Path.cwd() / ".pt-snap" / "focus.json").exists()

    def test_validate_session_db_rejects_invalid_device(self, sample_db: Path) -> None:
        with pytest.raises(InvalidDeviceError, match="Device 99 not found"):
            FocusService().validate_session_db(sample_db, device_id=99)

    def test_set_project_focus_reports_v1_layout_without_persisting_it(self, tmp_path: Path) -> None:
        db_path = tmp_path / "v1.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute("CREATE TABLE dictionary (`table` TEXT, `column` TEXT, `key` TEXT, `value` TEXT)")
        conn.execute("CREATE TABLE trace_entry_0 (id INTEGER PRIMARY KEY, callstack TEXT)")
        conn.commit()
        conn.close()

        state = FocusService().set_project_focus(db_path)
        focus_data = json.loads((Path.cwd() / ".pt-snap" / "focus.json").read_text())

        assert state.callstack_layout == "v1"
        assert state.callstack_layout_error is None
        assert "callstack_layout" not in focus_data
        assert set(focus_data) == {"db_path"}

    def test_get_focus_reports_layout_conflict_without_hiding_devices(self, tmp_path: Path) -> None:
        db_path = tmp_path / "conflict.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute("CREATE TABLE dictionary (`table` TEXT, `column` TEXT, `key` TEXT, `value` TEXT)")
        conn.execute("CREATE TABLE trace_entry_0 (id INTEGER PRIMARY KEY, callstack TEXT, callstackId INTEGER)")
        conn.commit()
        conn.close()
        config = Config()
        config.write_project_focus(db_path)

        state = FocusService(config).get_focus()
        assert state.available_devices == [0]
        assert state.callstack_layout is None
        assert state.callstack_layout_error is not None
        assert "both callstack and callstackId" in state.callstack_layout_error
