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

"""Same-artifact real route and subprocess paging acceptance.

Focused cases run on every PR. Slow cases use one million dynamic lifecycles
(2,999,998 real events), not one million events or an enormous capture. No test
asks SQLite to ATTACH beyond its actual limit. Signal/crash cleanup, concurrent
rewriters, ordered frames and producer acceptance are separate contracts.
"""

import json
import sqlite3
from pathlib import Path

import pytest

from pt_snap_cli.api import QueryLimits, SnapshotAnalyzer
from pt_snap_cli.core.common.errors import QueryExecutionError
from pt_snap_cli.core.dataset.lifecycle import dataset_lifecycle_scratch as scratch
from pt_snap_cli.core.dataset.lifecycle import dataset_lifecycle_sql as sql
from pt_snap_cli.core.dataset.lifecycle.dataset_lifecycle_connection import _AttachedSources
from test.dataset_failure_support import (
    ENV_NAMES,
    child_environment,
    lifecycle_dataset,
    run_cli,
)
from test.test_dataset_focus import hashes


@pytest.fixture(autouse=True)
def isolate(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HOME", str(tmp_path))
    for name in ENV_NAMES:
        monkeypatch.delenv(name, raising=False)


@pytest.fixture(scope="module")
def million_lifecycles(tmp_path_factory):
    return lifecycle_dataset(tmp_path_factory.mktemp("million-lifecycles") / "dataset", 1_000_000)


def assert_source_unchanged(root, before):
    assert hashes(root) == before
    for suffix in ("-journal", "-wal", "-shm"):
        assert not list(root.rglob(f"*{suffix}"))


def compare_routes(root, lifecycles, monkeypatch, record_property):
    before = hashes(root)
    assert sql._attachment_limit() >= 4, "Four-shard ATTACH evidence needs a legal runtime limit"
    attached, built, connections, directories = [], [], [], []
    original_enter, original_build = _AttachedSources.__enter__, scratch._ScratchSources.build

    def enter(database):
        result = original_enter(database)
        names = [r[1] for r in database.connection.execute("PRAGMA database_list").fetchall()]
        attached.append(names)
        connections.append(database.connection)
        return result

    def build(database, items, maximum):
        result = original_build(database, items, maximum)
        connection = database.connection
        path = Path(connection.execute("PRAGMA database_list").fetchone()[2])
        directories.append(path.parent)
        connections.append(connection)
        built.append(connection.execute("SELECT COUNT(*) FROM lifecycle_state").fetchone()[0])
        assert path.stat().st_size <= maximum
        return result

    monkeypatch.setattr(_AttachedSources, "__enter__", enter)
    monkeypatch.setattr(scratch._ScratchSources, "build", build)
    cases = [
        ("block", {"limit": 5, "offset": 2, "order_by": "id", "order_dir": "ASC"}),
        ("leak_detection", {"limit": 5}),
        ("freed_block_lifetime", {}),
    ]
    answers = []
    for threshold in (2 * lifecycles + 100, 0):
        # Only the route decision changes. Actual SQL, storage and all default
        # row/byte/scratch budgets are identical on the very same artifact.
        monkeypatch.setattr(sql, "_ATTACHED_OBSERVATION_LIMIT", threshold)
        with SnapshotAnalyzer(root) as analyzer:
            answers.append([analyzer.execute_query(name, params, exact_total=True) for name, params in cases])
    assert attached == [["main", "s0", "s1", "s2", "s3"]] * 3
    assert built == [lifecycles + 1] * 3
    for first, second in zip(*answers, strict=True):
        # Query counts are operational diagnostics, not semantic result fields.
        for answer in (first, second):
            answer["scope"]["source_coverage"].pop("source_queries")
        assert first == second
    block, leak, freed = answers[0]
    assert block["total"] == lifecycles + 1
    assert [row["id"] for row in block["rows"]] == [3, 6, 9, 12, 15]
    coverage = block["scope"]["source_coverage"]
    assert coverage["lifecycles"] == lifecycles + 1
    assert coverage["allocation_events_resolved"] == lifecycles
    assert coverage["free_events_resolved"] == lifecycles - 1
    assert coverage["unproved_identities"] == 0
    assert leak["total"] == 1
    assert leak["rows"][0]["allocEventId"] == 3 * (lifecycles - 1)
    assert freed["rows"][0]["block_count"] == lifecycles - 1
    assert freed["rows"][0]["size_bytes"] == 16 * (lifecycles - 1)
    assert freed["rows"][0]["lifetime_events"] == "<1k"
    assert all(not path.exists() for path in directories)
    for connection in connections:
        with pytest.raises(sqlite3.ProgrammingError, match="closed"):
            connection.execute("SELECT 1")
    assert_source_unchanged(root, before)
    record_property(
        "route_acceptance",
        json.dumps(
            {
                "dynamic_lifecycles": lifecycles,
                "static_lifecycles": 1,
                "events": 3 * lifecycles - 2,
                "shards": 4,
                "actual_attached_names": attached,
                "scratch_lifecycle_counts": built,
                "scratch_directories_removed": len(directories),
                "source_hashes": before,
            },
            default=str,
        ),
    )


def active_and_crossing_contract(root, lifecycles):
    before = hashes(root)
    manifest = json.loads((root / "manifest.json").read_text())
    boundary = manifest["eventsPerSlice"]
    allocation = boundary - boundary % 3
    if allocation == boundary:
        allocation -= 3
    assert allocation < boundary <= allocation + 2
    with SnapshotAnalyzer(root) as analyzer:
        row = analyzer.execute_query("block", {"allocEventId": allocation}, exact_total=True)["rows"][0]
        assert row["allocation_source"]["slice_index"] == 0
        assert row["free_source"]["slice_index"] == 1
        for template in ("active_blocks_at_event", "active_memory_callstack_at_event"):
            for include_static, offset, total in ((True, 1, 2), (False, 0, 1)):
                params = {"event_id": 3 * (lifecycles - 1), "include_static": include_static}
                if template == "active_blocks_at_event":
                    params.update(offset=offset, limit=1)
                else:
                    params["top_n"] = 1
                answer = analyzer.execute_query(template, params, exact_total=True)
                assert answer["total"] == total
                assert answer["returned"] == (1 if template == "active_blocks_at_event" else total)
                assert answer["total_is_exact"]
                if template == "active_blocks_at_event":
                    assert answer["rows"][0]["allocEventId"] == 3 * (lifecycles - 1)
                else:
                    assert sorted(row["size_bytes"] for row in answer["rows"]) == ([16, 64] if include_static else [16])
    assert_source_unchanged(root, before)


def test_focused_real_routes_and_cross_shard_templates(tmp_path, monkeypatch, record_property):
    root = lifecycle_dataset(tmp_path / "routes", 80)
    compare_routes(root, 80, monkeypatch, record_property)
    active_and_crossing_contract(root, 80)


@pytest.mark.nightly
@pytest.mark.slow
def test_million_lifecycles_real_attach_and_scratch_routes(million_lifecycles, monkeypatch, record_property):
    compare_routes(million_lifecycles, 1_000_000, monkeypatch, record_property)
    active_and_crossing_contract(million_lifecycles, 1_000_000)


def above_attachment_limit(root, lifecycles, monkeypatch):
    before = hashes(root)
    built, directories = [], []
    original = scratch._ScratchSources.build

    def build(database, items, maximum):
        result = original(database, items, maximum)
        built.append(len(items))
        path = Path(database.connection.execute("PRAGMA database_list").fetchone()[2])
        directories.append(path.parent)
        return result

    def illegal_attach(database):
        pytest.fail("Over-limit operation must select scratch or bounded Python fallback")

    monkeypatch.setattr(scratch._ScratchSources, "build", build)
    monkeypatch.setattr(_AttachedSources, "__enter__", illegal_attach)
    with SnapshotAnalyzer(root) as analyzer:
        actual = analyzer.execute_query("block", {"limit": 5}, exact_total=True)
        assert actual["total"] == lifecycles + 1 and actual["returned"] == 5
        assert actual["scope"]["source_coverage"]["allocation_events_resolved"] == lifecycles
        limits = QueryLimits(max_scratch_db_bytes=0)
        if lifecycles > limits.max_work_rows:
            with pytest.raises(QueryExecutionError, match="work budget exceeded"):
                analyzer.execute_query("block", {"limit": 5}, query_limits=limits)
        else:
            fallback = analyzer.execute_query("block", {"limit": 5}, exact_total=True, query_limits=limits)
            assert fallback["rows"] == actual["rows"]
            assert fallback["total"] == actual["total"]
    assert built == [sql._attachment_limit() + 1]
    assert all(not path.exists() for path in directories)
    assert_source_unchanged(root, before)


def test_focused_over_limit_scratch_and_disabled_fallback(tmp_path, monkeypatch):
    root = lifecycle_dataset(tmp_path / "over-limit", 80, sql._attachment_limit() + 1)
    above_attachment_limit(root, 80, monkeypatch)


@pytest.mark.nightly
@pytest.mark.slow
def test_million_lifecycles_over_limit_respects_disabled_scratch_budget(tmp_path, monkeypatch):
    root = lifecycle_dataset(tmp_path / "over-limit", 1_000_000, sql._attachment_limit() + 1)
    above_attachment_limit(root, 1_000_000, monkeypatch)


def deep_cli_paging(root, lifecycles, tmp_path):
    before = hashes(root)
    offset = 100_001 if lifecycles == 1_000_000 else 30_000
    raised_budget = 500_000 if lifecycles == 1_000_000 else 300_000
    count = 3 * lifecycles - 2
    params = {"min_id": 0, "offset": offset, "limit": 5, "order_by": "address", "order_dir": "DESC"}
    base = ["query", str(root), "--template-use", "event", "--exact-total", "--json"]

    def query(parameters, flags=(), env=None):
        return run_cli(tmp_path, base + ["--params", json.dumps(parameters), *flags], env=env)

    failed = query(params)
    assert failed.returncode == 1 and failed.stdout == ""
    error = json.loads(failed.stderr)["error"]
    assert error["code"] == "QUERY_FAILED"
    assert "max_work_rows=100000" in error["message"]
    assert "no partial global result" in error["message"]
    raised = query(params, ["--max-work-rows", str(raised_budget)])
    by_id = query({**params, "order_by": "id"})
    env = child_environment(tmp_path)
    env["PT_SNAP_MAX_WORK_ROWS"] = str(raised_budget)
    from_env = query(params, env=env)
    env["PT_SNAP_MAX_WORK_ROWS"] = "1"
    overridden = query(params, ["--max-work-rows", str(raised_budget)], env=env)
    env["PT_SNAP_MAX_WORK_ROWS"] = str(raised_budget)
    restrictive_flag = query(params, ["--max-work-rows", "1"], env=env)
    assert restrictive_flag.returncode == 1 and restrictive_flag.stdout == ""
    assert "max_work_rows=1," in json.loads(restrictive_flag.stderr)["error"]["message"]
    expected_ids = list(range(count - 1 - offset, count - 6 - offset, -1))
    for result, budget in (
        (raised, raised_budget),
        (by_id, 100000),
        (from_env, raised_budget),
        (overridden, raised_budget),
    ):
        assert result.returncode == 0, result.stderr
        assert result.stderr == ""
        payload = json.loads(result.stdout)
        assert [row["id"] for row in payload["rows"]] == expected_ids
        assert payload["total"] == count and payload["returned"] == 5
        assert payload["total_is_exact"] and payload["has_more"]
        assert payload["scope"]["work_budget"]["max_rows"] == budget
    assert_source_unchanged(root, before)


def test_focused_real_subprocess_deep_offset_and_budget_precedence(tmp_path):
    root = lifecycle_dataset(tmp_path / "paging", 40_000)
    deep_cli_paging(root, 40_000, tmp_path)


@pytest.mark.nightly
@pytest.mark.slow
def test_million_lifecycles_real_subprocess_deep_offset_and_budget_precedence(million_lifecycles, tmp_path):
    deep_cli_paging(million_lifecycles, 1_000_000, tmp_path)
