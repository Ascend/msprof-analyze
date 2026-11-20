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

"""Full frame paths, real imports and read-only cross-shard occupancy contracts."""

import dataclasses
import json
import sqlite3
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from pathlib import Path
from threading import Event

import pytest
from typer.testing import CliRunner

import pt_snap_cli.core.analysis.query_service as query_service_module
from pt_snap_cli.api import SnapshotAnalyzer
from pt_snap_cli.cli import app
from pt_snap_cli.core.analysis.query_service import QueryService
from pt_snap_cli.core.common.errors import (
    InvalidParameterError,
    QueryCancelledError,
    QueryExecutionError,
)
from pt_snap_cli.core.common.models import ImportOptions
from pt_snap_cli.core.common.query_limits import QueryLimits
from pt_snap_cli.core.dataset.query.dataset_frames import attach_frames
from pt_snap_cli.core.importing.import_service import ImportService
from pt_snap_cli.snapshot.base import TraceEntry
from pt_snap_cli.snapshot.representation import load_snapshot_representation
from pt_snap_cli.snapshot.tools.adaptors.ordered_frames import OrderedFrameWriter
from test.core.test_dataset_attribution import case
from test.core.test_msinsight_export import options
from test.core.wheel_scale_acceptance import write_scale_source
from test.snapshot.test_sharded_replay import write_source
from test.test_dataset_focus import hashes

TEMPLATE = "active_memory_frame_tree_at_event"
ROOT = {"filename": "train.py", "line": 1, "name": "train"}
SHARED = {"filename": "model.py", "line": 2, "name": "forward"}
LEAF = {"filename": "tensor.py", "line": 3, "name": "alloc"}
STACKS = {
    0: [LEAF, SHARED, ROOT],
    1: [LEAF, SHARED, ROOT],
    3: [LEAF, ROOT],
    4: [SHARED, SHARED, ROOT],
    5: [SHARED, ROOT],
    6: [],
    11: [LEAF, SHARED, ROOT],
}


@pytest.mark.parametrize("reset", [False, True])
def test_new_frame_tree_or_close_interrupts_old_work_and_releases_connections(tmp_path, monkeypatch, reset):
    root = framed_dataset(tmp_path)
    before = hashes(root)
    started = Event()
    original = query_service_module.frame_tree
    old_caches = []

    def slow_tree(sources, template, params, *args):
        if params["event_id"] == 8:
            old_caches.append(sources.cache)
            started.set()
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                sources.budget.remaining()
                Event().wait(0.005)
            pytest.fail("The obsolete tree was not cancelled")
        return original(sources, template, params, *args)

    monkeypatch.setattr(query_service_module, "frame_tree", slow_tree)
    with closing(QueryService()) as service, ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(service.execute_query, TEMPLATE, {"event_id": 8}, db_path=root, timeout_s=0)
        assert started.wait(3)
        if reset:
            service.close()
        second = pool.submit(service.execute_query, TEMPLATE, {"event_id": 9}, db_path=root)
        with pytest.raises(QueryCancelledError):
            first.result(timeout=5)
        result = second.result(timeout=5)
        assert_conserved(result.rows)
        assert all(len(cache) == 0 for cache in old_caches)
        # Completion must not leave cancellation installed for the next call.
        assert service.execute_query(TEMPLATE, {"event_id": 9}, db_path=root).rows == result.rows
    assert hashes(root) == before


@pytest.mark.parametrize("reset", ["close", "invalidate_context_cache"])
def test_analyzer_reset_cancels_its_inflight_tree(tmp_path, monkeypatch, reset):
    root = framed_dataset(tmp_path)
    started = Event()
    original = query_service_module.frame_tree

    def slow_tree(sources, template, params, *args):
        if params["event_id"] == 8:
            started.set()
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                sources.budget.remaining()
                Event().wait(0.005)
            pytest.fail("Analyzer reset did not cancel the obsolete tree")
        return original(sources, template, params, *args)

    monkeypatch.setattr(query_service_module, "frame_tree", slow_tree)
    with SnapshotAnalyzer(root) as analyzer, ThreadPoolExecutor(max_workers=1) as pool:
        first = pool.submit(analyzer.execute_query, TEMPLATE, {"event_id": 8}, timeout_s=0)
        assert started.wait(3)
        getattr(analyzer, reset)()
        with pytest.raises(QueryCancelledError):
            first.result(timeout=5)
        if reset == "invalidate_context_cache":
            assert_conserved(analyzer.execute_query(TEMPLATE, {"event_id": 9})["rows"])


@pytest.fixture(autouse=True)
def isolate(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.delenv("PT_SNAP_DB_PATH", raising=False)
    monkeypatch.delenv("PT_SNAP_QUERY_TIMEOUT", raising=False)


def framed_dataset(tmp_path, version=2):
    root = case(tmp_path)
    manifest = root / "manifest.json"
    raw = json.loads(manifest.read_text())
    raw["extensions"] = {"ptSnapOrderedFrames": {"version": version}}
    manifest.write_text(json.dumps(raw))
    for device in (0, 2):
        for index in range(8):
            with (
                closing(sqlite3.connect(root / f"device_{device}/slice_{index:05d}.db")) as conn,
                conn,
            ):
                if version == 2:
                    writer = OrderedFrameWriter(conn)
                else:
                    conn.executescript(
                        "CREATE TABLE pt_snap_frame_coverage (eventId INTEGER PRIMARY KEY,frameCount INTEGER);"
                        "CREATE TABLE pt_snap_frame (eventId INTEGER,frameIndex INTEGER,frameJson TEXT, PRIMARY KEY(eventId,frameIndex));"
                    )
                for event in range(index * 2, index * 2 + 2):
                    if event not in STACKS:
                        continue
                    if version == 2:
                        entry = TraceEntry.from_dict({"id": event, "action": "alloc", "frames": STACKS[event]})
                        writer.insert(entry)
                    else:
                        conn.execute(
                            "INSERT INTO pt_snap_frame_coverage VALUES (?,?)",
                            (event, len(STACKS[event])),
                        )
                        conn.executemany(
                            "INSERT INTO pt_snap_frame VALUES (?,?,?)",
                            [(event, i, json.dumps(frame)) for i, frame in enumerate(STACKS[event])],
                        )
    return root


def assert_conserved(rows):
    assert rows[0]["node_id"] == "root"
    for total, own in (
        ("size_bytes", "self_bytes"),
        ("requested_bytes", "self_requested_bytes"),
        ("block_count", "self_block_count"),
    ):
        assert sum(row[own] for row in rows) == rows[0][total]
        for row in rows:
            assert row[total] == row[own] + sum(child[total] for child in rows if child["parent_id"] == row["node_id"])


@pytest.mark.parametrize("version", (1, 2))
def test_paths_recursion_source_owners_and_devices_conserve_occupancy(tmp_path, version):
    root = framed_dataset(tmp_path, version)
    before = hashes(root)
    with SnapshotAnalyzer(root) as analyzer:
        result = analyzer.execute_query(TEMPLATE, {"event_id": 8}, exact_total=True)
        rows = result["rows"]
        assert_conserved(rows)
        assert (rows[0]["size_bytes"], rows[0]["block_count"]) == (295, 9)
        assert sorted(r["size_bytes"] for r in rows if r["name"] == "alloc") == [40, 150]
        assert sorted((r["depth"], r["size_bytes"], r["self_bytes"]) for r in rows if r["name"] == "forward") == [
            (2, 205, 25),
            (3, 30, 30),
        ]
        assert next(r for r in rows if r["node_id"] == "missing")["size_bytes"] == 15
        assert next(r for r in rows if r["node_id"] == "empty_callstack")["size_bytes"] == 20
        assert not result["scope"]["source_coverage"]["ordered_frames_complete"]
        assert rows == analyzer.execute_query(TEMPLATE, {"event_id": 8}, device_id=2)["rows"]
        assert analyzer.execute_query(TEMPLATE, {"event_id": 11})["rows"][0]["size_bytes"] == 285
        filtered = analyzer.execute_query(TEMPLATE, {"event_id": 8, "include_static": False, "min_size": 30})["rows"]
        assert_conserved(filtered)
        assert filtered[0]["size_bytes"] == 220
        empty = analyzer.execute_query(TEMPLATE, {"event_id": 8, "min_size": 9999})["rows"]
        assert len(empty) == 1 and empty[0]["size_bytes"] == 0 and empty[0]["percent_of_total"] is None
        capped = analyzer.execute_query(TEMPLATE, {"event_id": 8}, max_rows=2, exact_total=True)
        assert capped["rows"] == rows[:2] and capped["truncated"] and capped["total"] == len(rows)
        with pytest.raises(InvalidParameterError):
            analyzer.execute_query(TEMPLATE, {"event_id": 8}, slice_index=0)
    assert hashes(root) == before


@pytest.mark.parametrize("damage", ("tail", "frame", "json", "type", "schema", "version"))
def test_bad_evidence_degrades_to_missing_without_losing_bytes(tmp_path, damage):
    root = framed_dataset(tmp_path)
    path = root / "device_0/slice_00000.db"
    with closing(sqlite3.connect(path)) as conn, conn:
        if damage == "tail":
            conn.execute("DELETE FROM pt_snap_stack_frame WHERE frameIndex=2")
        elif damage == "frame":
            conn.execute("DELETE FROM pt_snap_frame_value")
        elif damage == "json":
            conn.execute("UPDATE pt_snap_frame_value SET frameJson='[]'")
        elif damage == "type":
            conn.execute(
                "UPDATE pt_snap_frame_value SET frameJson=?",
                ('{"filename":"x","line":true,"name":"n"}',),
            )
        elif damage == "schema":
            conn.execute("DROP TABLE pt_snap_stack_frame")
    if damage == "version":
        manifest = root / "manifest.json"
        data = json.loads(manifest.read_text())
        data["extensions"]["ptSnapOrderedFrames"]["version"] = 999
        manifest.write_text(json.dumps(data))
    before = hashes(root)
    with SnapshotAnalyzer(root) as analyzer:
        rows = analyzer.execute_query(TEMPLATE, {"event_id": 8})["rows"]
        assert_conserved(rows)
        assert rows[0]["size_bytes"] == 295
        assert next(r for r in rows if r["node_id"] == "missing")["size_bytes"] >= 165
    assert hashes(root) == before


@pytest.mark.parametrize("fmt", ("pt-snap-native-v2", "msinsight"))
def test_real_import_matches_single_tree_and_cli_report(tmp_path, fmt):
    request = options(tmp_path, capacity=2, focus=False)
    # Same complete raw triple under two parents; preserve deep recursion too.
    data = load_snapshot_representation(request.snapshot_file)  # test-owned generated input
    data["device_traces"][0][0]["frames"] = [LEAF, SHARED, ROOT]
    data["device_traces"][0][1]["frames"] = [SHARED, SHARED, ROOT]
    data["device_traces"][0][-1]["frames"] = [LEAF, ROOT]
    write_source(tmp_path, data)
    service = ImportService()
    dataset = service.import_snapshot(dataclasses.replace(request, format=fmt, events_per_slice=2))
    single = service.import_snapshot(ImportOptions(request.snapshot_file, tmp_path / "single", set_focus=False))
    before = hashes(dataset.db_path)

    def paths(rows):
        by_id = {r["node_id"]: r for r in rows}
        result = {}
        for row in rows:
            labels = []
            current = row
            while current is not None:
                labels.append(current["label"])
                current = by_id.get(current["parent_id"])
            result[tuple(reversed(labels))] = tuple(
                row[k]
                for k in (
                    "size_bytes",
                    "self_bytes",
                    "requested_bytes",
                    "self_requested_bytes",
                    "block_count",
                    "self_block_count",
                    "percent_of_total",
                )
            )
        return result

    with (
        SnapshotAnalyzer(dataset.db_path) as analyzer,
        SnapshotAnalyzer(single.db_path) as reference,
    ):
        for event in range(5):
            actual = analyzer.execute_query(TEMPLATE, {"event_id": event})
            assert_conserved(actual["rows"])
            assert paths(actual["rows"]) == paths(reference.execute_query(TEMPLATE, {"event_id": event})["rows"])
        rows = analyzer.execute_query(TEMPLATE, {"event_id": 3})["rows"]
        assert analyzer.execute_query("event", {"id": 0})["rows"][0]["frames"] == [
            LEAF,
            SHARED,
            ROOT,
        ]
    runner = CliRunner()
    args = ["report", "memory-tree", str(dataset.db_path), "--event-id", "3"]
    report = runner.invoke(app, [*args, "--json"])
    assert report.exit_code == 0, report.output
    assert json.loads(report.output)["rows"] == rows
    html = runner.invoke(app, [*args, "--format", "html"])
    assert html.exit_code == 0 and "Reset zoom" in html.output
    assert hashes(dataset.db_path) == before


def test_dedup_storage_and_budget_failure_are_explicit(tmp_path):
    root = framed_dataset(tmp_path)
    with closing(sqlite3.connect(root / "device_0/slice_00000.db")) as conn:
        assert conn.execute("SELECT COUNT(*) FROM pt_snap_frame_value").fetchone()[0] == 3
        assert conn.execute("SELECT COUNT(*) FROM pt_snap_stack").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM pt_snap_event_stack").fetchone()[0] == 2
    service = QueryService()
    try:
        with pytest.raises(QueryExecutionError, match="budget"):
            service.execute_query(TEMPLATE, {"event_id": 8}, db_path=root, query_limits=QueryLimits(max_work_rows=1))
        assert service.execute_query(TEMPLATE, {"event_id": 8}, db_path=root).rows[0]["size_bytes"] == 295
    finally:
        service.close()


def test_same_rendered_stack_is_not_a_frame_path_identity(tmp_path):
    root = framed_dataset(tmp_path)
    # Both arrays render as "a:1 b\nc:2 d" when traversed caller-first.
    arrays = [
        [{"filename": "a", "line": 1, "name": "b\nc:2 d"}],
        [{"filename": "c", "line": 2, "name": "d"}, {"filename": "a", "line": 1, "name": "b"}],
    ]
    with closing(sqlite3.connect(root / "device_0/slice_00000.db")) as conn, conn:
        conn.execute("DELETE FROM pt_snap_event_stack")
        conn.execute("DELETE FROM pt_snap_stack_frame")
        conn.execute("DELETE FROM pt_snap_stack")
        conn.execute("DELETE FROM pt_snap_frame_value")
        for table in (
            "pt_snap_event_stack",
            "pt_snap_stack_frame",
            "pt_snap_stack",
            "pt_snap_frame_value",
        ):
            conn.execute(f"DROP TABLE {table}")
        writer = OrderedFrameWriter(conn)
        for event, frames in enumerate(arrays):
            writer.insert(TraceEntry.from_dict({"id": event, "action": "alloc", "frames": frames}))
        conn.execute("UPDATE trace_entry_0 SET callstack=? WHERE id IN (0,1)", ("a:1 b\nc:2 d",))
    with SnapshotAnalyzer(root) as analyzer:
        rows = analyzer.execute_query(TEMPLATE, {"event_id": 1})["rows"]
        assert_conserved(rows)
        assert len([row for row in rows if row["filename"] == "a"]) == 2
        assert sorted(row["size_bytes"] for row in rows if row["filename"] == "a") == [60, 90]


def test_repeated_ordered_stacks_reduce_before_fetching_with_real_work_budget(tmp_path):
    source = write_scale_source(tmp_path / "scale.pkl", 10_003)
    result = ImportService().import_snapshot(
        ImportOptions(source, tmp_path / "output", set_focus=False, events_per_slice=5_000, format="msinsight")
    )
    before = hashes(result.db_path)
    with SnapshotAnalyzer(result.db_path) as analyzer:
        stats = analyzer.execute_query(
            "callstack_analysis", {"min_count": 1}, query_limits=QueryLimits(max_work_rows=1000)
        )
        assert len(stats["rows"]) == 6
        assert sum(row["alloc_count"] for row in stats["rows"]) == 10_003
        assert sum(row["total_size"] for row in stats["rows"]) == 16 * 10_003 + 64
        assert stats["scope"]["source_coverage"]["ordered_frame_events"] == 10_003
        for event, expected in ((4_999, 176), (5_000, 160), (10_002, 176)):
            tree = analyzer.execute_query(TEMPLATE, {"event_id": event})
            assert tree["rows"][0]["size_bytes"] == expected
            assert tree["scope"]["source_coverage"]["ordered_frames_complete"]
            assert_conserved(tree["rows"])
    assert hashes(result.db_path) == before


def test_legacy_native_artifact_is_readable_but_frame_tree_degrades(tmp_path):
    request = options(tmp_path, focus=False)
    result = ImportService().import_snapshot(dataclasses.replace(request, format=None))
    manifest = result.db_path / "manifest.json"
    raw = json.loads(manifest.read_text())
    raw["identity"]["extensionContractVersion"] = 1
    raw.pop("extensions")
    manifest.write_text(json.dumps(raw))
    before = hashes(result.db_path)
    with SnapshotAnalyzer(result.db_path) as analyzer:
        result = analyzer.execute_query(TEMPLATE, {"event_id": 3})
        assert_conserved(result["rows"])
        assert {row["name"] for row in result["rows"]} == {None}
        assert not result["scope"]["source_coverage"]["ordered_frames_complete"]
    assert hashes(manifest.parent) == before


def test_statistics_representative_is_earliest_event_not_local_stack_id(tmp_path):
    root = framed_dataset(tmp_path)
    # Equivalent arrays may use different local IDs in optional frame evidence.
    # SQLite's GROUP BY order must not select event 1 ahead of event 0.
    with closing(sqlite3.connect(root / "device_0/slice_00000.db")) as conn, conn:
        conn.execute("INSERT INTO pt_snap_stack SELECT 99,frameCount FROM pt_snap_stack WHERE stackId=0")
        conn.execute(
            "INSERT INTO pt_snap_stack_frame SELECT 99,frameIndex,frameId FROM pt_snap_stack_frame WHERE stackId=0"
        )
        conn.execute("UPDATE pt_snap_event_stack SET stackId=99 WHERE eventId=0")
    before = hashes(root)
    with SnapshotAnalyzer(root) as analyzer:
        rows = analyzer.execute_query("callstack_analysis", {"min_count": 1})["rows"]
        shared = next(row for row in rows if row["callstack"].startswith("shared:"))
        assert shared["stack_event_id"] == 0
        assert shared["alloc_count"] == 3  # Events 0, 1 and 11 share the raw array.
        assert shared["total_size"] == 24  # Trace-event sizes, not live block sizes.
    assert hashes(root) == before


def test_large_shared_stack_batch_never_searches_all_event_ids(tmp_path):
    class EventIds(list):
        def __contains__(self, event):
            pytest.fail("Frame loading must not perform linear event-list membership")

    class Budget:
        def remaining(self):
            return None

    path = tmp_path / "many-allocations.db"
    with closing(sqlite3.connect(path)) as conn:
        conn.executescript(
            "CREATE TABLE pt_snap_event_stack(eventId INTEGER PRIMARY KEY,stackId INTEGER);"
            "CREATE TABLE pt_snap_stack(stackId INTEGER PRIMARY KEY,frameCount INTEGER);"
            "CREATE TABLE pt_snap_stack_frame(stackId INTEGER,frameIndex INTEGER,frameId INTEGER);"
            "CREATE TABLE pt_snap_frame_value(id INTEGER PRIMARY KEY,frameJson TEXT);"
            "INSERT INTO pt_snap_stack VALUES(0,1);"
            "INSERT INTO pt_snap_stack_frame VALUES(0,0,0);"
        )
        conn.execute(
            "INSERT INTO pt_snap_frame_value VALUES(0,?)",
            (json.dumps({"filename": "alloc.py", "line": 1, "name": "alloc"}),),
        )
        conn.executemany("INSERT INTO pt_snap_event_stack VALUES(?,0)", ((i,) for i in range(30000)))
        conn.row_factory = sqlite3.Row

        class Resolver:
            _frame_schemas = {path: True}
            budget = Budget()
            reads = 0

            def read(self, path, sql, values=None):
                self.reads += 1
                return [dict(row) for row in conn.execute(sql, values or [])]

        resolver = Resolver()
        frames = attach_frames(resolver, path, EventIds(range(30000)))
        assert len(frames) == 30000
        assert resolver.reads == 2 * ((30000 + 255) // 256)
        assert frames[0] == frames[29999]
