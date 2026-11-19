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

"""Tests for shell completion functions."""

import json
import sqlite3
from pathlib import Path

import pytest

from pt_snap_cli.completion import (
    complete_categories,
    complete_device_ids,
    complete_template_names,
)
from pt_snap_cli.config import (
    DB_PATH_KEY,
    ENV_DB_PATH,
    PROJECT_FOCUS_DIR,
    PROJECT_FOCUS_FILE,
)
from pt_snap_cli.query.config import QueryTemplate
from pt_snap_cli.query.registry import QueryRegistry, register_query


@pytest.fixture(autouse=True)
def isolate_completion_state(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    """Reset registries and isolate focus resolution from the host machine."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv(ENV_DB_PATH, raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    QueryRegistry.reset()
    yield
    QueryRegistry.reset()


def _create_sample_db(db_path: Path) -> Path:
    """Create a sample SQLite database with device tables."""
    conn = sqlite3.connect(str(db_path))
    conn.execute("""
        CREATE TABLE dictionary (
            `table` TEXT, `column` TEXT, `key` TEXT, `value` TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE trace_entry_0 (
            id INTEGER PRIMARY KEY, action TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE trace_entry_1 (
            id INTEGER PRIMARY KEY, action TEXT
        )
    """)
    conn.commit()
    conn.close()
    return db_path


class TestCompleteTemplateNames:
    def test_returns_registered_templates(self):
        register_query(QueryTemplate(name="alpha_z_test", query="SELECT 1"))

        result = complete_template_names()
        assert "alpha_z_test" in result

    def test_returns_sorted(self):
        register_query(QueryTemplate(name="zebra_test", query="SELECT 1"))
        register_query(QueryTemplate(name="apple_test", query="SELECT 1"))
        after = complete_template_names()

        # Verify the result is sorted and contains our new entries
        assert after == sorted(after)
        assert "apple_test" in after
        assert "zebra_test" in after


class TestCompleteCategories:
    def test_returns_three_categories(self):
        result = complete_categories()
        assert len(result) == 3
        assert set(result) == {"basic", "statistical", "business"}

    def test_order_is_fixed(self):
        result = complete_categories()
        assert result == sorted(result)


class TestCompleteDeviceIds:
    @pytest.mark.parametrize("valid", [True, False])
    def test_completion_closes_connection(self, tmp_path, monkeypatch, valid):
        db_path = tmp_path / "completion.db"
        if valid:
            _create_sample_db(db_path)
        else:
            db_path.write_text("not SQLite")
        monkeypatch.setenv(ENV_DB_PATH, str(db_path))
        connections = []
        original_connect = sqlite3.connect

        def tracked_connect(*args, **kwargs):
            conn = original_connect(*args, **kwargs)
            connections.append(conn)
            return conn

        monkeypatch.setattr(sqlite3, "connect", tracked_connect)
        assert complete_device_ids() == (["0", "1"] if valid else [])
        assert len(connections) == 1
        try:
            with pytest.raises(sqlite3.ProgrammingError, match="closed"):
                connections[0].execute("SELECT 1")
        finally:
            connections[0].close()

    def test_returns_device_ids_from_db(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        db_path = _create_sample_db(tmp_path / "test.db")
        monkeypatch.setenv(ENV_DB_PATH, str(db_path))

        result = complete_device_ids()
        assert result == ["0", "1"]

    def test_returns_empty_for_no_db(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.chdir(tmp_path)
        result = complete_device_ids()
        # Without any DB configured, should return empty list
        assert result == []

    def test_returns_empty_for_invalid_db(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        invalid_file = tmp_path / "not_a_db.txt"
        invalid_file.write_text("not a database")
        monkeypatch.setenv(ENV_DB_PATH, str(invalid_file))

        result = complete_device_ids()
        assert result == []

    def test_uses_project_focus(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        db_path = _create_sample_db(tmp_path / "test.db")
        focus_dir = tmp_path / PROJECT_FOCUS_DIR
        focus_dir.mkdir()
        focus_file = focus_dir / PROJECT_FOCUS_FILE
        focus_file.write_text(json.dumps({DB_PATH_KEY: str(db_path)}))
        monkeypatch.chdir(tmp_path)

        result = complete_device_ids()
        assert result == ["0", "1"]

    def test_sorted_by_integer_value(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        """Device IDs should be sorted numerically, not lexicographically."""
        db_path = tmp_path / "test.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute("CREATE TABLE dictionary (k TEXT, v TEXT)")
        for dev in [0, 1, 2, 10]:
            conn.execute(f"CREATE TABLE trace_entry_{dev} (id INTEGER PRIMARY KEY)")
        conn.commit()
        conn.close()

        monkeypatch.setenv(ENV_DB_PATH, str(db_path))

        result = complete_device_ids()
        assert result == ["0", "1", "2", "10"]
