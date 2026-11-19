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

"""Operation-local reuse preserves real read accounting and source identity."""

import json
import sqlite3
import time
from contextlib import closing

import pytest

from pt_snap_cli.core.analysis.query_service import QueryService
from pt_snap_cli.core.cache.context_cache import ContextCache
from pt_snap_cli.core.common.errors import QueryExecutionError
from pt_snap_cli.core.dataset.dataset_resolver import DatasetResolver
from pt_snap_cli.core.dataset.dataset_sources import DatasetSourceResolver, QueryBudget
from test.test_dataset_focus import make_dataset


def dataset(tmp_path, count, stack="shared", blocks=False):
    root = make_dataset(tmp_path / "dataset", devices=(0,), slices=1)
    manifest = json.loads((root / "manifest.json").read_text())
    manifest["eventsPerSlice"] = count
    manifest["devices"]["0"]["eventCount"] = count
    manifest["devices"]["0"]["slices"][0]["endEventId"] = count - 1
    (root / "manifest.json").write_text(json.dumps(manifest))
    with closing(sqlite3.connect(root / "device_0/slice_00000.db")) as conn, conn:
        conn.execute("DELETE FROM trace_entry_0")
        conn.executemany(
            "INSERT INTO trace_entry_0 VALUES (?,4,?,8,0,8,8,16,?)",
            ((i, i * 8, stack) for i in range(count)),
        )
        if blocks:
            conn.executemany(
                "INSERT INTO block_0 VALUES (?,?,8,8,1,?,-1)",
                ((i, i * 8, i) for i in range(count)),
            )
    return root


@pytest.mark.parametrize("template", ["callstack_analysis", "event"])
def test_sixty_thousand_events_are_not_read_twice(tmp_path, template):
    root = dataset(tmp_path, 60_000)
    budget = QueryBudget(None, time.monotonic())
    service = QueryService()
    try:
        result = service.execute_query(
            template,
            params=(
                {"min_count": 1}
                if template == "callstack_analysis"
                else {
                    "order_by": "callstack",
                    "limit": 1,
                }
            ),
            db_path=root,
            _budget=budget,
        )
    finally:
        service.close()
    assert result.returned == 1
    assert budget.work_rows <= 60_001
    if template == "callstack_analysis":
        assert result.rows[0]["alloc_count"] == 60_000


def test_target_and_distinct_events_reuse_only_identical_sources(tmp_path):
    root = dataset(tmp_path, 4)
    resolved = DatasetResolver().inspect(root)
    budget = QueryBudget(None, time.monotonic())
    with closing(ContextCache()) as cache:
        sources = DatasetSourceResolver(resolved, 0, cache, budget)
        sources.target(3)
        first = sources.events([0, 1, 2, 3])
        reads, work = sources.query_count, budget.work_rows
        repeated = sources.events([3, 2, 1, 0, 3])
        assert sources.query_count == reads
        assert budget.work_rows == work == 4
        assert repeated[3] is first[3]
        assert first[0].event["id"] != first[1].event["id"]
        assert first[0].stack_id == first[1].stack_id


@pytest.mark.parametrize("count", [49_999, 50_000])
def test_active_reduction_does_not_materialize_blocks_and_allocation_events(tmp_path, count):
    root = dataset(tmp_path, count, blocks=True)
    budget = QueryBudget(None, time.monotonic())
    with closing(QueryService()) as service:
        result = service.execute_query(
            "active_memory_callstack_at_event",
            params={"event_id": count - 1},
            db_path=root,
            _budget=budget,
        )
    assert result.returned == 1
    assert result.rows[0]["block_count"] == count
    # Target, full coverage summary, group count, reduced group and enriched output.
    assert budget.work_rows == 5


def test_shared_long_text_reduction_is_small_but_full_sources_remain_budgeted(tmp_path):
    root = dataset(tmp_path, 5_000, stack="x" * 16_384, blocks=True)
    budget = QueryBudget(None, time.monotonic())
    with closing(QueryService()) as service:
        result = service.execute_query(
            "active_memory_callstack_at_event",
            params={"event_id": 4_999},
            db_path=root,
            _budget=budget,
        )
        assert result.rows[0]["block_count"] == 5_000
        assert budget.work_rows == 5 and budget.work_bytes < 100_000
        full = QueryBudget(None, time.monotonic())
        with pytest.raises(QueryExecutionError, match="work budget exceeded"):
            service.execute_query(
                "active_blocks_at_event",
                params={"event_id": 4_999, "limit": -1},
                db_path=root,
                _budget=full,
            )
        assert full.work_rows < full.max_work_rows
        assert full.work_bytes > full.max_work_bytes


def test_fallback_still_charges_distinct_blocks_and_sources(tmp_path, monkeypatch):
    from pt_snap_cli.core.dataset.query import dataset_attribution

    monkeypatch.setattr(dataset_attribution, "reduce_active", lambda *args: None)
    root = dataset(tmp_path, 100, blocks=True)
    with closing(QueryService()) as service:
        budget = QueryBudget(None, time.monotonic(), max_work_rows=201)
        result = service.execute_query(
            "active_memory_callstack_at_event", {"event_id": 99}, db_path=root, _budget=budget
        )
        assert result.returned == 1 and budget.work_rows == 201
        with pytest.raises(QueryExecutionError, match="work budget exceeded"):
            service.execute_query(
                "active_memory_callstack_at_event",
                {"event_id": 99},
                db_path=root,
                _budget=QueryBudget(None, time.monotonic(), max_work_rows=200),
            )


def test_id_sorted_page_does_not_materialize_unneeded_stack_text(tmp_path):
    root = dataset(tmp_path, 10_000, stack="x" * 8192)
    budget = QueryBudget(None, time.monotonic())
    with closing(QueryService()) as service:
        result = service.execute_query(
            "event",
            params={"order_by": "id", "limit": 1},
            db_path=root,
            _budget=budget,
        )
    assert result.returned == 1
    assert budget.work_bytes < 2_000_000


def framed_dataset(tmp_path, count):
    root = dataset(tmp_path, count)
    manifest = json.loads((root / "manifest.json").read_text())
    manifest["extensions"] = {"ptSnapOrderedFrames": {"version": 1}}
    (root / "manifest.json").write_text(json.dumps(manifest))
    with closing(sqlite3.connect(root / "device_0/slice_00000.db")) as conn, conn:
        conn.executescript(
            "CREATE TABLE pt_snap_frame_coverage (eventId INTEGER PRIMARY KEY,frameCount INTEGER);"
            "CREATE TABLE pt_snap_frame (eventId INTEGER,frameIndex INTEGER,frameJson TEXT,"
            "PRIMARY KEY(eventId,frameIndex));"
        )
        conn.executemany("INSERT INTO pt_snap_frame_coverage VALUES (?,1)", ((i,) for i in range(count)))
        conn.executemany("INSERT INTO pt_snap_frame VALUES (?,0,?)", ((i, '{"name":"f"}') for i in range(count)))
    return root


def test_frame_schema_is_checked_once_across_source_batches(tmp_path, monkeypatch):
    root = framed_dataset(tmp_path, 600)
    resolved = DatasetResolver().inspect(root)
    queries = []
    original = DatasetSourceResolver.read

    def observed(self, path, sql, values=None):
        queries.append(sql)
        return original(self, path, sql, values)

    monkeypatch.setattr(DatasetSourceResolver, "read", observed)
    with closing(ContextCache()) as cache:
        sources = DatasetSourceResolver(resolved, 0, cache, QueryBudget(None, time.monotonic()))
        first = sources.events(range(512))
        second = sources.events(range(512, 600))
        assert all(source.frames == [{"name": "f"}] for source in [*first.values(), *second.values()])
    assert sum("PRAGMA table_info" in sql for sql in queries) == 2
    assert sum("sqlite_master" in sql for sql in queries) == 2


def test_callstack_sort_loads_frames_only_for_returned_page(tmp_path):
    root = framed_dataset(tmp_path, 600)
    budget = QueryBudget(None, time.monotonic())
    with closing(QueryService()) as service:
        result = service.execute_query(
            "event", params={"order_by": "callstack", "limit": 1}, db_path=root, _budget=budget
        )
    assert result.rows[0]["frames"] == [{"name": "f"}]
    # SQL pushdown may reduce trace work; only one returned frame is hydrated.
    assert budget.work_rows <= 610


@pytest.mark.parametrize("invalid", [True, 1.0])
def test_cached_event_lookup_preserves_exact_integer_validation(tmp_path, invalid):
    root = dataset(tmp_path, 4)
    resolved = DatasetResolver().inspect(root)
    with closing(ContextCache()) as cache:
        sources = DatasetSourceResolver(resolved, 0, cache, QueryBudget(None, time.monotonic()))
        assert sources.events([invalid]) == {}
        expected = sources.events([1])
        reads = sources.query_count
        assert sources.events([invalid]) == {}
        assert sources.events([1]) == expected
        assert sources.query_count == reads


@pytest.mark.parametrize("warm_cache", [False, True])
def test_preloaded_rows_reject_wrong_shard_even_when_cached(tmp_path, warm_cache):
    root = make_dataset(tmp_path / "dataset", devices=(0,), slices=2)
    resolved = DatasetResolver().inspect(root)
    with closing(ContextCache()) as cache:
        sources = DatasetSourceResolver(resolved, 0, cache, QueryBudget(None, time.monotonic()))
        if warm_cache:
            assert 0 in sources.events([0])
        with pytest.raises(QueryExecutionError, match="does not belong"):
            sources.events_from_rows(sources.device.slices[1], [{"id": 0}])
