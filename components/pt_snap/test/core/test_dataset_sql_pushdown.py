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

"""Bounded global SQL reductions preserve full-scope evidence and lifecycle proof."""

import dataclasses
import hashlib
import json
import sqlite3
import time
from contextlib import closing

import pytest

from pt_snap_cli.core.analysis.query_service import QueryService
from pt_snap_cli.core.cache.context_cache import ContextCache
from pt_snap_cli.core.common.errors import QueryExecutionError, QueryTimeoutError
from pt_snap_cli.core.dataset.dataset_resolver import DatasetResolver
from pt_snap_cli.core.dataset.dataset_sources import DatasetSourceResolver, QueryBudget
from pt_snap_cli.core.dataset.lifecycle import dataset_lifecycle_sql
from pt_snap_cli.core.dataset.query.dataset_global import global_query
from pt_snap_cli.core.importing.import_service import ImportService
from pt_snap_cli.query.registry import get_query
from test.core.test_dataset_attribution import case
from test.core.test_dataset_import import source_options
from test.test_dataset_focus import make_dataset


def large_dataset(tmp_path, per_shard=60_000):
    root = make_dataset(tmp_path / "large", devices=(0,), slices=2)
    manifest_path = root / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["eventsPerSlice"] = per_shard
    manifest["devices"]["0"]["eventCount"] = 2 * per_shard
    for index, record in enumerate(manifest["devices"]["0"]["slices"]):
        low, high = index * per_shard, (index + 1) * per_shard - 1
        record.update(startEventId=low, endEventId=high)
        with closing(sqlite3.connect(root / record["file"])) as conn, conn:
            conn.execute("DELETE FROM trace_entry_0")
            conn.executemany(
                "INSERT INTO trace_entry_0 VALUES (?,4,?,8,0,?,?,?,'shared')",
                ((i, i * 8, i * 8, i * 8, i * 16) for i in range(low, high + 1)),
            )
            # Carry-in live blocks are repeated; future allocations never appear.
            conn.executemany(
                "INSERT INTO block_0 VALUES (?,?,8,8,1,?,-1)",
                ((i, i * 8, i) for i in range(high + 1)),
            )
    manifest_path.write_text(json.dumps(manifest))
    return root


@pytest.fixture(scope="module")
def large_root(tmp_path_factory):
    return large_dataset(tmp_path_factory.mktemp("sql-pushdown"))


@pytest.mark.parametrize(
    "template",
    ["memory_peak", "event", "allocation", "callstack_analysis", "block", "leak_detection"],
)
def test_large_real_scope_fetches_only_aggregates_and_bounded_candidates(large_root, template):
    budget = QueryBudget(None, time.monotonic(), max_work_rows=64)
    with closing(QueryService()) as service:
        result = service.execute_query(template, db_path=large_root, max_rows=5, exact_total=True, _budget=budget)
    expected_total = 1 if template in ("memory_peak", "callstack_analysis") else 120_000
    assert result.total == expected_total
    assert result.returned == min(expected_total, 5)
    assert result.has_more == (expected_total > 5)
    assert budget.work_rows <= 64
    if template in ("block", "leak_detection"):
        coverage = result.scope["source_coverage"]
        assert coverage["lifecycles"] == 120_000
        assert coverage["allocation_events_resolved"] == 120_000
    if template == "callstack_analysis":
        assert result.rows[0]["alloc_count"] == 120_000
        assert result.rows[0]["total_size"] == 960_000


def test_unbounded_output_still_exhausts_real_fetched_work_budget(large_root):
    budget = QueryBudget(None, time.monotonic())
    with closing(QueryService()) as service:
        with pytest.raises(QueryExecutionError, match="work budget"):
            service.execute_query("allocation", db_path=large_root, _budget=budget)
    assert budget.work_rows > budget.max_work_rows


def test_actual_range_precedes_filters_and_empty_window_is_exact(tmp_path):
    root = make_dataset(tmp_path / "range", devices=(0,), slices=3)
    with closing(QueryService()) as service:
        result = service.execute_query(
            "event",
            {"min_id": 1, "max_id": 4, "action": 99, "limit": 0},
            db_path=root,
            exact_total=True,
        )
    assert result.rows == [] and result.total == 0 and not result.has_more
    assert result.scope["actual_range"] == {
        "first_event_id": 1,
        "last_event_id": 4,
        "real_event_count": 4,
    }


def run_resolved(resolved, template, params=None, budget=None, slice_index=None, exact_total=True):
    config = get_query(template)
    with closing(ContextCache()) as cache:
        source = DatasetSourceResolver(resolved, 0, cache, budget or QueryBudget(None, time.monotonic()))
        return global_query(
            source,
            template,
            config.validate_params(params or {}),
            5,
            exact_total,
            slice_index,
            config.semantics_version,
        )


@pytest.mark.parametrize("template", ["block", "leak_detection", "freed_block_lifetime"])
def test_attachment_ceiling_fallback_preserves_lifecycle_results(tmp_path, monkeypatch, template):
    root = case(tmp_path, devices=(0,))
    resolved = DatasetResolver().inspect(root)
    pushed = run_resolved(resolved, template)
    monkeypatch.setattr(dataset_lifecycle_sql, "_attachment_limit", lambda: 1)
    fallback = run_resolved(resolved, template)
    assert pushed.rows == fallback.rows
    assert pushed.total == fallback.total and pushed.has_more == fallback.has_more
    first, second = pushed.scope["source_coverage"], fallback.scope["source_coverage"]
    assert {k: v for k, v in first.items() if k != "source_queries"} == {
        k: v for k, v in second.items() if k != "source_queries"
    }


@pytest.mark.parametrize("template", ["block", "freed_block_lifetime"])
@pytest.mark.parametrize("slice_index", [0, 3, 7])
def test_slice_scope_pushdown_matches_fallback(tmp_path, monkeypatch, template, slice_index):
    resolved = DatasetResolver().inspect(case(tmp_path, devices=(0,)))
    pushed = run_resolved(resolved, template, slice_index=slice_index)
    monkeypatch.setattr(dataset_lifecycle_sql, "_attachment_limit", lambda: 0)
    fallback = run_resolved(resolved, template, slice_index=slice_index)
    assert pushed.rows == fallback.rows
    assert pushed.total == fallback.total
    assert pushed.has_more == fallback.has_more
    first, second = pushed.scope["source_coverage"], fallback.scope["source_coverage"]
    assert {k: v for k, v in first.items() if k != "source_queries"} == {
        k: v for k, v in second.items() if k != "source_queries"
    }
    assert pushed.scope["slice_indices"] == [slice_index]


@pytest.mark.parametrize("attachment_limit", [0, 10])
def test_slice_leak_scope_is_rejected_before_pushdown_or_fallback(tmp_path, monkeypatch, attachment_limit):
    root = make_dataset(tmp_path / "slice-leak", devices=(0,))
    monkeypatch.setattr(dataset_lifecycle_sql, "_attachment_limit", lambda: attachment_limit)
    with closing(QueryService()) as service:
        with pytest.raises(QueryExecutionError, match="requires terminal dataset scope"):
            service.execute_query("leak_detection", db_path=root, slice_index=0)


def test_slice_attaches_only_observations_and_referenced_proof_owners(tmp_path, monkeypatch):
    root = make_dataset(tmp_path / "many-slices", devices=(0,), slices=12)
    with closing(sqlite3.connect(root / "device_0/slice_00011.db")) as conn, conn:
        conn.executemany(
            "INSERT INTO block_0 VALUES (?,?,?,?,?,?,?)",
            [(0, 100, 8, 8, -1, 0, 2), (-1, 200, 8, 8, 1, -1, -1), (1, 300, 8, 8, 1, 1, -1)],
        )
    with closing(sqlite3.connect(root / "device_0/slice_00000.db")) as conn, conn:
        conn.execute("UPDATE trace_entry_0 SET action=5 WHERE id=1")
    with closing(sqlite3.connect(root / "device_0/slice_00001.db")) as conn, conn:
        conn.execute("UPDATE trace_entry_0 SET action=6 WHERE id=2")
    resolved = DatasetResolver().inspect(root)
    attached = []
    original = dataset_lifecycle_sql._AttachedSources.__enter__

    def observed(database):
        result = original(database)
        attached.append([row[1] for row in database.connection.execute("PRAGMA database_list") if row[1] != "main"])
        return result

    monkeypatch.setattr(dataset_lifecycle_sql._AttachedSources, "__enter__", observed)
    monkeypatch.setattr(dataset_lifecycle_sql, "_attachment_limit", lambda: 3)
    pushed = run_resolved(resolved, "block", slice_index=11)
    assert attached == [["s0", "s1", "s11"]]
    row = next(row for row in pushed.rows if row["id"] == 0)
    assert row["allocation_source"]["slice_index"] == 0
    assert row["free_source"]["slice_index"] == 1
    monkeypatch.setattr(dataset_lifecycle_sql, "_attachment_limit", lambda: 2)
    fallback = run_resolved(resolved, "block", slice_index=11)
    assert attached == [["s0", "s1", "s11"]]
    assert pushed.rows == fallback.rows
    assert pushed.total == fallback.total == 3


def test_empty_slice_does_not_attach_unreferenced_members(tmp_path, monkeypatch):
    root = make_dataset(tmp_path / "empty-slice", devices=(0,), slices=12)
    resolved = DatasetResolver().inspect(root)
    monkeypatch.setattr(dataset_lifecycle_sql, "_attachment_limit", lambda: 1)
    with closing(ContextCache()) as cache:
        sources = DatasetSourceResolver(resolved, 0, cache, QueryBudget(None, time.monotonic()))
        assert dataset_lifecycle_sql._required_slices(sources, [sources.device.slices[11]], 1) == [
            sources.device.slices[11]
        ]
    assert run_resolved(resolved, "block", slice_index=11).rows == []


@pytest.mark.parametrize("template", ["event", "block", "leak_detection"])
@pytest.mark.parametrize("value", [-(2**63), 2**63 - 1])
def test_int64_filter_endpoints_are_accepted(tmp_path, template, value):
    root = case(tmp_path, devices=(0,))
    with closing(QueryService()) as service:
        result = service.execute_query(
            template,
            {"min_allocated" if template == "event" else "min_size": value},
            db_path=root,
            max_rows=1,
        )
    assert result.returned == (1 if value < 0 else 0)


@pytest.mark.parametrize("template", ["event", "block", "leak_detection"])
@pytest.mark.parametrize("value", [-(2**63) - 1, 2**63])
def test_out_of_int64_filters_raise_domain_errors(tmp_path, template, value):
    root = make_dataset(tmp_path / "overflow", devices=(0,))
    with closing(QueryService()) as service:
        with pytest.raises(QueryExecutionError):
            service.execute_query(
                template,
                {"min_allocated" if template == "event" else "min_size": value},
                db_path=root,
            )


@pytest.mark.parametrize("template", ["event", "block"])
@pytest.mark.parametrize("offset", [2**63 - 2, 2**63 - 1, 2**63])
def test_candidate_limit_int64_boundary(tmp_path, template, offset):
    root = make_dataset(tmp_path / "offset", devices=(0,))
    with closing(QueryService()) as service:
        if offset + 1 <= 2**63 - 1:
            result = service.execute_query(template, {"offset": offset, "limit": 1}, db_path=root)
            assert result.rows == []
        else:
            with pytest.raises(QueryExecutionError):
                service.execute_query(template, {"offset": offset, "limit": 1}, db_path=root)


def last_observation(root, block_id):
    for path in sorted(root.glob("device_0/*.db"), reverse=True):
        with closing(sqlite3.connect(path)) as conn:
            if conn.execute("SELECT 1 FROM block_0 WHERE id=?", [block_id]).fetchone():
                return path
    raise AssertionError(f"No observation for block {block_id}")


def test_lifecycle_conflicts_are_checked_before_filters_and_page(tmp_path):
    root = case(tmp_path, devices=(0,))
    resolved = DatasetResolver().inspect(root)
    with closing(sqlite3.connect(last_observation(root, 0))) as conn, conn:
        assert conn.execute("UPDATE block_0 SET size=size+1 WHERE id=0").rowcount == 1
    with pytest.raises(QueryExecutionError, match="Conflicting observations"):
        run_resolved(resolved, "block", {"id": 7})


def test_latest_state_and_prior_proved_completion_survive_sql_reduction(tmp_path, monkeypatch):
    root = case(tmp_path, devices=(0,))
    resolved = DatasetResolver().inspect(root)
    with closing(sqlite3.connect(last_observation(root, 0))) as conn, conn:
        assert conn.execute("UPDATE block_0 SET state=0,freeEventId=-1 WHERE id=0").rowcount == 1
    params = {"id": 0}
    pushed = run_resolved(resolved, "block", params)
    monkeypatch.setattr(dataset_lifecycle_sql, "_attachment_limit", lambda: 1)
    fallback = run_resolved(resolved, "block", params)
    assert pushed.rows == fallback.rows
    assert pushed.rows[0]["state"] == 0
    assert pushed.rows[0]["freeEventId"] == 10
    assert pushed.rows[0]["free_source"]["event"]["action"] == 6
    assert not pushed.rows[0]["terminal_survivor"]


def test_attached_members_are_read_only_and_connection_is_closed(tmp_path):
    resolved = DatasetResolver().inspect(make_dataset(tmp_path / "readonly", devices=(0,)))
    with closing(ContextCache()) as cache:
        source = DatasetSourceResolver(resolved, 0, cache, QueryBudget(None, time.monotonic()))
        with dataset_lifecycle_sql._AttachedSources(source) as attached:
            with pytest.raises(sqlite3.OperationalError, match="readonly"):
                attached.connection.execute("DELETE FROM s0.trace_entry_0")
        with pytest.raises(sqlite3.ProgrammingError, match="closed"):
            attached.connection.execute("SELECT 1")


def test_attached_query_timeout_clears_handler_and_closes_connection(tmp_path):
    resolved = DatasetResolver().inspect(make_dataset(tmp_path / "timeout", devices=(0,)))
    with closing(ContextCache()) as cache:
        source = DatasetSourceResolver(resolved, 0, cache, QueryBudget(0.05, time.monotonic()))
        with dataset_lifecycle_sql._AttachedSources(source) as attached:
            with pytest.raises(QueryTimeoutError):
                attached.read(
                    "WITH RECURSIVE n(x) AS (SELECT 1 UNION ALL SELECT x+1 FROM n "
                    "WHERE x<100000000) SELECT SUM(x) FROM n"
                )
            assert attached.connection.execute("SELECT 1").fetchone()[0] == 1
        with pytest.raises(sqlite3.ProgrammingError, match="closed"):
            attached.connection.execute("SELECT 1")


def test_callstack_order_reuses_already_fetched_candidate_events(tmp_path, monkeypatch):
    root = make_dataset(tmp_path / "reuse", devices=(0,), slices=3)
    queries = []
    original = DatasetSourceResolver.read

    def observed(self, path, sql, values=None):
        queries.append(sql)
        return original(self, path, sql, values)

    monkeypatch.setattr(DatasetSourceResolver, "read", observed)
    with closing(QueryService()) as service:
        result = service.execute_query("event", {"order_by": "callstack", "limit": 1}, db_path=root)
    assert result.returned == 1
    assert sum("ORDER BY" in sql and "trace_entry" in sql for sql in queries) == 3
    assert not any("WHERE t.id IN" in sql for sql in queries)


def test_attaching_locked_member_respects_remaining_deadline(tmp_path, monkeypatch):
    root = make_dataset(tmp_path / "locked", devices=(0,), slices=1)
    resolved = DatasetResolver().inspect(root)
    # Exercise the native non-immutable opening mode with an actual SQLite lock.
    monkeypatch.setattr(type(resolved), "callstack_layout", property(lambda self: "v2"))
    with closing(sqlite3.connect(root / "device_0/slice_00000.db")) as locked:
        locked.execute("BEGIN EXCLUSIVE")
        with closing(ContextCache()) as cache:
            start = time.monotonic()
            source = DatasetSourceResolver(resolved, 0, cache, QueryBudget(0.05, start))
            attached = dataset_lifecycle_sql._AttachedSources(source)
            with pytest.raises(QueryTimeoutError):
                with attached:
                    attached.read("SELECT COUNT(*) FROM s0.trace_entry_0")
            assert time.monotonic() - start < 0.5
            with pytest.raises(sqlite3.ProgrammingError, match="closed"):
                attached.connection.execute("SELECT 1")
        locked.rollback()


@pytest.mark.parametrize("layout", ["v1", "v2"])
@pytest.mark.parametrize("collation,texts", [("NOCASE", ("a", "A")), ("RTRIM", ("a ", "a"))])
def test_global_text_identity_and_candidates_ignore_source_collation(tmp_path, layout, collation, texts):
    if layout == "v1":
        root = make_dataset(tmp_path / "collated", devices=(0,), slices=1)
    else:
        root = (
            ImportService()
            .import_snapshot(dataclasses.replace(source_options(tmp_path), events_per_slice=99, set_focus=False))
            .db_path
        )
    manifest_path = root / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    item = manifest["devices"]["0"]["slices"][0]
    member = root / item["file"]
    with closing(sqlite3.connect(member)) as conn, conn:
        ids = [r[0] for r in conn.execute("SELECT id FROM trace_entry_0 WHERE id>=0 ORDER BY id")]
        if layout == "v1":
            original = conn.execute("SELECT sql FROM sqlite_master WHERE name='trace_entry_0'").fetchone()[0]
            conn.execute("ALTER TABLE trace_entry_0 RENAME TO original_trace")
            conn.execute(original.replace("callstack TEXT", f"callstack TEXT COLLATE {collation}"))
            conn.execute("INSERT INTO trace_entry_0 SELECT * FROM original_trace")
            conn.execute("DROP TABLE original_trace")
            conn.execute("UPDATE trace_entry_0 SET callstack=?", [texts[0]])
            conn.execute("UPDATE trace_entry_0 SET callstack=? WHERE id=?", [texts[1], ids[1]])
        else:
            conn.execute("DROP TABLE callstack")
            conn.execute(f"CREATE TABLE callstack (id INTEGER PRIMARY KEY,callstack TEXT COLLATE {collation})")
            conn.executemany("INSERT INTO callstack VALUES (?,?)", enumerate(texts))
            conn.execute("UPDATE trace_entry_0 SET callstackId=0")
            conn.execute("UPDATE trace_entry_0 SET callstackId=1 WHERE id=?", [ids[1]])
        conn.execute("UPDATE trace_entry_0 SET size=1 WHERE id>=0")
    if layout == "v2":
        # This fixture tests text collation, independently of the original raw
        # frames retained by new imports. Frame identity has separate coverage.
        manifest.pop("extensions", None)
        item["sha256"] = hashlib.sha256(member.read_bytes()).hexdigest()
        manifest_path.write_text(json.dumps(manifest))
    expected_text = {event: texts[int(event == ids[1])] for event in ids}
    with closing(QueryService()) as service:
        groups = service.execute_query("callstack_analysis", {"min_count": 1}, db_path=root)
        assert {r["callstack"]: r["alloc_count"] for r in groups.rows} == {
            texts[0]: len(ids) - 1,
            texts[1]: 1,
        }
        assert len({r["source_stack_id"] for r in groups.rows}) == 2
        for direction in ("ASC", "DESC"):
            result = service.execute_query(
                "event", {"order_by": "callstack", "order_dir": direction, "limit": 1}, db_path=root
            )
            expected = sorted(ids, key=lambda event: (expected_text[event], event), reverse=direction == "DESC")[0]
            assert result.rows[0]["id"] == expected
            assert result.rows[0]["callstack"] == expected_text[expected]
