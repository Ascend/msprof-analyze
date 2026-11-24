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

"""Tests for Context class."""

import sqlite3
import tempfile
from contextlib import closing
from pathlib import Path

import pytest

from pt_snap_cli.context import Context, DatabaseNotFoundError, SchemaVersionError


@pytest.fixture
def valid_db() -> Path:
    """Create a valid test database."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)

    conn = sqlite3.connect(str(db_path))
    conn.execute("""
        CREATE TABLE dictionary (
            `table` TEXT,
            `column` TEXT,
            `key` TEXT,
            `value` TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE trace_entry_0 (
            id INTEGER PRIMARY KEY,
            action INTEGER,
            address INTEGER,
            size INTEGER,
            stream INTEGER,
            allocated INTEGER,
            active INTEGER,
            reserved INTEGER,
            callstack TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE block_0 (
            id INTEGER PRIMARY KEY,
            address INTEGER,
            size INTEGER,
            requestedSize INTEGER,
            state INTEGER,
            allocEventId INTEGER,
            freeEventId INTEGER
        )
    """)
    conn.commit()
    conn.close()

    yield db_path

    db_path.unlink(missing_ok=True)


@pytest.fixture
def invalid_db() -> Path:
    """Create an invalid test database (missing dictionary table)."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)

    conn = sqlite3.connect(str(db_path))
    conn.execute("""
        CREATE TABLE other_table (
            id INTEGER PRIMARY KEY
        )
    """)
    conn.commit()
    conn.close()

    yield db_path

    db_path.unlink(missing_ok=True)


class TestContext:
    """Test Context class."""

    def test_context_with_valid_database(self, valid_db: Path) -> None:
        """Test creating context with valid database."""
        ctx = Context(valid_db)
        assert ctx.db_path == valid_db
        assert ctx.device_ids == [0]
        assert ctx.callstack_layout == "v1"

    def test_context_database_not_found(self, tmp_path: Path) -> None:
        """Test creating context with non-existent database."""
        non_existent = tmp_path / "not_found.db"
        with pytest.raises(DatabaseNotFoundError):
            Context(non_existent)

    def test_context_invalid_schema(self, invalid_db: Path) -> None:
        """Test creating context with invalid schema."""
        with pytest.raises(SchemaVersionError):
            Context(invalid_db)

    def test_connect_read_only(self, valid_db: Path) -> None:
        """Test database is opened in read-only mode."""
        ctx = Context(valid_db)
        with ctx.connect() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM trace_entry_0")
            assert cursor.fetchall() == []

            with pytest.raises(sqlite3.OperationalError):
                cursor.execute("INSERT INTO trace_entry_0 (id, action) VALUES (1, 4)")

    def test_cursor_without_connection(self, valid_db: Path) -> None:
        """Test cursor raises error without connection."""
        ctx = Context(valid_db)
        with pytest.raises(RuntimeError, match="not connected"):
            ctx.cursor()

    def test_device_ids_discovery(self, valid_db: Path) -> None:
        """Test device ID discovery from table names."""
        ctx = Context(valid_db)
        assert ctx.device_ids == [0]

    def test_device_ids_skip_non_numeric_suffix(self, tmp_path: Path) -> None:
        db_path = tmp_path / "mixed.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute("CREATE TABLE dictionary (`table` TEXT, `column` TEXT, `key` TEXT, `value` TEXT)")
        conn.execute("CREATE TABLE trace_entry_foo (id INTEGER PRIMARY KEY)")
        conn.execute("CREATE TABLE trace_entry_0 (id INTEGER PRIMARY KEY)")
        conn.commit()
        conn.close()
        assert Context(db_path).device_ids == [0]

    def test_device_trace_bounds_empty_and_populated(self, valid_db: Path) -> None:
        ctx = Context(valid_db)
        assert ctx.device_trace_bounds() == [(0, None, None)]
        with closing(sqlite3.connect(str(valid_db))) as conn, conn:
            conn.execute("INSERT INTO trace_entry_0 (id, action) VALUES (3, 4), (9, 4)")
            conn.commit()
        assert Context(valid_db).device_trace_bounds() == [(0, 3, 9)]

    def test_device_filter(self, valid_db: Path) -> None:
        """Test device filtering."""
        ctx = Context(valid_db, devices=[0])
        assert ctx.device_ids == [0]

        ctx2 = Context(valid_db, devices=[1])
        assert ctx2.device_ids == []

    def test_v2_callstack_layout_detection(self, tmp_path: Path) -> None:
        db_path = tmp_path / "v2.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute("CREATE TABLE dictionary (`table` TEXT, `column` TEXT, `key` TEXT, `value` TEXT)")
        conn.execute("CREATE TABLE callstack (id INTEGER PRIMARY KEY, callstack TEXT)")
        conn.execute("CREATE TABLE trace_entry_0 (id INTEGER PRIMARY KEY, callstackId INTEGER)")
        conn.commit()
        conn.close()

        assert Context(db_path).callstack_layout == "v2"

    def test_both_callstack_columns_are_incompatible(self, tmp_path: Path) -> None:
        db_path = tmp_path / "both.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute("CREATE TABLE dictionary (`table` TEXT, `column` TEXT, `key` TEXT, `value` TEXT)")
        conn.execute("CREATE TABLE trace_entry_0 (id INTEGER PRIMARY KEY, callstack TEXT, callstackId INTEGER)")
        conn.commit()
        conn.close()

        ctx = Context(db_path)
        assert ctx.callstack_layout is None
        assert ctx.callstack_layout_error is not None
        assert "both callstack and callstackId" in ctx.callstack_layout_error

    def test_close_connection(self, valid_db: Path) -> None:
        """Test closing connection."""
        ctx = Context(valid_db)
        with ctx.connect() as conn:
            assert conn is not None
        assert ctx._conn is None
