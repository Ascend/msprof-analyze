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

"""Real-SQLite report coverage and completeness contracts across CLI formats."""

import json
import sqlite3
from contextlib import closing
from pathlib import Path

import pytest
from typer.testing import CliRunner

from pt_snap_cli.api import SnapshotAnalyzer
from pt_snap_cli.cli import app
from pt_snap_cli.query.registry import QueryRegistry, _load_all_templates


@pytest.fixture
def attribution_db(tmp_path: Path) -> Path:
    QueryRegistry.reset()
    _load_all_templates()
    db = tmp_path / "attribution.db"
    with closing(sqlite3.connect(db)) as conn, conn:
        conn.executescript("""
            CREATE TABLE dictionary (`table` TEXT, `column` TEXT, `key` TEXT, `value` TEXT);
            CREATE TABLE callstack (id INTEGER PRIMARY KEY, callstack TEXT);
            CREATE TABLE trace_entry_0 (
                id INTEGER PRIMARY KEY, action INTEGER, address INTEGER, size INTEGER,
                stream INTEGER, allocated INTEGER, active INTEGER, reserved INTEGER,
                callstackId INTEGER
            );
            CREATE TABLE block_0 (
                id INTEGER PRIMARY KEY, address INTEGER, size INTEGER,
                requestedSize INTEGER, state INTEGER, allocEventId INTEGER, freeEventId INTEGER
            );
            INSERT INTO callstack VALUES (2, 'second'), (3, 'third');
            INSERT INTO trace_entry_0 VALUES
                (1, 4, 10, 10, 0, 160, 160, 1000, NULL),
                (2, 4, 20, 20, 0, 180, 180, 900, 2),
                (3, 4, 30, 30, 0, 175, 210, 900, 3);
            INSERT INTO block_0 VALUES
                (-1, 100, 100, NULL, 1, -1, -1),
                (-2, 200, 50, 50, 1, -1, 4),
                (1, 10, 10, NULL, 1, 1, -1),
                (2, 20, 20, 20, 1, 2, -1),
                (3, 30, 30, 30, 1, 3, -1);
            """)
    return db


@pytest.mark.parametrize("metric,event_id,active", [("active", 3, 210), ("allocated", 2, 180), ("reserved", 1, 160)])
@pytest.mark.parametrize("limit", [1, 2, 3, 4, -1])
@pytest.mark.parametrize("include_static", [True, False])
@pytest.mark.parametrize("json_output", [True, False])
def test_report_completeness_and_same_event_coverage(
    attribution_db: Path,
    metric: str,
    event_id: int,
    active: int,
    limit: int,
    include_static: bool,
    json_output: bool,
) -> None:
    """Below/equal/above cap preserve rows and flags, including special groups."""
    args = [
        "report",
        "peak-memory",
        str(attribution_db),
        "--device",
        "0",
        "--metric",
        metric,
        "--limit",
        str(limit),
        "--include-static" if include_static else "--exclude-static",
    ]
    params = {"event_id": event_id, "include_static": include_static, "min_size": 0, "top_n": limit}
    partial = limit >= 0 and event_id >= limit
    dynamic_sizes = sorted([10, 20, 30][:event_id], reverse=True)
    included = sum(dynamic_sizes if limit < 0 else dynamic_sizes[:limit])
    included += 150 if include_static else 0
    coverage = included * 100 / active
    result = CliRunner().invoke(app, args + (["--json"] if json_output else []))
    assert result.exit_code == 0, result.output
    if json_output:
        payload = json.loads(result.stdout)
        with SnapshotAnalyzer(attribution_db) as analyzer:
            query = analyzer.execute_query("active_memory_callstack_at_event", params=params, device_id=0)
        assert payload["callstack_groups"] == query["rows"]
        assert payload["has_more"] == query["has_more"] == partial
        assert payload["truncated"] == query["truncated"] == partial
        assert payload["total_is_exact"] == query["total_is_exact"] == (not partial)
        assert payload["effective_params"] == params
        assert payload["event_id"] == event_id
        assert payload["included_bytes"] == included
        assert payload["percent_denominator"] == "included_bytes"
        assert payload["active_bytes_at_event"] == active
        assert payload["coverage_percent"] == pytest.approx(coverage)
        for row in payload["callstack_groups"]:
            assert row["percent_of_active_blocks"] == pytest.approx(round(row["size_bytes"] * 100 / included, 4))
        if include_static:
            assert {row["category"] for row in payload["callstack_groups"]} == {
                "static",
                "preexisting_live_at_event",
                "dynamic_live_at_event",
            }
        if limit < 0 or limit >= event_id:
            missing = next(row for row in payload["callstack_groups"] if row["callstack"] == "[missing callstack]")
            assert missing["category"] == "dynamic_live_at_event"
            assert missing["requested_bytes"] is None
    else:
        assert f"Event ID: {event_id}" in result.stdout
        status = "partial / possibly incomplete" if partial else "complete for the effective filters"
        assert f"Attribution: {status}" in result.stdout
        assert f"include_static={include_static}, min_size=0, top_n={limit}" in result.stdout
        assert f"Percentage denominator: included_bytes={included} bytes" in result.stdout
        assert f"Active coverage at event {event_id}: {coverage:.4f}%" in result.stdout
        assert f"active={active} bytes" in result.stdout
        assert ("Increase --limit" in result.stdout) == partial


@pytest.mark.parametrize("bounded", [False, True])
@pytest.mark.parametrize("json_output", [True, False])
def test_default_report_has_no_attribution_for_null_active_peak(
    attribution_db: Path, bounded: bool, json_output: bool
) -> None:
    bounds = {"start_id": 2, "end_id": 3} if bounded else {}
    with closing(sqlite3.connect(attribution_db)) as conn, conn:
        where = " WHERE id BETWEEN 2 AND 3" if bounded else ""
        conn.execute(f"UPDATE trace_entry_0 SET active = NULL{where}")
    args = ["report", "peak-memory", str(attribution_db)]
    if bounded:
        args += ["--start-id", "2", "--end-id", "3"]
    result = CliRunner().invoke(app, args + (["--json"] if json_output else []))
    assert result.exit_code == 0, result.output
    if json_output:
        payload = json.loads(result.stdout)
        with SnapshotAnalyzer(attribution_db) as analyzer:
            peak = analyzer.execute_query("memory_peak", params=bounds)
        assert payload["peak"] == peak["rows"][0]
        assert payload["metric"] == "active"
        assert payload["event_id"] is None and payload["allocator_gap"] is None
        assert payload["callstack_groups"] == []
        assert payload["included_bytes"] == 0
        assert payload["active_bytes_at_event"] is None
        assert payload["coverage_percent"] is None
        assert payload["effective_params"]["event_id"] is None
        assert payload["total_is_exact"] is True
        assert payload["has_more"] is False and payload["truncated"] is False
    else:
        assert "Attribution: unavailable (no peak event)" in result.stdout
        assert "No active memory callstack groups found" in result.stdout


@pytest.mark.parametrize("state", ["empty", "null", "zero"])
@pytest.mark.parametrize("json_output", [True, False])
def test_report_unknown_coverage(attribution_db: Path, state: str, json_output: bool) -> None:
    with closing(sqlite3.connect(attribution_db)) as conn, conn:
        if state == "empty":
            conn.execute("DELETE FROM trace_entry_0")
        else:
            conn.execute("UPDATE trace_entry_0 SET active = ?", (None if state == "null" else 0,))
            conn.execute("UPDATE block_0 SET size = 0")
    # Select reserved so a NULL active counter still has a selected event.
    args = ["report", "peak-memory", str(attribution_db), "--metric", "reserved"]
    result = CliRunner().invoke(app, args + (["--json"] if json_output else []))
    assert result.exit_code == 0, result.output
    if json_output:
        payload = json.loads(result.stdout)
        assert payload["coverage_percent"] is None
        assert payload["included_bytes"] == 0
        assert payload["active_bytes_at_event"] == (0 if state == "zero" else None)
        assert payload["has_more"] is False
        assert payload["truncated"] is False
        assert payload["total_is_exact"] is True
        if state == "empty":
            assert payload["event_id"] is None
            assert payload["callstack_groups"] == []
        else:
            assert payload["event_id"] == 1
            assert all(row["percent_of_active_blocks"] is None for row in payload["callstack_groups"])
    else:
        assert "unknown (included=0 bytes" in result.stdout
        assert "Percentage denominator: included_bytes=0 bytes" in result.stdout
        if state == "empty":
            assert "Attribution: unavailable (no peak event)" in result.stdout
            assert "No active memory callstack groups found" in result.stdout
