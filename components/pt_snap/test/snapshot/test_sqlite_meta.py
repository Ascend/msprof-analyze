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
from typing import Optional, Union

import pytest

from pt_snap_cli.snapshot.tools.adaptors.database.snapshot_db import SnapshotDb
from pt_snap_cli.snapshot.util.sqlite_meta import (
    SqliteColumn,
    SqliteDB,
    SqliteTable,
    _map_py_type_to_sqlite,
    _parse_default_value,
    _sqlite_type_to_py_type,
)


def test_type_mapping_helpers_cover_supported_and_fallback_types():
    assert _map_py_type_to_sqlite(int) == "INTEGER"
    assert _map_py_type_to_sqlite(float) == "REAL"
    assert _map_py_type_to_sqlite(str) == "TEXT"
    assert _map_py_type_to_sqlite(bytes) == "BLOB"
    assert _map_py_type_to_sqlite(Optional[int]) == "INTEGER"  # noqa: UP045
    assert _map_py_type_to_sqlite(list) == "TEXT"

    assert _sqlite_type_to_py_type("INTEGER") is int
    assert _sqlite_type_to_py_type("TEXT") is str
    assert _sqlite_type_to_py_type("BLOB") is bytes
    assert _sqlite_type_to_py_type("REAL") is float
    assert _sqlite_type_to_py_type("") is str
    assert _sqlite_type_to_py_type("NUMERIC") is str


@pytest.mark.parametrize(
    ("py_type", "sqlite_type"),
    [(int, "INTEGER"), (float, "REAL"), (str, "TEXT"), (bool, "INTEGER"), (bytes, "BLOB")],
)
def test_type_mapping_supports_both_optional_spellings(py_type, sqlite_type):
    assert _map_py_type_to_sqlite(Optional[py_type]) == sqlite_type  # noqa: UP045
    assert _map_py_type_to_sqlite(py_type | None) == sqlite_type
    assert _map_py_type_to_sqlite(None | py_type) == sqlite_type


@pytest.mark.parametrize(
    "py_type",
    [
        int | str,
        int | str | None,
        Union[int, str],  # noqa: UP007
        Union[int, str, None],  # noqa: UP007
        list[int] | None,
        Optional[list[int]],  # noqa: UP045
        type(None),
    ],
)
def test_type_mapping_keeps_ambiguous_and_unsupported_types_as_text(py_type):
    assert _map_py_type_to_sqlite(py_type) == "TEXT"


def test_pep604_columns_preserve_sqlite_affinity_and_nulls():
    connection = sqlite3.connect(":memory:")
    try:
        table = SqliteTable(
            "nullable_values",
            [
                SqliteColumn("number", int | None),
                SqliteColumn("fraction", float | None),
                SqliteColumn("flag", bool | None),
                SqliteColumn("payload", bytes | None),
            ],
        )
        table.create_table(connection)
        assert [row[2] for row in connection.execute("PRAGMA table_info(nullable_values)")] == [
            "INTEGER",
            "REAL",
            "INTEGER",
            "BLOB",
        ]
        table.insert_records(
            connection,
            [
                {"number": 10, "fraction": 1.5, "flag": True, "payload": b"ten"},
                {"number": 2, "fraction": 2.5, "flag": False, "payload": b"two"},
                {"number": None, "fraction": None, "flag": None, "payload": None},
            ],
        )
        assert connection.execute(
            "SELECT number, fraction, flag, payload FROM nullable_values ORDER BY number"
        ).fetchall() == [(None, None, None, None), (2, 2.5, 0, b"two"), (10, 1.5, 1, b"ten")]
    finally:
        connection.close()


def test_parse_default_value_handles_literals_bool_and_strings():
    assert _parse_default_value(None) is None
    assert _parse_default_value("1") is True
    assert _parse_default_value("0") is False
    assert _parse_default_value("true") is True
    assert _parse_default_value("false") is False
    assert _parse_default_value("123") == 123
    assert _parse_default_value("'hello'") == "hello"
    assert _parse_default_value('"world"') == "world"
    assert _parse_default_value("CURRENT_TIMESTAMP") == "CURRENT_TIMESTAMP"


def test_sqlite_column_validation_and_sql_generation():
    with pytest.raises(ValueError):
        SqliteColumn("id", int, autoincrement=True)
    with pytest.raises(ValueError):
        SqliteColumn("id", str, primary_key=True, autoincrement=True)

    column = SqliteColumn("name", str, not_null=True, unique=True, default="O'Reilly")
    sql = column.to_sql_def()
    assert "`name` TEXT" in sql
    assert "NOT NULL" in sql
    assert "UNIQUE" in sql
    assert "DEFAULT 'O''Reilly'" in sql
    assert SqliteColumn("flag", bool, default=True)._format_default() == "1"
    assert SqliteColumn("score", float, default=1.5)._format_default() == "1.5"
    assert SqliteColumn("misc", dict, default={"a": 1})._format_default() == "'{'a': 1}'"


def test_sqlite_table_helpers_create_insert_and_index(tmp_path: Path):
    connection = sqlite3.connect(tmp_path / "table.sqlite")
    table = SqliteTable(
        "users",
        [
            SqliteColumn("id", int, primary_key=True),
            SqliteColumn("name", str, not_null=True),
            SqliteColumn("active", bool, default=False, value_map={True: 1, False: 0}),
        ],
    )

    sql = table.to_sql_def(delete_if_exists=True)
    assert "DROP TABLE IF EXISTS users;" in sql
    assert "CREATE TABLE users" in sql
    table.create_table(connection, delete_if_exists=True)
    table.create_index(connection, "name")
    table.insert_record(connection, {"id": 1, "name": "Alice", "active": True})
    table.insert_records(
        connection,
        [
            {"id": 2, "name": "Bob", "active": False},
            {"id": 3, "name": "Cara", "active": True},
        ],
    )

    rows = connection.execute("SELECT id, name, active FROM users ORDER BY id").fetchall()
    assert rows == [(1, "Alice", 1), (2, "Bob", 0), (3, "Cara", 1)]
    assert SqliteTable.get_insert_columns_by_record({"a": 1, "b": 2}) == ["`a`", "`b`"]
    assert SqliteTable.get_insert_placeholder_by_record({"a": 1, "b": 2}) == "?, ?"
    assert table.get_insert_values_by_records(
        [
            {"id": 4, "name": "Dan", "active": True},
            {"id": 5, "name": "Eve", "active": False},
        ]
    ) == [(4, "Dan", 1), (5, "Eve", 0)]
    assert table.get_insert_values_by_records([]) == []
    connection.close()


def test_sqlite_db_create_get_delete_and_dictionary_table(tmp_path: Path):
    db = SqliteDB(str(tmp_path / "meta.sqlite"), with_dictionary_table=True)
    assert db.is_table_exists("dictionary") is True
    assert db.get_table_by_name("dictionary").name == "dictionary"
    table = SqliteTable(
        "events",
        [
            SqliteColumn("id", int, primary_key=True, autoincrement=True),
            SqliteColumn("status", str, default="new", value_map={"ALLOC": "alloc"}),
            SqliteColumn("enabled", bool, default=True),
        ],
    )
    db.create_table(table, delete_if_exists=True)

    restored = db.get_table_by_name("events")
    assert restored.column_dict["id"].primary_key is True
    assert restored.column_dict["id"].autoincrement is True
    assert restored.column_dict["status"].default == "new"
    assert restored.column_dict["enabled"].default is True
    dictionary_rows = db.conn.execute(
        "SELECT `table`, `column`, `key`, `value` FROM dictionary ORDER BY rowid"
    ).fetchall()
    assert ("events", "status", "alloc", "ALLOC") in dictionary_rows

    db.delete_table("events")
    assert db.conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='events'").fetchone() is None
    db.conn.close()


def test_sqlite_db_missing_file_without_auto_create_raises(tmp_path: Path):
    with pytest.raises(FileNotFoundError):
        SqliteDB(str(tmp_path / "missing" / "db.sqlite"), auto_create=False)


def test_get_table_by_name_raises_for_missing_table(tmp_path: Path):
    db = SqliteDB(str(tmp_path / "empty.sqlite"))
    with pytest.raises(ValueError):
        db.get_table_by_name("missing_table")
    db.conn.close()


def pragma(connection: sqlite3.Connection, name: str):
    return connection.execute(f"PRAGMA {name}").fetchone()[0]


def indexed_columns(connection: sqlite3.Connection, table: str):
    indexes = connection.execute(f"PRAGMA index_list('{table}')").fetchall()
    return {
        column[2] for index in indexes for column in connection.execute(f"PRAGMA index_info('{index[1]}')").fetchall()
    }


def test_snapshot_db_optimizes_import_writes(tmp_path: Path):
    db = SnapshotDb(str(tmp_path / "snapshot.db"))
    try:
        assert pragma(db.conn, "journal_mode") == "memory"
        assert pragma(db.conn, "synchronous") == 0
        assert pragma(db.conn, "cache_size") == -65536
    finally:
        db.conn.close()


def test_generic_sqlite_db_keeps_default_write_settings(tmp_path: Path):
    baseline = sqlite3.connect(tmp_path / "baseline.db")
    db = SqliteDB(str(tmp_path / "generic.db"))
    try:
        for name in ("journal_mode", "synchronous", "cache_size"):
            assert pragma(db.conn, name) == pragma(baseline, name)
    finally:
        db.conn.close()
        baseline.close()


def test_create_trace_entry_table_adds_query_indexes(tmp_path: Path):
    db = SnapshotDb(str(tmp_path / "snapshot.db"))
    try:
        db.create_trace_entry_table(device=2)
        assert indexed_columns(db.conn, "trace_entry_2") == {
            "allocated",
            "active",
            "reserved",
        }
    finally:
        db.conn.close()


def test_create_block_table_adds_query_indexes(tmp_path: Path):
    db = SnapshotDb(str(tmp_path / "snapshot.db"))
    try:
        db.create_block_table(device=2)
        assert indexed_columns(db.conn, "block_2") == {
            "allocEventId",
            "freeEventId",
            "size",
        }
    finally:
        db.conn.close()
