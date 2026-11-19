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

"""Packaged replacements for the leak-analysis sqlite3 fallbacks."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from pt_snap_cli.context import Context
from pt_snap_cli.query.executor import QueryExecutor
from pt_snap_cli.query.registry import QueryRegistry, _load_all_templates, get_query


@pytest.fixture(autouse=True)
def _reload_query_templates() -> None:
    QueryRegistry.reset()
    _load_all_templates()


@pytest.fixture
def leak_fallback_db(tmp_path: Path) -> Path:
    db_path = tmp_path / "leak_fallback.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("CREATE TABLE dictionary (`table` TEXT, `column` TEXT, `key` TEXT, `value` TEXT)")
    conn.execute("""
        CREATE TABLE trace_entry_0 (
            id INTEGER PRIMARY KEY, action INTEGER, address INTEGER, size INTEGER,
            stream INTEGER, allocated INTEGER, active INTEGER, reserved INTEGER, callstack TEXT
        )
        """)
    conn.execute("""
        CREATE TABLE block_0 (
            id INTEGER PRIMARY KEY, address INTEGER, size INTEGER, requestedSize INTEGER,
            state INTEGER, allocEventId INTEGER, freeEventId INTEGER
        )
        """)
    conn.executemany(
        """
        INSERT INTO block_0
          (id, address, size, requestedSize, state, allocEventId, freeEventId)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (-10, 0xA000, 8192, 8000, 1, -1, -1),
            (-11, 0xB000, 2048, 2000, 1, -1, 8),
            (-12, 0xC000, 1024, 1000, 1, -1, None),
            (-13, 0xD000, 512, 500, 1, -1, -2),
            (-14, 0xE000, 256, 200, 1, -1, 3),
            (1, 0x1000, 4096, 4000, 1, 1, 50),
            (2, 0x2000, 2048, 2000, 1, 2, 3000),
            (3, 0x3000, 1024, 1000, 1, 3, 12000),
            (4, 0x4000, 512, 500, 1, 4, 40000),
            (5, 0x5000, 256, 200, 1, 5, 150000),
            (6, 0x6000, 128, 100, 1, 6, -1),
        ],
    )
    conn.commit()
    conn.close()
    return db_path


def _execute(db_path: Path, name: str, params: dict[str, object] | None = None) -> list[dict]:
    return QueryExecutor(Context(db_path)).execute_template(name, params or {}, device_id=0)


def test_preexisting_live_matches_hardened_predicate(leak_fallback_db: Path) -> None:
    template = get_query("preexisting_live")
    assert template is not None
    assert template.semantics_version == 1
    assert template.category == "business"

    rows = _execute(leak_fallback_db, "preexisting_live", {"event_id": 4})
    assert rows == [{"block_count": 3, "size_bytes": 3584}]


def test_preexisting_live_excludes_static_and_already_freed(leak_fallback_db: Path) -> None:
    later = _execute(leak_fallback_db, "preexisting_live", {"event_id": 8})
    assert later == [{"block_count": 2, "size_bytes": 1536}]


def test_preexisting_live_excludes_static_at_negative_event_ids(leak_fallback_db: Path) -> None:
    at_alloc_sentinel = _execute(leak_fallback_db, "preexisting_live", {"event_id": -1})
    before_alloc_sentinel = _execute(leak_fallback_db, "preexisting_live", {"event_id": -2})
    assert at_alloc_sentinel == [{"block_count": 4, "size_bytes": 3840}]
    assert before_alloc_sentinel == [{"block_count": 4, "size_bytes": 3840}]


def test_freed_block_lifetime_buckets_event_id_distance(leak_fallback_db: Path) -> None:
    template = get_query("freed_block_lifetime")
    assert template is not None
    assert template.semantics_version == 1
    rows = _execute(leak_fallback_db, "freed_block_lifetime")
    by_bucket = {row["lifetime_events"]: row for row in rows}
    assert by_bucket["<1k"]["block_count"] == 1
    assert by_bucket["<1k"]["size_bytes"] == 4096
    assert by_bucket["1k-5k"]["block_count"] == 1
    assert by_bucket["1k-5k"]["size_bytes"] == 2048
    assert by_bucket["5k-20k"]["block_count"] == 1
    assert by_bucket["20k-100k"]["block_count"] == 1
    assert by_bucket[">=100k"]["block_count"] == 1
    assert "lifetime_events" in {column["column"] for column in template.output_schema}


def test_freed_block_lifetime_excludes_unfreed_and_static(leak_fallback_db: Path) -> None:
    rows = _execute(leak_fallback_db, "freed_block_lifetime")
    assert sum(row["block_count"] for row in rows) == 5
