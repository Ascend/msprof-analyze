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

"""Tests for peak memory report service."""

import sqlite3
from contextlib import closing
from pathlib import Path

import pytest

from pt_snap_cli.core.analysis.query_service import QueryService
from pt_snap_cli.core.analysis.report_service import ReportService
from pt_snap_cli.query.registry import QueryRegistry, _load_all_templates

pytestmark = pytest.mark.usefixtures("owned_service_instances")


@pytest.fixture(autouse=True)
def _reload_query_templates():
    QueryRegistry.reset()
    _load_all_templates()


@pytest.fixture
def report_db(tmp_path: Path) -> Path:
    db_path = tmp_path / "report.db"
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
            callstackId INTEGER
        )
    """)
    conn.execute("""
        CREATE TABLE callstack (
            id INTEGER PRIMARY KEY,
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
    conn.executemany(
        "INSERT INTO callstack (id, callstack) VALUES (?, ?)",
        [
            (0, "train.py:10"),
            (1, "block.py:20"),
            (2, "free.py:30"),
            (3, "after.py:40"),
        ],
    )
    conn.executemany(
        """
        INSERT INTO trace_entry_0
          (id, action, address, size, stream, allocated, active, reserved, callstackId)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (1, 2, 0x1000, 1024, 0, 1024, 1024, 4096, 0),
            (2, 2, 0x2000, 2048, 0, 3072, 3072, 4096, 1),
            (3, 3, 0x2000, 2048, 0, 1024, 1024, 8192, 2),
            (4, 2, 0x4000, 4096, 0, 5120, 5120, 8192, 3),
            (5, 2, 0x5000, 512, 0, 5632, 5632, 8192, None),
        ],
    )
    conn.executemany(
        """
        INSERT INTO block_0
          (id, address, size, requestedSize, state, allocEventId, freeEventId)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (-10, 0xA000, 8192, 8000, 1, -1, -1),
            (1, 0x1000, 1024, 1000, 1, 1, -1),
            (2, 0x2000, 2048, 2000, 0, 2, 3),
            (4, 0x4000, 4096, 4000, 1, 4, -1),
            (5, 0x5000, 512, 500, 1, 5, -1),
        ],
    )
    conn.commit()
    conn.close()
    return db_path


def test_peak_memory_report_selects_active_peak_event(report_db: Path) -> None:
    report = ReportService().peak_memory_report(report_db, metric="active")

    assert report.device_id == 0
    assert report.metric == "active"
    assert report.event_id == 5
    assert report.peak["peak_active"] == 5632
    assert report.allocator_gap is not None
    assert report.allocator_gap["peak_reserved_event_id"] == 3
    assert report.callstack_groups[0]["callstack"] == "[static] allocEventId=-1, freeEventId=-1"


def test_peak_memory_report_can_exclude_static(report_db: Path) -> None:
    report = ReportService().peak_memory_report(report_db, include_static=False)

    assert "[static] allocEventId=-1, freeEventId=-1" not in {row["callstack"] for row in report.callstack_groups}


@pytest.mark.parametrize("metric", [None, "active", "allocated", "reserved"])
@pytest.mark.parametrize("bounded", [False, True])
def test_null_peak_matches_memory_peak_without_attribution(report_db: Path, monkeypatch, metric, bounded: bool) -> None:
    selected_metric = metric or "active"
    bounds = {"start_id": 2, "end_id": 3} if bounded else {}
    with closing(sqlite3.connect(report_db)) as conn, conn:
        where = " WHERE id BETWEEN 2 AND 3" if bounded else ""
        conn.execute(f"UPDATE trace_entry_0 SET {selected_metric} = NULL{where}")
    expected = QueryService().execute_query("memory_peak", params=bounds, db_path=report_db)
    service = ReportService()
    calls = []
    execute = service._query_service.execute_query

    def tracked_execute(template, *args, **kwargs):
        calls.append(template)
        return execute(template, *args, **kwargs)

    def unexpected_attribution(*args, **kwargs):
        pytest.fail("A NULL peak must not invent an attribution event")

    monkeypatch.setattr(service._query_service, "execute_query", tracked_execute)
    monkeypatch.setattr(service, "event_attribution", unexpected_attribution)
    report = service.peak_memory_report(report_db, **bounds, **({"metric": metric} if metric is not None else {}))

    assert report.peak == expected.rows[0]
    assert report.event_id is None and report.allocator_gap is None
    assert report.callstack_groups == [] and report.total_is_exact
    assert report.effective_params["event_id"] is None
    assert not report.has_more and not report.truncated
    assert calls == ["allocator_gap"]


@pytest.mark.parametrize("active", [None, 0])
def test_report_preserves_null_unselected_peak_and_zero_peak(report_db: Path, active) -> None:
    with closing(sqlite3.connect(report_db)) as conn, conn:
        conn.execute("UPDATE trace_entry_0 SET active = ?", (active,))
    expected = QueryService().execute_query("memory_peak", db_path=report_db)
    metric = "reserved" if active is None else "active"
    report = ReportService().peak_memory_report(report_db, metric=metric)

    assert report.peak == expected.rows[0]
    assert report.event_id == (3 if active is None else 1)
    assert report.allocator_gap is not None
    assert report.callstack_groups


def test_peak_memory_report_rejects_invalid_metric(report_db: Path) -> None:
    with pytest.raises(ValueError, match="Invalid metric"):
        ReportService().peak_memory_report(report_db, metric="invalid")  # type: ignore[arg-type]


def test_peak_memory_report_handles_empty_trace(tmp_path: Path) -> None:
    db_path = tmp_path / "empty.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("CREATE TABLE dictionary (`table` TEXT, `column` TEXT, `key` TEXT, `value` TEXT)")
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
            callstackId INTEGER
        )
    """)
    conn.execute("""
        CREATE TABLE callstack (
            id INTEGER PRIMARY KEY,
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

    report = ReportService().peak_memory_report(db_path)

    assert report.event_id is None
    assert report.allocator_gap is None
    assert report.callstack_groups == []


def test_peak_memory_report_reads_v1_inline_callstack(tmp_path: Path) -> None:
    db_path = tmp_path / "v1-report.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("CREATE TABLE dictionary (`table` TEXT, `column` TEXT, `key` TEXT, `value` TEXT)")
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
    conn.executemany(
        """
        INSERT INTO trace_entry_0
          (id, action, address, size, stream, allocated, active, reserved, callstack)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (1, 2, 0x1000, 1024, 0, 1024, 1024, 4096, "train.py:10"),
            (5, 2, 0x5000, 512, 0, 5632, 5632, 8192, None),
        ],
    )
    conn.executemany(
        """
        INSERT INTO block_0
          (id, address, size, requestedSize, state, allocEventId, freeEventId)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (-10, 0xA000, 8192, 8000, 1, -1, -1),
            (1, 0x1000, 1024, 1000, 1, 1, -1),
            (5, 0x5000, 512, 500, 1, 5, -1),
        ],
    )
    conn.commit()
    conn.close()

    report = ReportService().peak_memory_report(db_path, metric="active")

    assert report.event_id == 5
    by_callstack = {row["callstack"]: row for row in report.callstack_groups}
    assert by_callstack["[static] allocEventId=-1, freeEventId=-1"]["size_bytes"] == 8192
    assert by_callstack["train.py:10"]["size_bytes"] == 1024
    assert by_callstack["[missing callstack]"]["size_bytes"] == 512
