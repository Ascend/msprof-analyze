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
from pathlib import Path

from pt_snap_cli.snapshot.tools.adaptors.database.snapshot_db import SnapshotDb
from pt_snap_cli.snapshot.util.sqlite_meta import SqliteDB


def _pragma(conn: sqlite3.Connection, name: str) -> object:
    return conn.execute(f"PRAGMA {name}").fetchone()[0]


def _indexed_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    indexes = conn.execute(f"PRAGMA index_list('{table}')").fetchall()
    return {column[2] for index in indexes for column in conn.execute(f"PRAGMA index_info('{index[1]}')").fetchall()}


def test_snapshot_db_optimizes_import_writes(tmp_path: Path) -> None:
    db = SnapshotDb(str(tmp_path / "snapshot.db"))
    try:
        assert _pragma(db.conn, "journal_mode") == "memory"
        assert _pragma(db.conn, "synchronous") == 0
        assert _pragma(db.conn, "cache_size") == -65536
    finally:
        db.conn.close()


def test_generic_sqlite_db_keeps_default_write_settings(tmp_path: Path) -> None:
    baseline = sqlite3.connect(tmp_path / "baseline.db")
    db = SqliteDB(str(tmp_path / "generic.db"))
    try:
        for name in ("journal_mode", "synchronous", "cache_size"):
            assert _pragma(db.conn, name) == _pragma(baseline, name)
    finally:
        db.conn.close()
        baseline.close()


def test_create_trace_entry_table_adds_query_indexes(tmp_path: Path) -> None:
    db = SnapshotDb(str(tmp_path / "snapshot.db"))
    try:
        db.create_trace_entry_table(device=2)

        assert _indexed_columns(db.conn, "trace_entry_2") == {
            "allocated",
            "active",
            "reserved",
        }
    finally:
        db.conn.close()


def test_create_block_table_adds_query_indexes(tmp_path: Path) -> None:
    db = SnapshotDb(str(tmp_path / "snapshot.db"))
    try:
        db.create_block_table(device=2)

        assert _indexed_columns(db.conn, "block_2") == {
            "allocEventId",
            "freeEventId",
            "size",
        }
    finally:
        db.conn.close()
