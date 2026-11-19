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

"""Small, deterministic differential contracts; scale/export acceptance is separate."""

import copy
import dataclasses
import hashlib
import json
import sqlite3
import time
from collections import Counter
from contextlib import closing
from pathlib import Path

import pytest
from typer.testing import CliRunner

from pt_snap_cli.api import SnapshotAnalyzer
from pt_snap_cli.cli import app
from pt_snap_cli.core.analysis.query_service import QueryService
from pt_snap_cli.core.common.errors import QueryExecutionError, QueryTimeoutError
from pt_snap_cli.core.common.models import ImportOptions
from pt_snap_cli.core.dataset.dataset_contract import validate_dataset
from pt_snap_cli.core.dataset.dataset_sources import QueryBudget
from pt_snap_cli.core.dataset.lifecycle import dataset_lifecycle_scratch as scratch
from pt_snap_cli.core.dataset.lifecycle import dataset_lifecycle_sql as lifecycle_sql
from pt_snap_cli.core.dataset.query import dataset_attribution
from pt_snap_cli.core.importing.import_service import ImportService
from test.core.dataset_differential_assertions import compare_case
from test.core.dataset_differential_cases import capacity_for_seed, configured_seeds, query_cases
from test.core.dataset_lifecycle_fixtures import build, db, member
from test.core.test_dataset_attribution import case
from test.snapshot.test_sharded_replay import block, event, segment, write_source
from test.test_dataset_focus import hashes


@pytest.fixture(autouse=True)
def isolate(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.delenv("PT_SNAP_DB_PATH", raising=False)
    monkeypatch.delenv("PT_SNAP_QUERY_TIMEOUT", raising=False)


def common_rows(actual, expected, *, omit=()):
    """Ignore only dataset provenance and explicitly non-comparable observations."""
    fields = set(expected[0]) - set(omit) if expected else set()
    return [[{key: row[key] for key in fields} for row in rows] for rows in (actual, expected)]


def test_existing_attribution_fixture_has_only_actual_window_members(tmp_path):
    root = case(tmp_path, devices=(0,))
    observed = []
    for index in range(8):
        lo, hi = index * 2, index * 2 + 1
        with closing(sqlite3.connect(root / f"device_0/slice_{index:05d}.db")) as conn:
            blocks = conn.execute("SELECT id,allocEventId,freeEventId FROM block_0").fetchall()
        assert all(alloc == -1 or alloc <= hi for _, alloc, _ in blocks)
        assert all(free == -1 or free >= lo for _, _, free in blocks)
        observed.append({row[0] for row in blocks})
    assert 11 not in observed[0] and 11 in observed[5]
    assert 0 in observed[5] and 0 not in observed[6]
    assert -21 in set.intersection(*observed)


@pytest.mark.parametrize("seed", configured_seeds(), ids=lambda seed: f"seed-{seed}")
@pytest.mark.parametrize("layout", ("v1", "v2"))
def test_seeded_lifecycle_windows_match_single_database_strictly(tmp_path, monkeypatch, record_property, seed, layout):
    capacity = capacity_for_seed(seed)
    root, dataset, single, traces, blocks = build(tmp_path, seed, layout=layout, capacity=capacity)
    before = hashes(root)
    # Every seed contains these cases, rather than relying on probability.
    assert {b["stack"] for b in blocks} >= {None, "", "[missing callstack]", " \n"}
    assert sum(b["address"] == 1000 for b in blocks) == 2
    assert any(b["alloc"] == -1 and b["free"] == -1 for b in blocks)
    assert any(b["alloc"] == -1 and b["free"] >= 0 for b in blocks)
    assert any(b["request"] >= 0 and b["free"] > b["request"] for b in blocks)
    assert any(b["alloc"] >= 0 and b["free"] >= 0 and b["alloc"] // capacity != b["free"] // capacity for b in blocks)
    windows = json.loads((root / "timeline.json").read_text())["layout"]
    for entry in windows:
        expected = {b["id"] for b in blocks if member(b, entry["lo"], entry["hi"])}
        assert set(entry["block_ids"]) == expected
    scratch_builds = []
    original_build = scratch._ScratchSources.build

    def observed_build(database, items, maximum):
        result = original_build(database, items, maximum)
        scratch_builds.append(len(items))
        return result

    monkeypatch.setattr(scratch._ScratchSources, "build", observed_build)
    cases = query_cases(seed, capacity)
    with SnapshotAnalyzer(dataset) as actual, SnapshotAnalyzer(single) as reference:
        for query in cases:
            got = compare_case(actual, reference, query, root, seed, layout, capacity)
            if query.active_oracle:
                at = query.params["event_id"]
                expected = {
                    b["id"]
                    for b in blocks
                    if (b["alloc"] == -1 or b["alloc"] <= at)
                    and (b["free"] == -1 or b["free"] > at)
                    and (query.params["include_static"] or b["alloc"] >= 0)
                }
                context = (seed, layout, query)
                assert {r["id"] for r in got["rows"]} == expected, context
                assert sum(r["size"] for r in got["rows"]) == sum(b["size"] for b in blocks if b["id"] in expected), (
                    context
                )
                if query.params["include_static"]:
                    assert sum(r["size"] for r in got["rows"]) == traces[at][6], context
                assert got["scope"]["source_coverage"]["allocation_source_complete"], context
                for result in got["rows"]:
                    block = next(b for b in blocks if b["id"] == result["id"])
                    assert result["state_scope"] == "slice_observation", context
                    assert result["state"] == (0 if 0 <= block["request"] < (at // capacity) * capacity else 1), context
    # Native and compatibility inputs with more owners than SQLite can ATTACH
    # must actually build the bounded on-disk reducer; shard count alone is not evidence.
    if len(windows) > lifecycle_sql._attachment_limit() > 0:
        assert scratch_builds, (seed, layout, capacity, len(windows))
        assert max(scratch_builds) == len(windows)
    assert hashes(root) == before
    assert not any(root.rglob("*-wal")) and not any(root.rglob("*-journal"))
    summary = {
        "seed": seed,
        "format": layout,
        "capacity": capacity,
        "shards": len(windows),
        "comparisons": len(cases),
        "unexpected_errors": 0,
        "templates": sorted({q.template for q in cases}),
        "scratch_builds": len(scratch_builds),
    }
    (root / "coverage.json").write_text(json.dumps(summary, indent=2))
    for key, value in summary.items():
        record_property(key, value)


def rounding_case(tmp_path, sizes):
    root = tmp_path / "dataset"
    (root / "device_0").mkdir(parents=True)
    first, second = sizes
    total = first + second
    traces = [
        (0, 4, 100, first, 0, first, first, total, "first"),
        (1, 4, 200, second, 0, total, total, total, "second"),
    ]
    blocks = [(0, 100, first, first, 1, 0, -1), (1, 200, second, second, 1, 1, -1)]
    slices = []
    for index in range(2):
        file = f"device_0/slice_{index:05d}.db"
        db(root / file, [traces[index]], blocks[: index + 1])
        slices.append(
            {
                "index": index,
                "startEventId": index,
                "endEventId": index,
                "file": file,
                "ready": True,
            }
        )
    (root / "manifest.json").write_text(
        json.dumps(
            {
                "schemaVersion": 1,
                "status": "complete",
                "sourceFile": "/synthetic/no-pickle",
                "cacheHash": "",
                "eventsPerSlice": 1,
                "devices": {"0": {"eventCount": 2, "sliceCount": 2, "readySlices": [0, 1], "slices": slices}},
            }
        )
    )
    single = tmp_path / "single.db"
    db(single, traces, blocks)
    validate_dataset(root)
    return root, single


@pytest.mark.parametrize(
    "sizes",
    [
        (1, 127),
        (8 * 1024 * 1024, 127 * 8 * 1024 * 1024),
        (3, 1_999_997),
        (7, 1_999_993),
        (3, 1_999_996),
        (3, 1_999_998),
        (7, 1_999_992),
        (7, 1_999_994),
        (914_708_987_140_385, 1),
        (685_251_271_850_673, 1),
        (2**53 - 1, 128),
        (2**53 + 1, 128),
        (8 * 1024 * 1024 - 1, 1),
        (8 * 1024 * 1024 + 1, 1),
    ],
)
def test_half_near_half_and_large_values_match_actual_sqlite_rounding(tmp_path, sizes):
    root, single = rounding_case(tmp_path, sizes)
    before = hashes(tmp_path)
    with SnapshotAnalyzer(root) as dataset, SnapshotAnalyzer(single) as reference:
        params = {"event_id": 1, "top_n": -1}
        actual = dataset.execute_query("active_memory_callstack_at_event", params)["rows"]
        expected = reference.execute_query("active_memory_callstack_at_event", params)["rows"]
        left, right = common_rows(actual, expected)
        # SQLite versions can differ for decimal near-halves. The actual
        # standalone query is the oracle, never a decimal/string approximation.
        assert left == right
        if sizes == (1, 127):
            assert next(r for r in actual if r["size_bytes"] == 1)["percent_of_active_blocks"] == 0.7813
            assert next(r for r in actual if r["size_bytes"] == 127)["percent_of_active_blocks"] == 99.2188
        if sizes[0] == 8 * 1024 * 1024:
            first = next(r for r in actual if r["size_bytes"] == sizes[0])
            assert first["size_gib"] == first["requested_gib"] == 0.007813
    assert hashes(tmp_path) == before


@pytest.mark.parametrize("same_stack", [True, False], ids=["gib", "percentages"])
def test_rounding_int64_aggregate_overflow_is_a_domain_error(tmp_path, same_stack):
    root, single = rounding_case(tmp_path, (1, 1))
    for path in [single, *root.glob("device_0/*.db")]:
        with closing(sqlite3.connect(path)) as connection, connection:
            connection.execute("UPDATE block_0 SET size=?, requestedSize=?", (2**62, 2**62))
            if same_stack:
                connection.execute("UPDATE trace_entry_0 SET callstack='same'")
    validate_dataset(root)
    before = hashes(tmp_path)
    for path in (root, single):
        with SnapshotAnalyzer(path) as analyzer, pytest.raises(QueryExecutionError):
            analyzer.execute_query("active_memory_callstack_at_event", {"event_id": 1, "top_n": -1})
        result = CliRunner().invoke(
            app,
            [
                "query",
                str(path),
                "--template-use",
                "active_memory_callstack_at_event",
                "--params",
                '{"event_id": 1, "top_n": -1}',
                "--json",
            ],
        )
        assert result.exit_code == 1 and result.stdout == ""
        assert json.loads(result.stderr)["error"]["code"] == "QUERY_FAILED"
        assert "Traceback" not in result.stderr
    assert hashes(tmp_path) == before


@pytest.mark.parametrize("rounding_pass", [1, 2], ids=["gib", "percentages"])
def test_rounding_timeout_closes_scalar_connection_and_cursor(tmp_path, monkeypatch, rounding_pass):
    root, _ = rounding_case(tmp_path, (1, 127))
    # Exercise the retained ordered-frame/fallback scalar ownership path.
    monkeypatch.setattr(dataset_attribution, "reduce_active", lambda *args: None)
    connections, cursors = [], []
    connect = sqlite3.connect

    class TrackedCursor(sqlite3.Cursor):
        calls = 0
        closed = False

        def execute(self, *args, **kwargs):
            self.calls += 1
            return super().execute(*args, **kwargs)

        def close(self):
            self.closed = True
            super().close()

    class TrackedConnection(sqlite3.Connection):
        closed = False

        def cursor(self, *args, **kwargs):
            cursor = super().cursor(*args, factory=TrackedCursor, **kwargs)
            cursors.append(cursor)
            return cursor

        def close(self):
            self.closed = True
            super().close()

    def scalar_connect(database, *args, **kwargs):
        if database == ":memory:":
            connection = connect(database, *args, factory=TrackedConnection, **kwargs)
            connections.append(connection)
            return connection
        return connect(database, *args, **kwargs)

    budget = QueryBudget(None, time.monotonic())
    remaining = budget.remaining

    def expire_during_rounding():
        if len(connections) == rounding_pass and cursors[-1].calls == 1:
            raise QueryTimeoutError("rounding deadline expired")
        return remaining()

    monkeypatch.setattr(dataset_attribution.sqlite3, "connect", scalar_connect)
    monkeypatch.setattr(budget, "remaining", expire_during_rounding)
    service = QueryService()
    try:
        with pytest.raises(QueryTimeoutError, match="rounding deadline expired"):
            service.execute_query(
                "active_memory_callstack_at_event",
                {"event_id": 1, "top_n": -1},
                db_path=root,
                _budget=budget,
            )
    finally:
        service.close()
    assert len(connections) == len(cursors) == rounding_pass
    assert all(connection.closed for connection in connections)
    assert all(cursor.closed for cursor in cursors)
    for connection in connections:
        with pytest.raises(sqlite3.ProgrammingError, match="closed"):
            connection.execute("SELECT 1")
    for cursor in cursors:
        with pytest.raises(sqlite3.ProgrammingError, match="closed"):
            cursor.fetchone()


def test_native_ordered_frames_and_local_stack_collisions_use_full_identity(tmp_path):
    """Real native replay plus an explicitly attached optional-frame fixture.

    Standalone SQL supplies the common event/block oracle. Ordered group identity
    is checked independently against input frames, since standalone SQL is text-only.
    """
    first = {"filename": "a.py", "line": 1, "name": "a"}
    second = {"filename": "b.py", "line": 2, "name": "b"}
    frames = [
        [first, second, first],
        [second, first, second],
        [first, second, first],
        [{**first, "extra": {"native": True}}, second, first],
    ]
    sizes = [16, 32, 16, 64]
    addresses = [1000, 1016, 1048, 1064]
    events = [event("alloc", addr=addr, size=size) for addr, size in zip(addresses, sizes, strict=True)]
    for trace, stack in zip(events, frames, strict=True):
        trace["frames"] = stack
    data = {
        "segments": [segment(0, 128, [block(a, n, n) for a, n in zip(addresses, sizes, strict=True)])],
        "device_traces": [events, copy.deepcopy(events)],
    }
    data["segments"] += [{**copy.deepcopy(s), "device": 1} for s in data["segments"]]
    request = ImportOptions(write_source(tmp_path, data), tmp_path / "output", set_focus=False, events_per_slice=1)
    service = ImportService()
    root = service.import_snapshot(request).db_path
    single = service.import_snapshot(dataclasses.replace(request, events_per_slice=None)).db_path
    manifest = json.loads((root / "manifest.json").read_text())
    manifest["extensions"] = {"ptSnapOrderedFrames": {"version": 1}}
    for device in (0, 1):
        for index, item in enumerate(manifest["devices"][str(device)]["slices"]):
            path = root / item["file"]
            with closing(sqlite3.connect(path)) as conn, conn:
                local_id = conn.execute(
                    f"SELECT callstackId FROM trace_entry_{device} WHERE id=?", (index,)
                ).fetchone()[0]
                conn.execute("UPDATE callstack SET id=42 WHERE id=?", (local_id,))
                conn.execute(
                    f"UPDATE trace_entry_{device} SET callstackId=42 WHERE callstackId=?",
                    (local_id,),
                )
                conn.executescript(
                    "CREATE TABLE pt_snap_frame_coverage (eventId INTEGER PRIMARY KEY,frameCount INTEGER);"
                    "CREATE TABLE pt_snap_frame (eventId INTEGER,frameIndex INTEGER,frameJson TEXT,PRIMARY KEY(eventId,frameIndex));"
                )
                conn.execute("INSERT INTO pt_snap_frame_coverage VALUES (?,3)", (index,))
                conn.executemany(
                    "INSERT INTO pt_snap_frame VALUES (?,?,?)",
                    [(index, i, json.dumps(f)) for i, f in enumerate(frames[index])],
                )
            item["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    (root / "manifest.json").write_text(json.dumps(manifest))
    before = hashes(root)
    identities = []
    expected_groups = Counter()
    for stack, size in zip(frames, sizes, strict=True):
        expected_groups[json.dumps(stack, sort_keys=True)] += size
    with SnapshotAnalyzer(root) as dataset, SnapshotAnalyzer(single) as reference:
        for device in (0, 1):
            for at in range(4):
                actual_event = dataset.execute_query("event", {"id": at}, device_id=device)["rows"]
                expected_event = reference.execute_query("event", {"id": at}, device_id=device)["rows"]
                left, right = common_rows(actual_event, expected_event)
                assert left == right
                params = {"event_id": at}
                got = dataset.execute_query("active_blocks_at_event", params, device_id=device)["rows"]
                want = reference.execute_query("active_blocks_at_event", params, device_id=device)["rows"]
                left, right = common_rows(got, want, omit=("state",))
                assert left == right
                for row in got:
                    source = row["allocation_source"]
                    assert source["local_stack_id"] == 42
                    assert source["frames"] == frames[row["allocEventId"]]
                    assert source["frames_status"] == "ordered"
                params["top_n"] = -1
                grouped = dataset.execute_query("active_memory_callstack_at_event", params, device_id=device)
                assert grouped["scope"]["source_coverage"]["ordered_frames_complete"]
            rows = grouped["rows"]
            assert {json.dumps(r["frames"], sort_keys=True): r["size_bytes"] for r in rows} == expected_groups
            assert sorted(r["block_count"] for r in rows) == [1, 1, 2]
            identities.append({row["lifecycle_id"] for row in got})
    assert not identities[0] & identities[1]
    assert hashes(root) == before
