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

"""Regression tests for the ``memory_peak`` template rewrite.

The CTE-based rewrite must produce byte-identical results to the original
nested-subquery form for every ``start_id`` / ``end_id`` combination --
including ``null`` and edge cases such as inverted or out-of-range windows.
These guard against regressions in the SQL itself as well as in the
``QueryService`` -> ``QueryExecutor`` integration that drives it.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from pt_snap_cli.context import Context
from pt_snap_cli.query.executor import QueryExecutor
from pt_snap_cli.query.registry import QueryRegistry, _load_all_templates


@pytest.fixture(autouse=True)
def _isolate_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Run each test from a temp directory so ``write_project_focus``
    doesn't pollute the workspace root with a stray ``.pt-snap/``.
    """
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("PT_SNAP_DB_PATH", raising=False)


ORIGINAL_SQL = """
SELECT
  (SELECT MAX(allocated) FROM trace_entry_0
    {start_cond}
  ) as peak_allocated,
  (SELECT MIN(id) FROM trace_entry_0
    WHERE allocated = (SELECT MAX(allocated) FROM trace_entry_0
      {start_cond}
    )
    {end_cond_inner}
  ) as peak_allocated_event_id,
  (SELECT MAX(active) FROM trace_entry_0
    {start_cond}
  ) as peak_active,
  (SELECT MIN(id) FROM trace_entry_0
    WHERE active = (SELECT MAX(active) FROM trace_entry_0
      {start_cond}
    )
    {end_cond_inner}
  ) as peak_active_event_id,
  (SELECT MAX(reserved) FROM trace_entry_0
    {start_cond}
  ) as peak_reserved,
  (SELECT MIN(id) FROM trace_entry_0
    WHERE reserved = (SELECT MAX(reserved) FROM trace_entry_0
      {start_cond}
    )
    {end_cond_inner}
  ) as peak_reserved_event_id
"""


def _render_original(start_id: int | None, end_id: int | None) -> str:
    if start_id is not None and end_id is not None:
        start_cond = f"WHERE id >= {start_id} AND id <= {end_id}"
        end_cond_inner = f"AND id >= {start_id} AND id <= {end_id}"
    elif start_id is not None:
        start_cond = f"WHERE id >= {start_id}"
        end_cond_inner = f"AND id >= {start_id}"
    elif end_id is not None:
        start_cond = f"WHERE id <= {end_id}"
        end_cond_inner = f"AND id <= {end_id}"
    else:
        start_cond = ""
        end_cond_inner = ""
    return ORIGINAL_SQL.format(start_cond=start_cond, end_cond_inner=end_cond_inner)


@pytest.fixture(autouse=True)
def _reload_registry() -> None:
    QueryRegistry.reset()
    _load_all_templates()


@pytest.fixture
def memory_peak_db(tmp_path: Path) -> Path:
    """Snapshot database with non-trivial, overlapping peaks per metric."""
    db_path = tmp_path / "memory_peak.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("""
        CREATE TABLE dictionary (
            `table` TEXT, `column` TEXT, `key` TEXT, `value` TEXT
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
    # Rows are crafted so:
    #   * The all-time allocated peak lives at id=4 (not at id=8 which is
    #     inside an arbitrary window).
    #   * The active peak is id=5.
    #   * The reserved peak is id=3.
    #   * Different windows pick different ids.
    conn.executemany(
        """
        INSERT INTO trace_entry_0
          (id, action, address, size, stream, allocated, active, reserved, callstack)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (1, 2, 0x1000, 1024, 0, 100, 50, 200, "a"),
            (2, 2, 0x2000, 2048, 0, 200, 150, 400, "b"),
            (3, 3, 0x2000, 2048, 0, 100, 100, 800, "c"),
            (4, 2, 0x4000, 4096, 0, 500, 300, 500, "d"),
            (5, 2, 0x5000, 512, 0, 400, 700, 600, "e"),
            (6, 2, 0x6000, 1024, 0, 400, 500, 1000, "f"),
            (7, 3, 0x6000, 1024, 0, 200, 200, 500, "g"),
            (8, 2, 0x8000, 2048, 0, 350, 350, 700, "h"),
        ],
    )
    conn.commit()
    conn.close()
    return db_path


def _execute_cte(db_path: Path, params: dict) -> dict:
    ctx = Context(db_path)
    executor = QueryExecutor(ctx)
    rows = executor.execute_template("memory_peak", params=params, device_id=0)
    ctx.close()
    return rows[0]


def _execute_original(db_path: Path, start_id: int | None, end_id: int | None) -> tuple:
    conn = sqlite3.connect(str(db_path))
    try:
        return conn.execute(_render_original(start_id, end_id)).fetchone()
    finally:
        conn.close()


@pytest.mark.parametrize(
    "start_id, end_id",
    [
        (None, None),
        (3, None),
        (None, 5),
        (3, 6),
        (5, 5),
        (1, 8),
        (10, 20),  # out of range
        (5, 1),  # inverted window -- yields empty set
        (4, 4),
        (None, 3),
    ],
)
def test_memory_peak_cte_matches_original(memory_peak_db: Path, start_id: int | None, end_id: int | None) -> None:
    """The CTE rewrite must be byte-identical to the original nested
    subquery form for every start_id/end_id combination (including
    inverted and out-of-range windows).
    """
    expected = _execute_original(memory_peak_db, start_id, end_id)
    actual = _execute_cte(
        memory_peak_db,
        {"start_id": start_id, "end_id": end_id},
    )

    # Translate the CTE dict into the same column order as ``expected`` so
    # tuple comparison works regardless of dict ordering.
    if expected is None:
        assert actual == {}
        return
    actual_tuple = tuple(
        actual[name]
        for name in (
            "peak_allocated",
            "peak_allocated_event_id",
            "peak_active",
            "peak_active_event_id",
            "peak_reserved",
            "peak_reserved_event_id",
        )
    )
    assert actual_tuple == expected


def test_memory_peak_null_start_and_end_runs_via_query_service(
    memory_peak_db: Path,
    request,
) -> None:
    """End-to-end smoke test: the rewritten template is reachable through
    the QueryService -> QueryExecutor pipeline used by the CLI and
    SnapshotAnalyzer.
    """
    from pt_snap_cli.config import Config
    from pt_snap_cli.core.analysis.query_service import QueryService

    config = Config()
    config.write_project_focus(memory_peak_db, device_id=0)

    service = QueryService()
    request.addfinalizer(service.close)
    result = service.execute_query("memory_peak")

    assert result.total == 1
    row = result.rows[0]
    assert row["peak_allocated"] == 500
    assert row["peak_allocated_event_id"] == 4
    assert row["peak_active"] == 700
    assert row["peak_active_event_id"] == 5
    assert row["peak_reserved"] == 1000
    assert row["peak_reserved_event_id"] == 6
