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

"""Device-global real SQLite regressions; synthetic inputs, never an upstream producer."""

import copy
import dataclasses
import hashlib
import json
import sqlite3
import time
from contextlib import closing
from pathlib import Path

import pytest
from typer.testing import CliRunner

from pt_snap_cli.api import SnapshotAnalyzer
from pt_snap_cli.cli import app
from pt_snap_cli.core.analysis.query_service import QueryService
from pt_snap_cli.core.analysis.report_service import ReportService
from pt_snap_cli.core.cache.context_cache import ContextCache
from pt_snap_cli.core.common.errors import (
    InvalidParameterError,
    QueryExecutionError,
    QueryTimeoutError,
    TemplateNotFoundError,
)
from pt_snap_cli.core.dataset.dataset_resolver import DatasetResolver
from pt_snap_cli.core.dataset.dataset_sources import DatasetSourceResolver, QueryBudget
from pt_snap_cli.core.dataset.dataset_support import DATASET_SUPPORT
from pt_snap_cli.core.importing.import_service import ImportService
from pt_snap_cli.query.registry import get_query, register_query
from test.core.test_dataset_attribution import add_frames, case, standalone
from test.core.test_dataset_import import source_options
from test.test_dataset_focus import hashes, make_dataset


@pytest.fixture(autouse=True)
def isolate(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.delenv("PT_SNAP_DB_PATH", raising=False)
    monkeypatch.delenv("PT_SNAP_QUERY_TIMEOUT", raising=False)


def projected(rows, keys):
    return [{k: row[k] for k in keys} for row in rows]


@pytest.mark.parametrize(
    "template",
    [
        "memory_peak",
        "allocator_gap",
        "allocation",
        "event",
        "block",
        "leak_detection",
        "freed_block_lifetime",
        "callstack_analysis",
        "preexisting_live",
    ],
)
def test_inline_global_matches_real_standalone_without_extensions(tmp_path, template):
    root = case(tmp_path)
    single = standalone(root, tmp_path)
    before = hashes(root)
    params = (
        {"min_count": 1}
        if template == "callstack_analysis"
        else {"event_id": 8}
        if template == "preexisting_live"
        else {}
    )
    with SnapshotAnalyzer(root) as dataset, SnapshotAnalyzer(single) as reference:
        actual = dataset.execute_query(template, params, exact_total=True)
        expected = reference.execute_query(template, params, exact_total=True)
        keys = list(expected["rows"][0]) if expected["rows"] else []
        assert projected(actual["rows"], keys) == expected["rows"]
        assert actual["total"] == expected["total"] and actual["total_is_exact"]
        assert actual["scope"]["range_complete"]
        assert actual["scope"]["boundary_events_included"] is False
    assert hashes(root) == before


@pytest.mark.parametrize(
    "template",
    [
        "memory_peak",
        "allocator_gap",
        "allocation",
        "event",
        "block",
        "leak_detection",
        "freed_block_lifetime",
        "callstack_analysis",
    ],
)
def test_native_sparse_multiple_devices_matches_standalone(tmp_path, template):
    request = dataclasses.replace(source_options(tmp_path, multiple=True), set_focus=False)
    service = ImportService()
    root = service.import_snapshot(request).db_path
    single = service.import_snapshot(dataclasses.replace(request, events_per_slice=None)).db_path
    before = hashes(root)
    params = (
        {"min_count": 1}
        if template == "callstack_analysis"
        else {"min_id": 7}
        if template in ("event", "allocation")
        else {}
    )
    with SnapshotAnalyzer(root) as dataset, SnapshotAnalyzer(single) as reference:
        for device in (0, 1):
            actual = dataset.execute_query(template, params, device_id=device, exact_total=True)
            expected = reference.execute_query(template, params, device_id=device, exact_total=True)
            keys = list(expected["rows"][0]) if expected["rows"] else []
            # Negative IDs are dataset-local tokens, not comparable across imports.
            if template == "block":
                keys.remove("id")
                # Stored state is an observation, not a lifecycle invariant.
                # The standalone dump and latest containing slice can observe
                # different pending-free states; neither is state at arbitrary E.
                keys.remove("state")
                assert all(r["state_scope"] == "latest_slice_observation" for r in actual["rows"])

                def norm(rs, fields=tuple(keys)):
                    return sorted(tuple(str(r[k]) for k in fields) for r in rs)

                assert norm(actual["rows"]) == norm(expected["rows"])
            else:
                assert projected(actual["rows"], keys) == expected["rows"]
            assert actual["total"] == expected["total"]
    assert hashes(root) == before


def test_peaks_ties_last_shard_boundary_and_same_event_report(tmp_path):
    root = case(tmp_path)
    single = standalone(root, tmp_path)
    for index in range(8):
        with closing(sqlite3.connect(root / f"device_0/slice_{index:05d}.db")) as conn, conn:
            conn.execute("UPDATE trace_entry_0 SET allocated=99999,active=99999,reserved=99999 WHERE id<0")
            conn.execute("UPDATE trace_entry_0 SET reserved=5000 WHERE id IN (4,15)")
            conn.execute("UPDATE trace_entry_0 SET allocated=3000 WHERE id=15")
    with closing(sqlite3.connect(single)) as conn, conn:
        conn.execute("UPDATE trace_entry_0 SET reserved=5000 WHERE id IN (4,15)")
        conn.execute("UPDATE trace_entry_0 SET allocated=3000 WHERE id=15")
        conn.execute("INSERT INTO trace_entry_0 VALUES (-1,2,0,0,0,99999,99999,99999,'fake')")
    report = ReportService()
    try:
        with SnapshotAnalyzer(root) as dataset, SnapshotAnalyzer(single) as reference:
            peak = dataset.execute_query("memory_peak")["rows"][0]
            assert peak == reference.execute_query("memory_peak")["rows"][0]
            assert peak["peak_allocated_event_id"] == 15 and peak["peak_reserved_event_id"] == 4
            assert dataset.execute_query("allocator_gap")["rows"] == reference.execute_query("allocator_gap")["rows"]
            for metric in ("allocated", "active", "reserved"):
                result = report.peak_memory_report(root, metric=metric, limit=-1, timeout_s=10)
                original = report.peak_memory_report(single, metric=metric, limit=-1, timeout_s=10)
                assert result.event_id == original.event_id
                assert result.active_bytes_at_event == original.active_bytes_at_event
                assert result.included_bytes == original.included_bytes
                assert result.coverage_percent == original.coverage_percent
                assert result.allocator_gap == original.allocator_gap
                assert result.source_coverage["allocation_source_complete"]
                assert result.budget_scope == "report_composition"
    finally:
        report.close()


def test_global_stack_winner_threshold_weighted_average_and_all_actions(tmp_path):
    root = make_dataset(tmp_path / "ranking", devices=(0,), slices=3)
    for index in range(3):
        with closing(sqlite3.connect(root / f"device_0/slice_{index:05d}.db")) as conn, conn:
            conn.execute(
                "UPDATE trace_entry_0 SET callstack=?,size=11 WHERE id=?",
                (f"local:{index}", index * 2),
            )
            conn.execute(
                "UPDATE trace_entry_0 SET callstack='global',size=?,action=6 WHERE id=?",
                (10 + index, index * 2 + 1),
            )
    with SnapshotAnalyzer(root) as analyzer:
        result = analyzer.execute_query(
            "callstack_analysis", {"min_count": 2, "min_size": 30, "limit": 1}, exact_total=True
        )
        assert result["total"] == 1 and not result["truncated"]
        row = result["rows"][0]
        assert (
            row["callstack"],
            row["alloc_count"],
            row["total_size"],
            row["avg_size"],
            row["max_size"],
        ) == ("global", 3, 33, 11, 12)
        assert result["semantics_version"] == 2  # counts free_completed too, not allocations
        assert (
            analyzer.execute_query("callstack_analysis", {"min_count": 1, "limit": 1})["rows"][0]["callstack"]
            == "global"
        )


def test_lifecycles_terminal_survival_completed_free_reuse_and_unknown(tmp_path):
    root = case(tmp_path)
    # An allocation present in early shards but absent at the terminal shard is
    # NOT a terminal candidate, even if its earlier observation says unfreed.
    with closing(sqlite3.connect(root / "device_0/slice_00007.db")) as conn, conn:
        conn.execute("DELETE FROM block_0 WHERE id=3")
    with SnapshotAnalyzer(root) as analyzer:
        all_rows = analyzer.execute_query("block", exact_total=True)
        assert all_rows["total"] == 10  # not 8 * 10
        assert len({r["lifecycle_id"] for r in all_rows["rows"]}) == 10
        same_address = [r for r in all_rows["rows"] if r["address"] == 100]
        assert len(same_address) == 2 and same_address[0]["lifecycle_id"] != same_address[1]["lifecycle_id"]
        candidates = analyzer.execute_query("leak_detection")["rows"]
        assert {r["id"] for r in candidates} == {4, 5, 6, 7, 11}
        assert all(r["terminal_survivor"] for r in candidates)
        freed = analyzer.execute_query("freed_block_lifetime")["rows"]
        assert sum(r["block_count"] for r in freed) == 2
        old = next(r for r in all_rows["rows"] if r["id"] == 0)
        assert old["free_source"]["event"]["id"] == 10 and old["free_source"]["event"]["action"] == 6
        assert all(r["identity_status"] == "stable_negative_token" for r in all_rows["rows"] if r["id"] < 0)
    with closing(sqlite3.connect(root / "device_0/slice_00000.db")) as conn, conn:
        conn.execute("UPDATE trace_entry_0 SET action=2 WHERE id=0")
    with SnapshotAnalyzer(root) as analyzer:
        result = analyzer.execute_query("block")
        assert result["scope"]["source_coverage"]["unproved_identities"] == 6  # Present through E10.
        assert not result["scope"]["source_coverage"]["allocation_source_complete"]
        assert all(r["id"] != 0 for r in analyzer.execute_query("leak_detection")["rows"])


def test_global_page_filters_ties_exact_total_source_range_and_empty(tmp_path):
    root = case(tmp_path)
    single = standalone(root, tmp_path)
    params = {
        "min_id": 1,
        "max_id": 14,
        "min_active": 50,
        "order_by": "active",
        "order_dir": "DESC",
        "offset": 2,
        "limit": 3,
    }
    with SnapshotAnalyzer(root) as dataset, SnapshotAnalyzer(single) as reference:
        actual = dataset.execute_query("event", params, max_rows=2, exact_total=True)
        expected = reference.execute_query("event", params, max_rows=2, exact_total=True)
        assert actual["rows"] == expected["rows"] and actual["total"] == expected["total"]
        assert len(actual["rows"][0]) == 9
        assert actual["has_more"] and actual["truncated"]
        assert actual["scope"]["slice_indices"] == list(range(8))
        assert actual["scope"]["source_coverage"]["events_resolved"] == 2
        assert actual["scope"]["range_complete"]
        empty = dataset.execute_query("event", {"action": 99}, exact_total=True)
        assert empty["total"] == 0 and not empty["truncated"]
        for endpoints in ({"min_id": -1}, {"max_id": 99}, {"min_id": 3, "max_id": 2}, {"id": True}):
            with pytest.raises(InvalidParameterError):
                dataset.execute_query("event", endpoints)
    request = dataclasses.replace(source_options(tmp_path), set_focus=False)
    native = ImportService().import_snapshot(request).db_path
    with SnapshotAnalyzer(native) as analyzer:
        gap = analyzer.execute_query("memory_peak", {"start_id": 18, "end_id": 26})
        assert all(v is None for v in gap["rows"][0].values())
        assert gap["scope"]["actual_range"]["real_event_count"] == 0
        assert analyzer.execute_query("event", {"min_id": 18, "max_id": 26})["rows"] == []


def test_runtime_overrides_custom_sql_and_capabilities_are_not_builtin_semantics(tmp_path):
    root = case(tmp_path)
    original = get_query("memory_peak")
    custom = copy.deepcopy(original)
    custom.query = "SELECT 999 AS fake"
    register_query(custom)
    try:
        with SnapshotAnalyzer(root) as analyzer:
            assert analyzer.get_template_info("memory_peak")["dataset_support"]["supported"] is False
            with pytest.raises(QueryExecutionError, match="runtime override"):
                analyzer.execute_query("memory_peak")
            with pytest.raises(TemplateNotFoundError):
                analyzer.execute_query("SELECT * FROM block_0")
    finally:
        register_query(original)
    service = QueryService()
    try:
        member = root / "device_0/slice_00000.db"
        executor = service._get_executor(service._validated_context(member))
        executor.register_template(custom)
        assert service.get_template_info("memory_peak").dataset_support["supported"] is False
        with pytest.raises(QueryExecutionError, match="runtime override"):
            service.execute_query("memory_peak", db_path=root)
    finally:
        service.close()
    with SnapshotAnalyzer(root) as analyzer:
        contracts = analyzer.list_capabilities()["templates"]
        assert {c["name"] for c in contracts if c["dataset_support"]["supported"]} == set(DATASET_SUPPORT)


def test_work_limits_detached_batches_borrowed_lru_timeout_cleanup_and_report_deadline(tmp_path, monkeypatch):
    root = case(tmp_path)
    cache = ContextCache(maxsize=1)
    service = QueryService(context_cache=cache)
    report = ReportService()
    try:
        budget = QueryBudget(None, time.monotonic(), max_work_rows=4)
        with pytest.raises(QueryExecutionError, match="work budget"):
            service.execute_query("block", db_path=root, _budget=budget)
        # Eight shard count rows plus one ID page row consume nine work rows;
        # source hydration must use the SAME cumulative budget, not reset.
        budget = QueryBudget(None, time.monotonic(), max_work_rows=9)
        with pytest.raises(QueryExecutionError, match="work budget"):
            service.execute_query("event", db_path=root, max_rows=1, exact_total=True, _budget=budget)
        budget = QueryBudget(None, time.monotonic(), max_work_bytes=1)
        with pytest.raises(QueryExecutionError, match="work budget"):
            service.execute_query("event", db_path=root, _budget=budget)
        assert service.execute_query("block", db_path=root).rows and len(cache) == 1
        held = next(iter(cache._entries.values()))[0]
        with held.connect() as conn:
            assert conn.execute("SELECT 1").fetchone()[0] == 1
        remaining, budgets = [], []
        original = DatasetSourceResolver.read

        def counted(self, path, sql, values=None):
            remaining.append(self.budget.remaining())
            budgets.append(self.budget)
            return original(self, path, sql, values)

        monkeypatch.setattr(DatasetSourceResolver, "read", counted)
        report.peak_memory_report(root, timeout_s=10)
        assert len({id(b) for b in budgets}) == 1
        assert remaining == sorted(remaining, reverse=True)
        remaining.clear()
        expired = QueryBudget(0.001, time.monotonic() - 1)
        with pytest.raises(QueryTimeoutError):
            service.execute_query("event", db_path=root, _budget=expired)
        source = DatasetSourceResolver(DatasetResolver().inspect(root), 0, cache, QueryBudget(0.001, time.monotonic()))
        with pytest.raises(QueryTimeoutError):
            source.read(
                root / "device_0/slice_00000.db",
                "WITH RECURSIVE n(x) AS (SELECT 1 UNION ALL SELECT x+1 FROM n WHERE x<10000000) SELECT SUM(x) FROM n",
            )
        source = DatasetSourceResolver(DatasetResolver().inspect(root), 0, cache, QueryBudget(None, time.monotonic()))
        with pytest.raises(QueryExecutionError):
            source.read(root / "device_0/slice_00000.db", "SELECT * FROM absent_table")
        assert source.read(root / "device_0/slice_00000.db", "SELECT 1 AS okay") == [{"okay": 1}]
        service.close()
        assert len(cache) == 1
    finally:
        service.close()
        report.close()
        cache.close()


def test_callback_deadline_keeps_domain_timeout_and_cli_json_code(tmp_path, monkeypatch):
    root = case(tmp_path)
    original = QueryBudget.consume

    def expire(self, rows):
        self.started -= 100
        return original(self, rows)

    cache = ContextCache(maxsize=1)
    try:
        with monkeypatch.context() as patch:
            patch.setattr(QueryBudget, "consume", expire)
            with SnapshotAnalyzer(root, context_cache=cache) as analyzer:
                with pytest.raises(QueryTimeoutError):
                    analyzer.execute_query("memory_peak", timeout_s=10)
            cli = CliRunner().invoke(
                app,
                ["query", str(root), "--template-use", "memory_peak", "--timeout", "10", "--json"],
            )
            assert cli.exit_code != 0 and not cli.stdout
            assert json.loads(cli.stderr)["error"]["code"] == "QUERY_TIMEOUT"
        with SnapshotAnalyzer(root, context_cache=cache) as analyzer:
            assert analyzer.execute_query("memory_peak")["rows"]
        assert len(cache) == 1
    finally:
        cache.close()


def test_ordered_arrays_control_global_stack_identity_not_local_ids_or_display(tmp_path):
    root = case(tmp_path)
    add_frames(root)
    with SnapshotAnalyzer(root) as analyzer:
        rows = analyzer.execute_query("callstack_analysis", {"min_count": 1})["rows"]
        assert len(rows) == 16  # every explicit raw array differs, including repeated text
        assert len({r["source_stack_id"] for r in rows}) == 16
        assert all(r["frames_status"] == "ordered" for r in rows)


def test_raw_stats_identity_prefers_captured_text_over_null_and_empty(tmp_path):
    root = case(tmp_path)
    add_frames(root)
    for index, changes in [(0, [(0, None), (1, "")]), (1, [(3, "third")])]:
        with closing(sqlite3.connect(root / f"device_0/slice_{index:05d}.db")) as conn, conn:
            for event, text in changes:
                conn.execute("UPDATE trace_entry_0 SET callstack=? WHERE id=?", (text, event))
                conn.execute(
                    "UPDATE pt_snap_frame SET frameJson=? WHERE eventId=? AND frameIndex=2",
                    (json.dumps({"name": "event:0"}), event),
                )
    with SnapshotAnalyzer(root) as analyzer:
        identity = analyzer.execute_query("event", {"id": 0})["rows"][0]["source_stack_id"]
        row = next(
            r
            for r in analyzer.execute_query("callstack_analysis", {"min_count": 1})["rows"]
            if r["source_stack_id"] == identity
        )
        assert row["alloc_count"] == 3 and row["callstack"] == "third"
        assert row["stack_event_id"] == 3 and row["text_kind"] == "captured"
        assert analyzer.execute_query("event", {"id": 1})["rows"][0]["text_kind"] == "missing"


@pytest.mark.parametrize("layout", ["inline", "native"])
@pytest.mark.parametrize("detailed", [False, True])
def test_all_dataset_row_keys_are_declared_by_shared_template_schema(tmp_path, layout, detailed):
    if layout == "inline":
        root = case(tmp_path)
        event = 15
        if detailed:
            add_frames(root)
    else:
        root = ImportService().import_snapshot(dataclasses.replace(source_options(tmp_path), set_focus=False)).db_path
        event = 87
        if detailed:
            manifest = root / "manifest.json"
            raw = json.loads(manifest.read_text())
            raw["extensions"] = {"ptSnapOrderedFrames": {"version": 1}}
            for device, data in raw["devices"].items():
                for item in data["slices"]:
                    path = root / item["file"]
                    with closing(sqlite3.connect(path)) as conn, conn:
                        conn.executescript(
                            "CREATE TABLE pt_snap_frame_coverage (eventId INTEGER PRIMARY KEY,frameCount INTEGER);"
                            "CREATE TABLE pt_snap_frame (eventId INTEGER,frameIndex INTEGER,frameJson TEXT, PRIMARY KEY(eventId,frameIndex));"
                        )
                        ids = [r[0] for r in conn.execute(f"SELECT id FROM trace_entry_{device} WHERE id>=0")]
                        conn.executemany("INSERT INTO pt_snap_frame_coverage VALUES (?,1)", [(i,) for i in ids])
                        conn.executemany(
                            "INSERT INTO pt_snap_frame VALUES (?,0,?)",
                            [(i, '{"name":"same","line":1}') for i in ids],
                        )
                    item["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
            manifest.write_text(json.dumps(raw))
    params = {
        "event": {"stack_bytes": 0 if detailed else -1},
        "callstack_analysis": {"min_count": 1},
        "active_blocks_at_event": {"event_id": event},
        "active_memory_callstack_at_event": {
            "event_id": event,
            "top_n": -1,
            "stack_bytes": 0 if detailed else -1,
        },
        "preexisting_live": {"event_id": event},
        "active_memory_frame_tree_at_event": {"event_id": event},
    }
    with SnapshotAnalyzer(root) as analyzer:
        for template in DATASET_SUPPORT:
            rows = analyzer.execute_query(template, params.get(template), max_rows=1)["rows"]
            info = analyzer.get_template_info(template)
            columns = {field["column"] for field in info["output_schema"]}
            assert all(set(row) <= columns for row in rows), (
                template,
                [set(row) - columns for row in rows],
            )
            cli = CliRunner().invoke(app, ["query", "--template-info", template, "--json"])
            assert cli.exit_code == 0, cli.output
            assert json.loads(cli.stdout)["output_schema"] == info["output_schema"]
            if template in ("block", "leak_detection", "callstack_analysis"):
                dataset_fields = [
                    field
                    for field in info["output_schema"]
                    if any("Dataset only" in text for text in field.get("interpretation_limits", []))
                ]
                assert dataset_fields and all(
                    field.get("metric_semantics") and field.get("scope") for field in dataset_fields
                )


def test_cli_api_report_global_parity_and_range_options(tmp_path):
    root = case(tmp_path)
    runner = CliRunner()
    with SnapshotAnalyzer(root) as analyzer:
        api = analyzer.execute_query("memory_peak", {"start_id": 4, "end_id": 15})
        cli = runner.invoke(
            app,
            [
                "query",
                str(root),
                "--template-use",
                "memory_peak",
                "--params",
                '{"start_id":4,"end_id":15}',
                "--json",
            ],
        )
        assert cli.exit_code == 0, cli.output
        payload = json.loads(cli.stdout)
        for key in api:
            assert payload[key] == api[key]
    cli = runner.invoke(
        app,
        [
            "report",
            "peak-memory",
            str(root),
            "--start-id",
            "4",
            "--end-id",
            "15",
            "--timeout",
            "10",
            "--json",
        ],
    )
    assert cli.exit_code == 0, cli.output
    result = json.loads(cli.stdout)
    assert result["scope"]["requested_range"] == {"first_event_id": 4, "last_event_id": 15}
    assert result["budget_scope"] == "report_composition" and result["timeout_s"] == 10


@pytest.mark.parametrize("native", [False, True])
@pytest.mark.parametrize("direction", ["ASC", "DESC"])
def test_callstack_sorted_event_page_matches_standalone(tmp_path, native, direction):
    if native:
        request = dataclasses.replace(source_options(tmp_path, multiple=True), set_focus=False)
        importer = ImportService()
        root = importer.import_snapshot(request).db_path
        single = importer.import_snapshot(dataclasses.replace(request, events_per_slice=None)).db_path
    else:
        root = case(tmp_path)
        single = standalone(root, tmp_path)
    # Standalone includes synthetic negative boundary IDs; compare real events.
    params = {
        "min_id": 7 if native else 0,
        "order_by": "callstack",
        "order_dir": direction,
        "offset": 1,
        "limit": 3,
    }
    before = hashes(root)
    with SnapshotAnalyzer(root) as dataset, SnapshotAnalyzer(single) as reference:
        for device in (0, 1) if native else (0,):
            actual = dataset.execute_query("event", params, device_id=device, exact_total=True)
            expected = reference.execute_query("event", params, device_id=device, exact_total=True)
            assert actual["rows"]
            keys = list(expected["rows"][0])
            assert projected(actual["rows"], keys) == expected["rows"]
            assert all("callstackId" not in row for row in actual["rows"])
            assert actual["total"] == expected["total"]
            assert actual["has_more"] == expected["has_more"]
            assert actual["truncated"] == expected["truncated"]
    assert hashes(root) == before
