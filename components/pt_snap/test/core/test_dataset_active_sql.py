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

"""Full-scope active reduction and bounded text/detail materialization."""

import json
import sqlite3
import time
from contextlib import closing

import pytest

from benchmarks.active_at_event_capacity import build_case, run_case
from pt_snap_cli.core.analysis.query_service import QueryService
from pt_snap_cli.core.common.errors import QueryExecutionError, QueryTimeoutError
from pt_snap_cli.core.dataset.dataset_sources import QueryBudget
from pt_snap_cli.core.dataset.lifecycle.dataset_lifecycle_connection import _AttachedSources
from pt_snap_cli.core.dataset.query import dataset_active_sql
from test.core.test_dataset_attribution import case
from test.test_dataset_focus import hashes


def normalized(result):
    value = dict(result.__dict__)
    value["scope"] = dict(value["scope"])
    value["scope"]["source_coverage"] = {
        k: v for k, v in value["scope"]["source_coverage"].items() if k != "source_queries"
    }
    return value


@pytest.mark.parametrize("layout", ["v1", "v2"])
def test_small_capacity_gate_checks_exact_total_native_local_ids_and_future_frees(tmp_path, layout):
    receipt = run_case(tmp_path / layout, 1000, 200, 32, layout, 10)
    assert receipt["standalone_differential"] == "passed"
    assert receipt["source_unchanged"]


@pytest.mark.parametrize(
    "template,params,cap,exact",
    [
        ("active_blocks_at_event", {"limit": 0}, None, False),
        ("active_blocks_at_event", {"limit": -1}, 2, True),
        (
            "active_blocks_at_event",
            {"limit": 2, "offset": 1, "order_by": "freeEventId", "order_dir": "ASC"},
            1,
            False,
        ),
        ("active_blocks_at_event", {"limit": 2, "offset": 100}, None, True),
        ("active_memory_callstack_at_event", {"top_n": -1}, None, True),
        ("active_memory_callstack_at_event", {"top_n": 0}, None, False),
        ("active_memory_callstack_at_event", {"top_n": 1}, 1, True),
        ("active_memory_callstack_at_event", {"top_n": 5}, None, False),
        ("active_memory_callstack_at_event", {"min_size": 999}, None, True),
        ("active_memory_callstack_at_event", {"include_static": False}, None, False),
    ],
)
def test_sql_matches_full_source_path_including_identity_coverage_and_completeness(
    tmp_path, monkeypatch, template, params, cap, exact
):
    root = case(tmp_path, devices=(0,))
    params = (
        {"event_id": 8, "stack_bytes": 0, **params}
        if template != "active_blocks_at_event"
        else {"event_id": 8, **params}
    )
    before = hashes(root)
    with closing(QueryService()) as service:
        sql = service.execute_query(template, params, db_path=root, max_rows=cap, exact_total=exact)
        monkeypatch.setattr(dataset_active_sql, "_attachment_limit", lambda: 0)
        raw = service.execute_query(template, params, db_path=root, max_rows=cap, exact_total=exact)
    assert normalized(sql) == normalized(raw)
    assert hashes(root) == before


@pytest.mark.parametrize("template", ["active_blocks_at_event", "active_memory_callstack_at_event"])
def test_missing_allocation_and_future_free_outside_page_keep_full_coverage(tmp_path, template):
    root, _ = build_case(tmp_path / "case", 1000, 200)
    with closing(sqlite3.connect(root / "device_0/slice_00000.db")) as connection, connection:
        connection.execute("UPDATE trace_entry_0 SET action=5 WHERE id=0")
    with closing(sqlite3.connect(root / "device_0/slice_00002.db")) as connection, connection:
        connection.execute("UPDATE trace_entry_0 SET action=5 WHERE id=2000")
    before = hashes(root)
    params = {"event_id": 1999, "min_size": 0}
    params.update({"limit": 1} if template == "active_blocks_at_event" else {"top_n": 1})
    with closing(QueryService()) as service:
        result = service.execute_query(template, params, db_path=root, max_rows=1, exact_total=True)
    coverage = result.scope["source_coverage"]
    assert coverage["active_blocks"] == coverage["free_references"] == 200
    assert coverage["allocation_events_resolved"] == coverage["free_events_resolved"] == 199
    assert not coverage["allocation_source_complete"]
    assert result.returned == 1
    if template == "active_blocks_at_event":
        assert result.rows[0]["id"] != 0
        assert result.rows[0]["free_source_status"] == "resolved"
    assert hashes(root) == before


def test_zero_frame_coverage_still_uses_ordered_fallback(tmp_path, monkeypatch):
    root = case(tmp_path, devices=(0,))
    manifest = root / "manifest.json"
    data = json.loads(manifest.read_text())
    data["extensions"] = {"ptSnapOrderedFrames": {"version": 1}}
    manifest.write_text(json.dumps(data))
    monkeypatch.setattr(dataset_active_sql, "_required_slices", lambda *args: pytest.fail("frame fallback"))
    with closing(QueryService()) as service:
        result = service.execute_query("active_memory_callstack_at_event", {"event_id": 8}, db_path=root)
    assert not result.scope["source_coverage"]["ordered_frames_complete"]


@pytest.mark.parametrize("fault", ["timeout", "work_rows", "work_bytes"])
def test_attached_reduction_failure_closes_connection_and_reusable_service(tmp_path, monkeypatch, fault):
    root, _ = build_case(tmp_path / "case", 1000, 200)
    before = hashes(root)
    owners = []
    original = _AttachedSources.read
    budget = QueryBudget(None, time.monotonic())

    def fail(database, sql, values=None):
        owners.append(database)
        if "FROM included ORDER" in sql:
            if fault == "timeout":
                database.sources.budget.timeout_s = 0.0001
                database.sources.budget.started = time.monotonic() - 1
            elif fault == "work_rows":
                database.sources.budget.max_work_rows = database.sources.budget.work_rows
            else:
                database.sources.budget.max_work_bytes = database.sources.budget.work_bytes
        return original(database, sql, values)

    with closing(QueryService()) as service:
        with monkeypatch.context() as patch:
            patch.setattr(_AttachedSources, "read", fail)
            with pytest.raises(QueryTimeoutError if fault == "timeout" else QueryExecutionError):
                service.execute_query(
                    "active_memory_callstack_at_event",
                    {"event_id": 1999},
                    db_path=root,
                    _budget=budget,
                )
        assert owners
        for owner in owners:
            with pytest.raises(sqlite3.ProgrammingError, match="closed"):
                owner.connection.execute("SELECT 1")
        result = service.execute_query("active_memory_callstack_at_event", {"event_id": 1999}, db_path=root)
        assert result.rows and result.scope["source_coverage"]["active_blocks"] == 200
    assert hashes(root) == before


@pytest.mark.slow
@pytest.mark.parametrize("layout", ["v1", "v2"])
def test_default_export_capacity_with_two_hundred_thousand_active_blocks(tmp_path, layout):
    receipt = run_case(tmp_path / layout, 500_000, 200_000, 32, layout, 120)
    assert receipt["events"] == 1_500_000 and receipt["active"] == 200_000
    assert receipt["unbounded_output_rejected"]
    assert [query["returned"] for query in receipt["queries"]] == [20, 20]


@pytest.mark.parametrize("template", ["active_blocks_at_event", "active_memory_callstack_at_event"])
def test_coverage_totals_above_int64_remain_exact_for_bounded_results(tmp_path, monkeypatch, template):
    from test.core.test_dataset_realistic import rounding_case

    root, single = rounding_case(tmp_path, (1, 1))
    # Each group fits int64; the full-scope coverage sum does not. The low bit
    # also detects a lossy floating-point TOTAL() replacement.
    for path in [single, *root.glob("device_0/*.db")]:
        with closing(sqlite3.connect(path)) as connection, connection:
            connection.execute("UPDATE block_0 SET size=?,requestedSize=? WHERE id=0", (2**62 + 1, 2**62 + 1))
            connection.execute("UPDATE block_0 SET size=?,requestedSize=? WHERE id=1", (2**62, 2**62))
    params = {"event_id": 1}
    params.update({"limit": 1} if template == "active_blocks_at_event" else {"top_n": 1})
    with closing(QueryService()) as service:
        result = service.execute_query(template, params, db_path=root)
        monkeypatch.setattr(dataset_active_sql, "_attachment_limit", lambda: 0)
        raw = service.execute_query(template, params, db_path=root)
        expected = service.execute_query(template, params, db_path=single)
    assert normalized(result) == normalized(raw)
    assert result.scope["source_coverage"]["active_bytes"] == 2**63 + 1
    fields = set(expected.rows[0])
    assert [{key: row[key] for key in fields} for row in result.rows] == expected.rows
