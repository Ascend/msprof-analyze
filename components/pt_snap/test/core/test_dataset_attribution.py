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

"""Real SQLite contracts for point-event attribution; no original producer execution."""

import dataclasses
import json
import sqlite3
import time
from contextlib import closing
from pathlib import Path

import pytest

from pt_snap_cli.api import SnapshotAnalyzer
from pt_snap_cli.core.analysis.query_service import QueryService
from pt_snap_cli.core.analysis.report_service import ReportService
from pt_snap_cli.core.cache.context_cache import ContextCache
from pt_snap_cli.core.common.errors import InvalidParameterError, QueryTimeoutError
from pt_snap_cli.core.dataset.dataset_resolver import DatasetResolver
from pt_snap_cli.core.dataset.dataset_sources import (
    SOURCE_BATCH_SIZE,
    DatasetSourceResolver,
    QueryBudget,
)
from pt_snap_cli.core.importing.import_service import ImportService
from test.core.test_dataset_import import source_options
from test.test_dataset_focus import hashes, make_dataset


@pytest.fixture(autouse=True)
def isolate(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.delenv("PT_SNAP_DB_PATH", raising=False)
    monkeypatch.delenv("PT_SNAP_QUERY_TIMEOUT", raising=False)


def case(tmp_path, devices=(0, 2)):
    root = make_dataset(tmp_path / "no-extensions", devices=devices, slices=8)
    blocks = [
        (0, 100, 90, 85, 0, 0, 10),
        (1, 200, 60, 55, 1, 1, 14),
        (3, 300, 40, 35, 1, 3, -1),
        (4, 400, 30, 25, 1, 4, -1),
        (5, 500, 25, 20, 1, 5, -1),
        (6, 600, 20, 15, 1, 6, -1),
        (7, 700, 15, 10, 1, 7, -1),
        (11, 100, 80, 75, 1, 11, -1),
        (-20, 800, 10, 5, 1, -1, 12),
        (-21, 900, 5, 5, 1, -1, -1),
    ]
    for device in devices:
        for index in range(8):
            with (
                closing(sqlite3.connect(root / f"device_{device}/slice_{index:05d}.db")) as conn,
                conn,
            ):
                # Carry-in and new allocations only. Future allocations and completed
                # lifetimes from earlier windows are not member observations.
                lo, hi = index * 2, index * 2 + 1
                members = [
                    (*b[:4], 0 if b[0] == 0 and lo > 2 else 1, *b[5:])
                    for b in blocks
                    if (b[5] == -1 or b[5] <= hi) and (b[6] == -1 or b[6] >= lo)
                ]
                conn.executemany(f"INSERT INTO block_{device} VALUES (?,?,?,?,?,?,?)", members)
                for event in range(index * 2, index * 2 + 2):
                    text = {
                        0: "shared:" + "长" * 100,
                        1: "shared:" + "长" * 100,
                        3: "third",
                        4: "[missing callstack]",
                        5: "  \n",
                        6: "",
                        7: None,
                        11: "reused",
                    }.get(event, f"free:{event}")
                    action = (
                        4
                        if event in (0, 1, 3, 4, 5, 6, 7, 11)
                        else 6
                        if event in (10, 12, 14)
                        else 5
                        if event == 2
                        else 7
                    )
                    active = sum(b[2] for b in blocks if (b[5] == -1 or b[5] <= event) and (b[6] == -1 or b[6] > event))
                    conn.execute(
                        f"UPDATE trace_entry_{device} SET action=?, active=?, allocated=?, reserved=1000, callstack=? WHERE id=?",
                        (action, active, active - (90 if 2 <= event < 10 else 0), text, event),
                    )
    return root


def standalone(root, tmp_path, device=0):
    target = tmp_path / f"standalone-{device}.db"
    with closing(sqlite3.connect(target)) as out, out:
        out.executescript(
            'CREATE TABLE dictionary ("table" TEXT,"column" TEXT,"key" TEXT,"value" TEXT);'
            f"CREATE TABLE trace_entry_{device} (id INTEGER PRIMARY KEY, action INTEGER,address INTEGER,size INTEGER,stream INTEGER,allocated INTEGER,active INTEGER,reserved INTEGER,callstack TEXT);"
            f"CREATE TABLE block_{device} (id INTEGER PRIMARY KEY,address INTEGER,size INTEGER,requestedSize INTEGER,state INTEGER,allocEventId INTEGER,freeEventId INTEGER);"
        )
        for index in range(8):
            with closing(
                sqlite3.connect(
                    (root / f"device_{device}/slice_{index:05d}.db").as_uri() + "?mode=ro&immutable=1",
                    uri=True,
                )
            ) as conn:
                rows = conn.execute(f"SELECT * FROM trace_entry_{device} WHERE id>=0").fetchall()
                out.executemany(f"INSERT INTO trace_entry_{device} VALUES (?,?,?,?,?,?,?,?,?)", rows)
                if index == 0:
                    out.executemany(
                        "INSERT INTO dictionary VALUES (?,?,?,?)",
                        conn.execute("SELECT * FROM dictionary").fetchall(),
                    )
                # Use the same latest-containing observation contract as global
                # block queries; never take only the first shard's block table.
                out.executemany(
                    f"INSERT OR REPLACE INTO block_{device} VALUES (?,?,?,?,?,?,?)",
                    conn.execute(f"SELECT * FROM block_{device}").fetchall(),
                )
    return target


def normalized_groups(rows):
    return sorted(
        (
            r["callstack"],
            r["category"],
            r["size_bytes"],
            r["requested_bytes"],
            r["block_count"],
            r["percent_of_active_blocks"],
        )
        for r in rows
    )


@pytest.mark.parametrize("event", [0, 2, 8, 10, 11, 12, 14, 15])
def test_original_noextensions_matches_single_db_after_event_and_completed_free(tmp_path, event):
    root = case(tmp_path)
    single = standalone(root, tmp_path)
    before = hashes(root)
    with SnapshotAnalyzer(root) as dataset, SnapshotAnalyzer(single) as reference:
        blocks = dataset.execute_query("active_blocks_at_event", {"event_id": event})
        local = reference.execute_query("active_blocks_at_event", {"event_id": event})
        assert {b["id"] for b in blocks["rows"]} == {b["id"] for b in local["rows"]}
        counter = dataset.execute_query("event", {"id": event})["rows"][0]["active"]
        assert sum(b["size"] for b in blocks["rows"]) == counter
        params = {"event_id": event, "top_n": -1}
        grouped = dataset.execute_query("active_memory_callstack_at_event", params)
        assert normalized_groups(grouped["rows"]) == normalized_groups(
            reference.execute_query("active_memory_callstack_at_event", params)["rows"]
        )
        coverage = grouped["scope"]["source_coverage"]
        assert coverage["active_bytes"] == counter
        assert coverage["allocation_source_complete"]
        assert not coverage["ordered_frames_complete"]
        assert grouped["scope"]["boundary_events_included"] is False
        assert (
            blocks["scope"]["source_coverage"]["free_events_resolved"]
            == blocks["scope"]["source_coverage"]["free_references"]
        )
        assert all(b["state_scope"] == "slice_observation" for b in blocks["rows"])
        if event == 2:
            pending = next(b for b in blocks["rows"] if b["id"] == 0)
            assert pending["free_source"]["event"]["id"] == 10  # Not free_requested=2.
            assert pending["free_source"]["event"]["action"] == 6
        if event == 11:
            reused = next(b for b in blocks["rows"] if b["address"] == 100)
            assert reused["id"] == 11 and reused["allocation_source"]["event"]["id"] == 11
    assert before == hashes(root)
    assert not list(root.rglob("*-wal"))


def test_source_before_top_n_bytes_denominator_specials_missing_literal_and_summary(tmp_path):
    root = case(tmp_path)
    with SnapshotAnalyzer(root) as analyzer:
        result = analyzer.execute_query(
            "active_memory_callstack_at_event", {"event_id": 8, "top_n": 1, "stack_bytes": 5}
        )
        assert [r["size_bytes"] for r in result["rows"]] == [150, 10, 5]
        assert result["rows"][0]["percent_of_active_blocks"] == round(15000 / 165, 4)
        assert result["rows"][0]["stack_event_id"] == 0
        assert result["rows"][0]["stack_truncated"]
        assert result["has_more"] and result["truncated"]
        assert result["scope"]["source_coverage"]["active_bytes"] == 295
        assert result["scope"]["source_coverage"]["allocation_source_complete"]
        smaller = analyzer.execute_query(
            "active_memory_callstack_at_event",
            {"event_id": 8, "top_n": 1},
            max_rows=1,
            exact_total=True,
        )
        assert smaller["total"] == 7 and smaller["returned"] == 1
        assert smaller["rows"][0]["percent_of_active_blocks"] == result["rows"][0]["percent_of_active_blocks"]
        complete = analyzer.execute_query("active_memory_callstack_at_event", {"event_id": 8, "top_n": -1})
        labels = [r for r in complete["rows"] if r["callstack"] == "[missing callstack]"]
        assert len(labels) == 2
        assert {r["stack_kind"] for r in labels} == {"missing", "captured"}
        assert len({r["stack_id"] for r in labels}) == 2
        assert next(r for r in complete["rows"] if r["stack_kind"] == "missing")["size_bytes"] == 35
        assert next(r for r in complete["rows"] if r["callstack"] == "  \n")["stack_kind"] == "captured"
        exclude = analyzer.execute_query(
            "active_memory_callstack_at_event",
            {"event_id": 8, "include_static": False, "min_size": 40, "top_n": -1},
            exact_total=True,
        )
        assert sum(r["size_bytes"] for r in exclude["rows"]) == 190
        assert sum(r["percent_of_active_blocks"] for r in exclude["rows"]) == pytest.approx(100, abs=0.0001)


def test_devices_address_and_negative_lifecycle_identity_are_independent(tmp_path):
    root = case(tmp_path)
    with SnapshotAnalyzer(root) as analyzer:
        one = analyzer.execute_query("active_blocks_at_event", {"event_id": 8}, device_id=0)["rows"]
        two = analyzer.execute_query("active_blocks_at_event", {"event_id": 8}, device_id=2)["rows"]
        assert not {b["lifecycle_id"] for b in one} & {b["lifecycle_id"] for b in two}
        unknown = {b["category"]: b for b in one if b["allocEventId"] == -1}
        assert set(unknown) == {"static", "preexisting_live_at_event"}
        assert unknown["static"]["free_source_status"] == "live_or_unknown"
        assert all(b["allocation_source_status"] == "unknown_preexisting" for b in unknown.values())
        old = next(b for b in one if b["id"] == 0)
        new = next(
            b for b in analyzer.execute_query("active_blocks_at_event", {"event_id": 11})["rows"] if b["id"] == 11
        )
        assert old["address"] == new["address"] and old["lifecycle_id"] != new["lifecycle_id"]


def test_missing_dynamic_action_is_not_static_or_row_truncation(tmp_path):
    root = case(tmp_path)
    with closing(sqlite3.connect(root / "device_0/slice_00000.db")) as conn, conn:
        conn.execute("UPDATE trace_entry_0 SET action=2 WHERE id=0")
    with SnapshotAnalyzer(root) as analyzer:
        result = analyzer.execute_query("active_memory_callstack_at_event", {"event_id": 8, "top_n": -1})
        assert not result["truncated"]
        assert not result["scope"]["source_coverage"]["allocation_source_complete"]
        assert sum(r["size_bytes"] for r in result["rows"]) == 295
        missing = next(r for r in result["rows"] if r["stack_kind"] == "missing")
        assert missing["category"] == "dynamic_live_at_event" and missing["size_bytes"] == 125


@pytest.mark.parametrize("template", ["active_blocks_at_event", "active_memory_callstack_at_event"])
@pytest.mark.parametrize("event,slice_index", [(-1, None), (16, None), (8, 0), (8, True), (8, 99)])
def test_point_event_rejects_boundary_outside_or_wrong_scope(tmp_path, template, event, slice_index):
    root = case(tmp_path)
    with SnapshotAnalyzer(root) as analyzer, pytest.raises(InvalidParameterError):
        analyzer.execute_query(template, {"event_id": event}, slice_index=slice_index)


def test_active_block_limit_offset_exact_and_zero_top_n_keep_coverage(tmp_path):
    root = case(tmp_path)
    with SnapshotAnalyzer(root) as analyzer:
        page = analyzer.execute_query(
            "active_blocks_at_event",
            {"event_id": 8, "order_by": "id", "order_dir": "ASC", "limit": 2, "offset": 1},
            max_rows=1,
            exact_total=True,
        )
        assert page["total"] == 9 and page["returned"] == 1 and page["truncated"]
        assert page["rows"][0]["id"] == -20
        assert page["scope"]["source_coverage"]["active_blocks"] == 9
        zero = analyzer.execute_query("active_memory_callstack_at_event", {"event_id": 8, "top_n": 0}, exact_total=True)
        assert {r["category"] for r in zero["rows"]} == {"static", "preexisting_live_at_event"}
        assert sum(r["percent_of_active_blocks"] for r in zero["rows"]) == 100
        assert zero["has_more"] and zero["total"] == 7


def add_frames(root, version=1, corrupt=None):
    manifest = root / "manifest.json"
    raw = json.loads(manifest.read_text())
    raw["extensions"] = {"ptSnapOrderedFrames": {"version": version}}
    manifest.write_text(json.dumps(raw))
    frame = {"filename": "raw.py", "name": "same", "line": 1, "extra": {"native": True}}
    for device in (0, 2):
        for index in range(8):
            with (
                closing(sqlite3.connect(root / f"device_{device}/slice_{index:05d}.db")) as conn,
                conn,
            ):
                conn.executescript(
                    "CREATE TABLE pt_snap_frame_coverage (eventId INTEGER PRIMARY KEY,frameCount INTEGER); CREATE TABLE pt_snap_frame (eventId INTEGER,frameIndex INTEGER,frameJson TEXT, PRIMARY KEY(eventId,frameIndex));"
                )
                for event in range(index * 2, index * 2 + 2):
                    conn.execute("INSERT INTO pt_snap_frame_coverage VALUES (?,3)", (event,))
                    # order and repeats are significant. Events 0 and 1 share text
                    # but raw identity differs in the final frame.
                    frames = [frame, frame, {"name": f"event:{event}"}]
                    conn.executemany(
                        "INSERT INTO pt_snap_frame VALUES (?,?,?)",
                        [(event, i, json.dumps(f)) for i, f in enumerate(frames)],
                    )
                if index == 0:
                    if corrupt == "gap":
                        conn.execute("DELETE FROM pt_snap_frame WHERE eventId=0 AND frameIndex=1")
                    elif corrupt == "json":
                        conn.execute("UPDATE pt_snap_frame SET frameJson='[]' WHERE eventId=0")
                    elif corrupt == "absent":
                        conn.execute("DROP TABLE pt_snap_frame")
    return frame


def test_recognized_ordered_frames_retain_order_repeats_exact_identity_and_shared_sources(tmp_path):
    root = case(tmp_path)
    frame = add_frames(root)
    before = hashes(root)
    with SnapshotAnalyzer(root) as analyzer:
        row = analyzer.execute_query("event", {"id": 0, "stack_bytes": 0})["rows"][0]
        assert row["frames"] == [frame, frame, {"name": "event:0"}]
        assert row["frames_status"] == "ordered" and row["stack_truncated"]
        result = analyzer.execute_query(
            "active_memory_callstack_at_event", {"event_id": 8, "top_n": -1, "stack_bytes": 0}
        )
        shared = [r for r in result["rows"] if r["stack_event_id"] in (0, 1)]
        assert len(shared) == 2 and shared[0]["stack_id"] != shared[1]["stack_id"]
        assert shared[0]["stack_id"] == row["stack_id"]
        assert shared[0]["frames"][:2] == [frame, frame]
        assert result["scope"]["source_coverage"]["ordered_frames_complete"]
        assert (
            analyzer.get_database_overview()["dataset"]["structured_frames"] is False
        )  # P0 validation, not scoped source coverage.
    assert before == hashes(root)


@pytest.mark.parametrize("version,corrupt", [(999, None), (True, None), (1, "gap"), (1, "json"), (1, "absent")])
def test_unsupported_or_uncovered_frames_degrade_without_reconstructing_text(tmp_path, version, corrupt):
    root = case(tmp_path)
    add_frames(root, version, corrupt)
    with SnapshotAnalyzer(root) as analyzer:
        row = analyzer.execute_query("event", {"id": 0, "stack_bytes": 1000})["rows"][0]
        assert row["frames"] is None and row["frames_status"] == "text_only"
        assert row["callstack"].startswith("shared:")
        result = analyzer.execute_query("active_memory_callstack_at_event", {"event_id": 8, "top_n": -1})
        assert not result["scope"]["source_coverage"]["ordered_frames_complete"]


def test_native_sources_preserve_sparse_ids_local_stack_collision_and_borrowed_lifetime(tmp_path):
    request = dataclasses.replace(source_options(tmp_path, multiple=True), set_focus=False)
    root = ImportService().import_snapshot(request).db_path
    cache = ContextCache(maxsize=1)
    try:
        with SnapshotAnalyzer(root, context_cache=cache) as analyzer:
            result = analyzer.execute_query("active_memory_callstack_at_event", {"event_id": 57, "top_n": -1})
            assert result["scope"]["first_event_id"] == 57
            assert result["scope"]["source_coverage"]["allocation_source_complete"]
            blocks = analyzer.execute_query("active_blocks_at_event", {"event_id": 57})
            sources = [b["allocation_source"] for b in blocks["rows"] if b["allocation_source"]]
            assert sources and all(type(s["local_stack_id"]) is int and type(s["slice_index"]) is int for s in sources)
            assert len(cache) == 1
            with pytest.raises(InvalidParameterError, match="sparse"):
                analyzer.execute_query("active_blocks_at_event", {"event_id": 48})
            assert analyzer.execute_query("event", {"id": 48})["rows"] == []
            with pytest.raises(InvalidParameterError):
                analyzer.execute_query("active_blocks_at_event", {"event_id": 58})
            held = next(iter(cache._entries.values()))[0]
        assert len(cache) == 1
        with held.connect() as conn:
            assert conn.execute("SELECT 1").fetchone()[0] == 1
        with pytest.raises(RuntimeError, match="closed"):
            analyzer.execute_query("active_blocks_at_event", {"event_id": 57})
    finally:
        cache.close()


@pytest.mark.parametrize("event", [7, 17, 27, 37, 47, 57, 67, 77, 87])
def test_native_same_event_active_sets_bytes_and_attribution_match_standalone(tmp_path, event):
    request = dataclasses.replace(source_options(tmp_path), set_focus=False)
    service = ImportService()
    root = service.import_snapshot(request).db_path
    single = service.import_snapshot(dataclasses.replace(request, events_per_slice=None)).db_path
    with SnapshotAnalyzer(root) as dataset, SnapshotAnalyzer(single) as reference:
        params = {"event_id": event}
        blocks = dataset.execute_query("active_blocks_at_event", params)["rows"]
        original = reference.execute_query("active_blocks_at_event", params)["rows"]
        # Unknown negative lifetimes are stable WITHIN a dataset, not globally
        # comparable to a separately imported standalone DB's negative tokens.
        from collections import Counter

        assert {
            (r["id"], r["size"], r["allocEventId"], r["freeEventId"]) for r in blocks if r["allocEventId"] >= 0
        } == {(r["id"], r["size"], r["allocEventId"], r["freeEventId"]) for r in original if r["allocEventId"] >= 0}
        assert Counter(
            (r["address"], r["size"], r["requestedSize"], r["allocEventId"], r["freeEventId"])
            for r in blocks
            if r["allocEventId"] == -1
        ) == Counter(
            (r["address"], r["size"], r["requestedSize"], r["allocEventId"], r["freeEventId"])
            for r in original
            if r["allocEventId"] == -1
        )
        assert sum(r["size"] for r in blocks) == dataset.execute_query("event", {"id": event})["rows"][0]["active"]
        params["top_n"] = -1
        assert normalized_groups(
            dataset.execute_query("active_memory_callstack_at_event", params)["rows"]
        ) == normalized_groups(reference.execute_query("active_memory_callstack_at_event", params)["rows"])


@pytest.mark.parametrize("ordered", [False, True])
def test_cross_owner_same_full_stack_merges_before_top_n_like_standalone(tmp_path, ordered):
    from pt_snap_cli.core.common.models import ImportOptions
    from test.snapshot.test_sharded_replay import block, event, segment, write_source

    data = {
        "segments": [segment(0, 64, [block(1000, 16, 16), block(1016, 16, 16), block(1032, 24, 24)])],
        "device_traces": [
            [
                event("alloc", addr=1000),
                event("alloc", addr=1016),
                event("alloc", addr=1032, size=24),
            ]
        ],
    }
    data["device_traces"][0][2]["frames"] = [{"filename": "other.py", "line": 8, "name": "other"}]
    source = write_source(tmp_path, data)
    service = ImportService()
    request = ImportOptions(source, tmp_path / "outputs", set_focus=False, events_per_slice=1)
    root = service.import_snapshot(request).db_path
    single = service.import_snapshot(dataclasses.replace(request, events_per_slice=None)).db_path
    if ordered:
        raw = json.loads((root / "manifest.json").read_text())
        raw["extensions"] = {"ptSnapOrderedFrames": {"version": 1}}
        import hashlib

        for i, item in enumerate(raw["devices"]["0"]["slices"]):
            path = root / item["file"]
            with closing(sqlite3.connect(path)) as conn, conn:
                conn.executescript(
                    "CREATE TABLE pt_snap_frame_coverage (eventId INTEGER PRIMARY KEY,frameCount INTEGER); CREATE TABLE pt_snap_frame (eventId INTEGER,frameIndex INTEGER,frameJson TEXT, PRIMARY KEY(eventId,frameIndex));"
                )
                conn.execute("INSERT INTO pt_snap_frame_coverage VALUES (?,1)", (i,))
                conn.execute(
                    "INSERT INTO pt_snap_frame VALUES (?,0,?)",
                    (i, json.dumps(data["device_traces"][0][i]["frames"][0])),
                )
            item["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
        (root / "manifest.json").write_text(json.dumps(raw))
    before = hashes(root)
    with SnapshotAnalyzer(root) as dataset, SnapshotAnalyzer(single) as reference:
        params = {"event_id": 2, "top_n": 1}
        result = dataset.execute_query("active_memory_callstack_at_event", params)
        expected = reference.execute_query("active_memory_callstack_at_event", params)
        assert normalized_groups(result["rows"]) == normalized_groups(expected["rows"])
        assert result["rows"][0]["block_count"] == 2 and result["rows"][0]["size_bytes"] == 32
        assert result["rows"][0]["percent_of_active_blocks"] == 100
    assert before == hashes(root)


@pytest.mark.parametrize("missing", [None, ""])
def test_ordered_identity_ignores_formatted_text_availability_across_owners(tmp_path, missing):
    root = case(tmp_path)
    add_frames(root)
    with closing(sqlite3.connect(root / "device_0/slice_00000.db")) as conn, conn:
        conn.execute("UPDATE trace_entry_0 SET callstack=? WHERE id=0", (missing,))
    with closing(sqlite3.connect(root / "device_0/slice_00001.db")) as conn, conn:
        conn.execute(
            "UPDATE pt_snap_frame SET frameJson=? WHERE eventId=3 AND frameIndex=2",
            (json.dumps({"name": "event:0"}),),
        )
    before = hashes(root)
    with SnapshotAnalyzer(root) as analyzer:
        blocks = analyzer.execute_query("active_blocks_at_event", {"event_id": 8})["rows"]
        first = next(b["allocation_source"] for b in blocks if b["id"] == 0)
        other = next(b["allocation_source"] for b in blocks if b["id"] == 3)
        assert first["frames"] == other["frames"]
        assert first["stack_id"] == other["stack_id"]
        result = analyzer.execute_query(
            "active_memory_callstack_at_event", {"event_id": 8, "top_n": 1, "stack_bytes": 0}
        )
        group = result["rows"][0]
        assert (group["size_bytes"], group["block_count"]) == (130, 2)
        assert group["stack_event_id"] == 3
        assert group["text_kind"] == "captured" and first["text_kind"] == "missing"
        assert first["event"]["callstack"] == missing
        row = analyzer.execute_query("event", {"id": 0, "stack_bytes": 0})["rows"][0]
        assert row["frames"] == first["frames"] and row["text_kind"] == "missing"
        json.dumps(row, allow_nan=False)
    assert before == hashes(root)


@pytest.mark.parametrize(
    "raw",
    ['{"line":1e309}', '{"nested":' + "[" * 1200 + "0" + "]" * 1200 + "}"],
    ids=["nonfinite", "too_deep"],
)
def test_nonfinite_and_deep_optional_frames_degrade_readonly(tmp_path, raw):
    root = case(tmp_path)
    add_frames(root)
    with closing(sqlite3.connect(root / "device_0/slice_00000.db")) as conn, conn:
        conn.execute("UPDATE pt_snap_frame SET frameJson=? WHERE eventId=0 AND frameIndex=0", (raw,))
    before = hashes(root)
    with SnapshotAnalyzer(root) as analyzer:
        row = analyzer.execute_query("event", {"id": 0})["rows"][0]
        assert row["frames"] is None and row["frames_status"] == "text_only"
        json.dumps(row, allow_nan=False)
    assert before == hashes(root)


def test_native_bare_local_stack_ids_do_not_alias_foreign_sources(tmp_path):
    root = ImportService().import_snapshot(dataclasses.replace(source_options(tmp_path), set_focus=False)).db_path
    raw = json.loads((root / "manifest.json").read_text())
    # Exercise legacy text-only identity independently of captured frame evidence.
    raw.pop("extensions", None)
    for event in (17, 67):
        item = next(s for s in raw["devices"]["0"]["slices"] if s["startEventId"] <= event <= s["endEventId"])
        path = root / item["file"]
        with closing(sqlite3.connect(path)) as conn, conn:
            local = conn.execute("SELECT callstackId FROM trace_entry_0 WHERE id=?", (event,)).fetchone()[0]
            conn.execute("UPDATE callstack SET id=42 WHERE id=?", (local,))
            conn.execute("UPDATE trace_entry_0 SET callstackId=42 WHERE callstackId=?", (local,))
        import hashlib

        item["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    # Different complete texts with the same local ID must NOT alias.
    for item in raw["devices"]["0"]["slices"]:
        path = root / item["file"]
        with closing(sqlite3.connect(path)) as conn, conn:
            conn.execute(
                "UPDATE callstack SET callstack='different complete stack' WHERE id IN (SELECT callstackId FROM trace_entry_0 WHERE id=67)"
            )
            conn.execute(
                "UPDATE pt_snap_block_reference SET allocCallstack='different complete stack' WHERE blockId=67"
            )
        item["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    (root / "manifest.json").write_text(json.dumps(raw))
    cache = ContextCache(maxsize=1)
    try:
        resolver = DatasetSourceResolver(DatasetResolver().inspect(root), 0, cache, QueryBudget(None, time.monotonic()))
        sources = resolver.events([17, 67])
        assert len(sources) == 2
        assert all(s.local_stack_id == 42 for s in sources.values())
        assert sources[17].slice_index != sources[67].slice_index
        assert sources[17].event["callstack"] != sources[67].event["callstack"]
        assert sources[17].stack_id != sources[67].stack_id
        assert {s.event["id"] for s in sources.values()} == {17, 67}
    finally:
        cache.close()


def test_high_block_count_batches_distinct_sources_and_bounds_cache_queries(tmp_path):
    root = make_dataset(tmp_path / "large", devices=(0,), slices=300)
    with closing(sqlite3.connect(root / "device_0/slice_00299.db")) as conn, conn:
        conn.executemany(
            "INSERT INTO block_0 VALUES (?,100,8,8,1,?,-1)",
            [(event, event) for event in range(599)],
        )
    dataset = DatasetResolver().inspect(root)
    cache = ContextCache(maxsize=2)
    try:
        sources = DatasetSourceResolver(dataset, 0, cache, QueryBudget(None, time.monotonic()))
        result = sources.events([*range(599), *range(599)])
        assert len(result) == 599
        assert sources.query_count == 300  # Per owning shard, not each block.
        assert len(cache) <= 2
        with SnapshotAnalyzer(root, context_cache=cache) as analyzer:
            high = analyzer.execute_query("active_memory_callstack_at_event", {"event_id": 599, "top_n": -1})
            assert sum(r["block_count"] for r in high["rows"]) == 599
            assert high["scope"]["source_coverage"]["source_queries"] == 303  # Includes the bounded proof-owner probe.
            assert len(cache) <= 2
        # A single large shard specifically crosses the parameter batch bound.
        single = make_dataset(tmp_path / "wide", devices=(0,), slices=1)
        path = single / "device_0/slice_00000.db"
        count = SOURCE_BATCH_SIZE * 3 + 7
        with closing(sqlite3.connect(path)) as conn, conn:
            conn.executemany(
                "INSERT INTO trace_entry_0 VALUES (?,4,100,8,0,8,8,16,'wide')",
                [(i,) for i in range(2, count)],
            )
        raw = json.loads((single / "manifest.json").read_text())
        raw["eventsPerSlice"] = count
        raw["devices"]["0"]["eventCount"] = count
        raw["devices"]["0"]["slices"][0]["endEventId"] = count - 1
        (single / "manifest.json").write_text(json.dumps(raw))
        resolver = DatasetSourceResolver(
            DatasetResolver().inspect(single), 0, cache, QueryBudget(None, time.monotonic())
        )
        assert len(resolver.events([*range(count), *range(count)])) == count
        assert resolver.query_count == 4
    finally:
        cache.close()


def test_global_budget_counts_source_work_and_clears_sqlite_progress_handler(tmp_path, monkeypatch):
    root = case(tmp_path)
    cache = ContextCache(maxsize=1)
    service = QueryService(context_cache=cache)
    try:
        original = DatasetSourceResolver.read
        values = []

        def counted(self, path, sql, params=None):
            values.append(self.budget.remaining())
            return original(self, path, sql, params)

        monkeypatch.setattr(DatasetSourceResolver, "read", counted)
        from pt_snap_cli.core.dataset.lifecycle.dataset_lifecycle_connection import _AttachedSources

        original_attached = _AttachedSources.read

        def counted_attached(self, sql, params=None):
            values.append(self.sources.budget.remaining())
            return original_attached(self, sql, params)

        monkeypatch.setattr(_AttachedSources, "read", counted_attached)
        service.execute_query(
            "active_memory_callstack_at_event",
            {"event_id": 8},
            root,
            timeout_s=10,
            exact_total=True,
        )
        assert len(values) > 3 and values == sorted(values, reverse=True)
        expired = DatasetSourceResolver(
            DatasetResolver().inspect(root), 0, cache, QueryBudget(0.001, time.monotonic() - 1)
        )
        with pytest.raises(QueryTimeoutError):
            expired.events([0, 1])
        sources = DatasetSourceResolver(
            DatasetResolver().inspect(root), 0, cache, QueryBudget(0.0001, time.monotonic())
        )
        path = root / "device_0/slice_00000.db"
        with pytest.raises(QueryTimeoutError):
            sources.read(
                path,
                "WITH RECURSIVE n(x) AS (SELECT 1 UNION ALL SELECT x+1 FROM n WHERE x<10000000) SELECT SUM(x) FROM n",
            )
        sources = DatasetSourceResolver(DatasetResolver().inspect(root), 0, cache, QueryBudget(None, time.monotonic()))
        assert sources.read(path, "SELECT 1 AS okay") == [{"okay": 1}]
        service.close()
        assert len(cache) == 1  # Borrowed ownership, even following cancellation.
    finally:
        service.close()
        cache.close()


def test_report_uses_same_point_event_core_and_global_aggregates_stay_explicit(tmp_path):
    root = case(tmp_path)
    report = ReportService()
    try:
        attribution = report.event_attribution(8, root, limit=-1)
        with SnapshotAnalyzer(root) as analyzer:
            assert dataclasses.asdict(attribution) == analyzer.execute_query(
                "active_memory_callstack_at_event",
                {
                    "event_id": 8,
                    "include_static": True,
                    "min_size": 0,
                    "top_n": -1,
                    "stack_bytes": -1,
                },
            )
            for template in (
                "memory_peak",
                "allocator_gap",
                "leak_detection",
                "block",
                "callstack_analysis",
            ):
                assert analyzer.execute_query(template)["scope"]["range_complete"]
        peak = report.peak_memory_report(root)
        assert peak.event_id is not None and peak.source_coverage["allocation_source_complete"]
    finally:
        report.close()
