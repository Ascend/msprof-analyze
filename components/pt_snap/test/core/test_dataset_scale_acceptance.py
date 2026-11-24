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

"""Default-budget scale gates, separated from the small differential suite.

Synthetic SQL tests do not claim producer coverage. The final test imports a
trusted test-owned snapshot through a non-editable installed CLI/exporter, then
uses that installation's CLI and Python API. Supply PT_SNAP_ACCEPTANCE_WHEEL to
run it; this is not live PyTorch/NPU capture or upstream msinsight GUI acceptance.
"""

import json
import os
import sqlite3
import time
from contextlib import closing
from pathlib import Path

import pytest

from pt_snap_cli.api import SnapshotAnalyzer
from pt_snap_cli.core.common.errors import QueryExecutionError
from pt_snap_cli.core.dataset.dataset_contract import ACTION_NAMES, BLOCK_STATES
from pt_snap_cli.core.dataset.dataset_sources import QueryBudget
from pt_snap_cli.core.importing.msinsight_export import DEFAULT_CAPACITY
from test.core.dataset_lifecycle_fixtures import SCHEMA
from test.core.wheel_scale_acceptance import (
    API_QUERIES,
    WheelRuntime,
    query_cases,
    sha256,
    write_scale_source,
)
from test.test_dataset_focus import hashes

pytestmark = pytest.mark.slow


@pytest.fixture(autouse=True)
def isolate(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.delenv("PT_SNAP_DB_PATH", raising=False)
    monkeypatch.delenv("PT_SNAP_QUERY_TIMEOUT", raising=False)


def scale_dataset(root, count, capacity, stack):
    """Bounded occupancy, repeated addresses, real lifecycle-window membership."""
    (root / "device_0").mkdir(parents=True)
    slices = []
    for index, lo in enumerate(range(0, count, capacity)):
        hi = min(count, lo + capacity) - 1
        file = f"device_0/slice_{index:05d}.db"
        with closing(sqlite3.connect(root / file)) as conn, conn:
            conn.executescript(SCHEMA)
            conn.executemany(
                "INSERT INTO dictionary VALUES (?,?,?,?)",
                [("trace_entry_0", "action", str(i), name) for i, name in enumerate(ACTION_NAMES)]
                + [("block_0", "state", str(i), name) for i, name in BLOCK_STATES],
            )
            conn.executemany(
                "INSERT INTO trace_entry_0 VALUES (?,?,?,?,?,?,?,?,?)",
                (
                    (
                        at,
                        (4, 5, 6, 7)[at % 4],
                        1000 if at % 4 < 3 else 0,
                        16 if at % 4 < 3 else 0,
                        0,
                        16 if at % 4 == 0 else 0,
                        16 if at % 4 < 2 else 0,
                        4096,
                        stack,
                    )
                    for at in range(lo, hi + 1)
                ),
            )
            # Include a crossing lifecycle even when capacity is not a multiple of four.
            conn.executemany(
                "INSERT INTO block_0 VALUES (?,?,?,?,?,?,?)",
                (
                    (
                        alloc,
                        1000,
                        16,
                        16,
                        0 if alloc + 1 < lo else 1,
                        alloc,
                        alloc + 2 if alloc + 2 < count else -1,
                    )
                    for alloc in range(lo - lo % 4, hi + 1, 4)
                    if alloc + 2 >= lo
                ),
            )
            conn.execute("INSERT INTO trace_entry_0 VALUES (-1,2,1000,4096,0,999999,999999,999999,'boundary')")
            for metric in ("allocated", "active", "reserved"):
                conn.execute(f"CREATE INDEX trace_{metric} ON trace_entry_0 ({metric})")
        slices.append({"index": index, "startEventId": lo, "endEventId": hi, "file": file, "ready": True})
    (root / "manifest.json").write_text(
        json.dumps(
            {
                "schemaVersion": 1,
                "status": "complete",
                "sourceFile": "/synthetic/no-pickle",
                "cacheHash": "",
                "eventsPerSlice": capacity,
                "devices": {
                    "0": {
                        "eventCount": count,
                        "sliceCount": len(slices),
                        "readySlices": list(range(len(slices))),
                        "slices": slices,
                    }
                },
            }
        )
    )
    return root


@pytest.fixture(scope="module")
def default_scale(tmp_path_factory):
    assert DEFAULT_CAPACITY == 500_000
    budget = QueryBudget(None, time.monotonic())
    assert budget.max_work_rows == 100_000 and budget.max_work_bytes == 64 * 1024 * 1024
    return scale_dataset(
        tmp_path_factory.mktemp("default-scale") / "dataset",
        2 * DEFAULT_CAPACITY,
        DEFAULT_CAPACITY,
        "short",
    )


@pytest.mark.parametrize(
    "template,params,total",
    [
        ("memory_peak", {}, 1),
        ("allocator_gap", {}, 1),
        ("event", {"min_id": 0, "limit": 5}, 1_000_000),
        ("allocation", {"min_id": 0, "limit": 5}, 1_000_000),
        ("block", {"limit": 5}, 250_000),
        ("leak_detection", {"limit": 5}, 0),
        ("callstack_analysis", {"min_count": 1}, 1),
    ],
)
def test_two_default_shards_return_global_results_with_real_budgets(default_scale, template, params, total):
    before = hashes(default_scale)
    with SnapshotAnalyzer(default_scale) as analyzer:
        result = analyzer.execute_query(template, params, exact_total=True)
    assert result["total"] == total and result["total_is_exact"]
    assert result["returned"] == min(total, 5)
    if template == "memory_peak":
        assert result["rows"][0]["peak_active"] == 16
        assert result["rows"][0]["peak_active_event_id"] == 0
    elif template == "callstack_analysis":
        assert result["rows"][0]["alloc_count"] == 1_000_000
        assert result["rows"][0]["total_size"] == 12_000_000
    assert hashes(default_scale) == before


def test_real_default_row_budget_still_rejects_unbounded_materialization(default_scale):
    with (
        SnapshotAnalyzer(default_scale) as analyzer,
        pytest.raises(QueryExecutionError, match="budget"),
    ):
        analyzer.execute_query("event", {"min_id": 0, "limit": 100_001})


def test_long_stack_aggregate_and_small_page_succeed_but_full_output_is_byte_bounded(tmp_path):
    root = scale_dataset(tmp_path / "long-stacks", 10_000, 5_000, "x" * 8192)
    before = hashes(root)
    with SnapshotAnalyzer(root) as analyzer:
        peak = analyzer.execute_query("memory_peak")["rows"][0]
        assert peak["peak_active"] == 16
        grouped = analyzer.execute_query("callstack_analysis", {"min_count": 1})
        assert grouped["rows"][0]["alloc_count"] == 10_000
        page = analyzer.execute_query("event", {"min_id": 0, "limit": 5}, exact_total=True)
        assert page["returned"] == 5 and page["total"] == 10_000
        with pytest.raises(QueryExecutionError, match="budget"):
            analyzer.execute_query("event", {"min_id": 0, "limit": -1})
    assert hashes(root) == before


@pytest.fixture
def installed_runtime(tmp_path, request):
    wheel_value = os.environ.get("PT_SNAP_ACCEPTANCE_WHEEL")
    if not wheel_value:
        pytest.skip("Set PT_SNAP_ACCEPTANCE_WHEEL to test a clean-venv installed artifact")
    wheel = Path(wheel_value).resolve()
    assert wheel.is_file() and wheel.suffix == ".whl"
    evidence_dir = Path(os.environ.get("PT_SNAP_ACCEPTANCE_EVIDENCE_DIR", tmp_path / "evidence"))
    if request.node.name != "test_installed_trusted_producer_default_export_cli_and_api":
        evidence_dir /= request.node.name
    wheelhouse = os.environ.get("PT_SNAP_ACCEPTANCE_WHEELHOUSE")
    return WheelRuntime(tmp_path, wheel, evidence_dir.resolve(), Path(wheelhouse).resolve() if wheelhouse else None)


def _assert_scale_oracle(queries, count, boundary):
    """Independent arithmetic/geometry, not the same API used as its own oracle."""
    for name, value in queries.items():
        assert value["total_is_exact"], name
        assert value["returned"] == len(value["rows"]), name
        assert value["scope"]["boundary_events_included"] is False, name
        scope = value["scope"]
        if scope["kind"] == "event":
            assert scope["source_coverage"]["range_complete"], name
        else:
            assert scope["range_complete"], name
    peak = queries["memory_peak"]["rows"][0]
    assert peak == {
        "peak_allocated": 176,
        "peak_allocated_event_id": 3,
        "peak_active": 176,
        "peak_active_event_id": 3,
        "peak_reserved": 4096,
        "peak_reserved_event_id": 0,
    }
    gap = queries["allocator_gap"]["rows"][0]
    assert gap["reserved_active_gap_at_active_peak"] == 3920
    assert gap["active_at_reserved_peak"] == 112
    assert gap["all_peaks_same_event"] == 0
    for name in ("event", "allocation"):
        result = queries[name]
        assert [row["id"] for row in result["rows"]] == list(range(boundary - 2, boundary + 3))
        assert result["total"] == count
        assert result["has_more"] and result["truncated"]
        assert [row["active"] for row in result["rows"]] == [176, 176, 160, 176, 176]
    blocks = queries["block"]
    assert blocks["total"] == (count - 1) // 3 + 5
    assert [row["id"] for row in blocks["rows"]] == [0, 1, 2, 3, 6]
    assert blocks["has_more"] and blocks["truncated"]
    crossing = queries["crossing_block"]["rows"]
    assert len(crossing) == 1
    assert crossing[0]["allocEventId"] == boundary - 2
    assert crossing[0]["freeEventId"] == boundary
    assert crossing[0]["allocation_source"]["slice_index"] == 0
    assert crossing[0]["free_source"]["slice_index"] == 1
    assert crossing[0]["free_source"]["event"]["action"] == 6
    assert queries["freed_block_lifetime"]["rows"] == [
        {
            "lifetime_events": "<1k",
            "block_count": (count - 4) // 3,
            "size_bytes": 16 * ((count - 4) // 3),
        }
    ]
    leaks = queries["leak_detection"]
    assert leaks["total"] == 4 and not leaks["has_more"] and not leaks["truncated"]
    assert {row["allocEventId"] for row in leaks["rows"]} == {0, 1, 2, count - 1}
    assert all(row["terminal_survivor"] for row in leaks["rows"])
    grouped = queries["callstack_analysis"]["rows"]
    assert len(grouped) == 6
    assert sum(row["alloc_count"] for row in grouped) == count
    assert sum(row["total_size"] for row in grouped) == 16 * count + 64
    expected_stacks = {
        "retain_64": (1, 64),
        "retain_32": (1, 32),
        "retain_16": (1, 16),
        "alloc": ((count - 1) // 3, 16 * ((count - 1) // 3)),
        "free_requested": ((count - 4) // 3, 16 * ((count - 4) // 3)),
        "free_completed": ((count - 4) // 3, 16 * ((count - 4) // 3)),
    }
    assert {
        row["callstack"].rsplit(" ", 1)[1]: (row["alloc_count"], row["total_size"]) for row in grouped
    } == expected_stacks
    for name in ("block", "crossing_block", "leak_detection", "freed_block_lifetime"):
        coverage = queries[name]["scope"]["source_coverage"]
        assert coverage["lifecycles"] == (count - 1) // 3 + 5
        assert coverage["allocation_events_resolved"] == (count - 1) // 3 + 3
        assert coverage["free_events_resolved"] == (count - 4) // 3
        assert coverage["unproved_identities"] == 0 and coverage["allocation_source_complete"]
    assert queries["preexisting_live"]["rows"] == [{"block_count": 0, "size_bytes": 0}]
    before = queries["active_before"]["rows"]
    after = queries["active_after"]["rows"]
    assert len(before) == 6 and sum(row["size"] for row in before) == 176
    assert len(after) == 5 and sum(row["size"] for row in after) == 160
    assert [row["allocEventId"] for row in before if row["allocEventId"] >= 0] == [
        0,
        1,
        2,
        boundary - 2,
    ]
    assert [row["allocEventId"] for row in after if row["allocEventId"] >= 0] == [0, 1, 2]
    assert sum(row["size"] for row in before if row["category"] == "static") == 48
    page = queries["active_static_offset"]
    assert page["rows"] == before[1:4] and page["total"] == 6
    assert page["has_more"] and page["truncated"]
    dynamic = queries["active_dynamic_offset"]
    assert [row["id"] for row in dynamic["rows"]] == [1, 2] and dynamic["total"] == 4
    assert dynamic["has_more"] and dynamic["truncated"]
    groups = queries["active_groups"]["rows"]
    assert sum(row["size_bytes"] for row in groups) == 176
    assert sum(row["block_count"] for row in groups) == 6
    assert next(row for row in groups if row["category"] == "static")["size_bytes"] == 48


@pytest.mark.nightly
def test_installed_trusted_producer_default_export_cli_and_api(tmp_path, installed_runtime, record_property):
    runtime = installed_runtime
    assert DEFAULT_CAPACITY == 500_000
    count, boundary = 2 * DEFAULT_CAPACITY, DEFAULT_CAPACITY
    source = write_scale_source(runtime.cwd / "input.pkl", count)
    source_hash = sha256(source)
    (runtime.evidence_dir / "inputs.json").write_text(
        json.dumps(
            {
                "identity": runtime.identity,
                "wheel_sha256": runtime.wheel_hash,
                "source_sha256": source_hash,
                "events": count,
                "events_per_slice": boundary,
            },
            indent=2,
        )
    )
    imported = runtime.cli_json(
        "import",
        "import",
        source,
        "--format",
        "msinsight",
        "--output-dir",
        runtime.cwd / "exported",
        "--no-focus",
        "--json",
    )
    root = Path(imported["db_path"])
    manifest = json.loads((root / "manifest.json").read_text())
    assert manifest["eventsPerSlice"] == boundary
    assert manifest["devices"]["0"]["eventCount"] == count
    slices = manifest["devices"]["0"]["slices"]
    assert [(s["startEventId"], s["endEventId"]) for s in slices] == [
        (0, 499_999),
        (500_000, 999_999),
    ]
    before = hashes(root)
    (runtime.evidence_dir / "members-before.json").write_text(json.dumps(before, indent=2))
    # Preserve the old 500002-event boundary regression in the full-size workload:
    # first-shard pending-free allocation completes only in the second shard.
    for item in slices:
        with closing(sqlite3.connect((root / item["file"]).as_uri() + "?mode=ro", uri=True)) as conn:
            assert conn.execute("SELECT COUNT(*) FROM trace_entry_0 WHERE id>=0").fetchone()[0] == boundary
            assert (
                conn.execute("SELECT COUNT(*) FROM block_0 WHERE allocEventId>?", (item["endEventId"],)).fetchone()[0]
                == 0
            )
            assert (
                conn.execute(
                    "SELECT COUNT(*) FROM block_0 WHERE freeEventId>=0 AND freeEventId<?",
                    (item["startEventId"],),
                ).fetchone()[0]
                == 0
            )
            assert conn.execute("SELECT allocEventId,freeEventId FROM block_0 WHERE id=499998").fetchall() == [
                (499_998, 500_000)
            ]
    catalog = runtime.cli_json("capabilities", "capabilities", "--json")
    cases = query_cases(boundary)
    by_name = {entry["name"]: entry for entry in catalog["templates"]}
    assert {case["template"] for case in cases} == set(by_name)
    supported = {name for name, entry in by_name.items() if entry["dataset_support"]["supported"]}
    unsupported = set(by_name) - supported
    assert unsupported == {"event_frames"}
    cases_file = runtime.cwd / "cases.json"
    cases_file.write_text(json.dumps(cases))
    api = runtime.python_json("api", API_QUERIES, root, cases_file, boundary - 1)
    assert catalog["ok"] is True and catalog["schema_version"] == 1
    assert {key: catalog[key] for key in api["catalog"]} == api["catalog"]
    assert set(api["errors"]) == unsupported
    cli_queries = {}
    for case in cases:
        success = case["template"] in supported
        result = runtime.cli_json(
            f"query-{case['name']}",
            "query",
            root,
            "--template-use",
            case["template"],
            "--params",
            json.dumps(case["params"]),
            "--exact-total",
            "--json",
            expected=0 if success else 1,
        )
        if success:
            assert {key: result[key] for key in api["queries"][case["name"]]} == api["queries"][case["name"]]
            cli_queries[case["name"]] = result
        else:
            assert result["error"]["code"] == api["errors"][case["name"]]["code"] == "QUERY_FAILED"
            assert "Unsupported dataset-global" in result["error"]["message"]
    _assert_scale_oracle(cli_queries, count, boundary)
    peak = runtime.cli_json("report-peak", "report", "peak-memory", root, "--limit", "-1", "--json")
    assert peak == api["peak_report"]
    assert peak["event_id"] == 3 and peak["included_bytes"] == 176
    assert peak["active_bytes_at_event"] == 176 and peak["coverage_percent"] == 100
    assert peak["total_is_exact"] and not peak["truncated"]
    tree = runtime.cli_json(
        "report-tree",
        "report",
        "memory-tree",
        root,
        "--event-id",
        boundary - 1,
        "--json",
        expected=0,
    )
    assert tree["rows"] == api["tree_report"]["rows"]
    assert tree["rows"] == cli_queries["active_memory_frame_tree_at_event"]["rows"]
    assert tree["rows"][0]["size_bytes"] == 176
    assert sum(row["self_bytes"] for row in tree["rows"]) == 176
    assert hashes(root) == before
    assert sha256(source) == source_hash
    assert not (runtime.cwd / ".pt-snap").exists()
    assert not (runtime.home / ".config" / "pt-snap-cli").exists()
    evidence = {
        "scope": "test-owned snapshot -> clean-venv installed console import/export, query/report and API; no live collector or upstream GUI",
        "identity": runtime.identity,
        "wheel_sha256": runtime.wheel_hash,
        "source_sha256": source_hash,
        "members_sha256": before,
        "events": count,
        "events_per_slice": boundary,
        "slices": 2,
        "templates_supported": sorted(supported),
        "templates_expected_rejections": sorted(unsupported),
        "reports": {"peak-memory": "passed", "memory-tree": "passed"},
        "commands": runtime.commands,
        "read_only_verified": True,
    }
    record_property("dataset_acceptance", json.dumps(evidence))
    (runtime.evidence_dir / "acceptance.json").write_text(json.dumps(evidence, indent=2))


@pytest.mark.nightly
def test_installed_default_export_short_final_shard_boundary(installed_runtime, record_property):
    """Keep the original 500002-event final-two-row shard producer regression."""
    runtime = installed_runtime
    assert DEFAULT_CAPACITY == 500_000
    count, boundary = DEFAULT_CAPACITY + 2, DEFAULT_CAPACITY
    source = write_scale_source(runtime.cwd / "input.pkl", count)
    source_hash = sha256(source)
    imported = runtime.cli_json(
        "import",
        "import",
        source,
        "--format",
        "msinsight",
        "--output-dir",
        runtime.cwd / "exported",
        "--no-focus",
        "--json",
    )
    root = Path(imported["db_path"])
    manifest = json.loads((root / "manifest.json").read_text())
    assert manifest["eventsPerSlice"] == boundary
    device = manifest["devices"]["0"]
    assert device["eventCount"] == count and device["sliceCount"] == 2
    assert device["readySlices"] == [0, 1]
    slices = device["slices"]
    assert [(item["startEventId"], item["endEventId"]) for item in slices] == [
        (0, 499_999),
        (500_000, 500_001),
    ]
    before = hashes(root)
    for item, expected_count in zip(slices, (500_000, 2), strict=True):
        with closing(sqlite3.connect((root / item["file"]).as_uri() + "?mode=ro", uri=True)) as conn:
            assert conn.execute("SELECT COUNT(*),MIN(id),MAX(id) FROM trace_entry_0 WHERE id>=0").fetchone() == (
                expected_count,
                item["startEventId"],
                item["endEventId"],
            )
            assert conn.execute(
                "SELECT COUNT(*) FROM block_0 WHERE allocEventId>? OR (freeEventId>=0 AND freeEventId<?)",
                (item["endEventId"], item["startEventId"]),
            ).fetchone() == (0,)
            if item["index"] == 1:
                assert conn.execute("SELECT id,action FROM trace_entry_0 WHERE id>=0 ORDER BY id").fetchall() == [
                    (500_000, 6),
                    (500_001, 4),
                ]
                assert conn.execute("SELECT allocEventId,freeEventId FROM block_0 ORDER BY id").fetchall() == [
                    (-1, -1),
                    (-1, -1),
                    (0, -1),
                    (1, -1),
                    (2, -1),
                    (499_998, 500_000),
                    (500_001, -1),
                ]
    names = {"event", "crossing_block", "active_before", "active_after", "leak_detection"}
    cases = [case for case in query_cases(boundary) if case["name"] in names]
    cases_file = runtime.cwd / "cases.json"
    cases_file.write_text(json.dumps(cases))
    api = runtime.python_json("api", API_QUERIES, root, cases_file, boundary - 1)
    assert api["errors"] == {}
    results = {}
    for case in cases:
        result = runtime.cli_json(
            f"query-{case['name']}",
            "query",
            root,
            "--template-use",
            case["template"],
            "--params",
            json.dumps(case["params"]),
            "--exact-total",
            "--json",
        )
        assert {key: result[key] for key in api["queries"][case["name"]]} == api["queries"][case["name"]]
        assert result["total_is_exact"] and result["returned"] == len(result["rows"])
        results[case["name"]] = result
    tail = results["event"]
    assert tail["total"] == count and tail["returned"] == 4
    assert not tail["has_more"] and tail["truncated"]
    assert [(row["id"], row["action"], row["active"]) for row in tail["rows"]] == [
        (499_998, 4, 176),
        (499_999, 5, 176),
        (500_000, 6, 160),
        (500_001, 4, 176),
    ]
    crossing = results["crossing_block"]["rows"]
    assert len(crossing) == 1
    assert crossing[0]["allocEventId"] == 499_998 and crossing[0]["freeEventId"] == 500_000
    assert crossing[0]["allocation_source"]["slice_index"] == 0
    assert crossing[0]["free_source"]["slice_index"] == 1
    assert crossing[0]["free_source"]["event"]["id"] == 500_000
    assert crossing[0]["free_source"]["event"]["action"] == 6
    before_rows, after_rows = results["active_before"]["rows"], results["active_after"]["rows"]
    assert [row["allocEventId"] for row in before_rows if row["allocEventId"] >= 0] == [
        0,
        1,
        2,
        499_998,
    ]
    assert [row["allocEventId"] for row in after_rows if row["allocEventId"] >= 0] == [0, 1, 2]
    assert sum(row["size"] for row in before_rows) == 176
    assert sum(row["size"] for row in after_rows) == 160
    leak = results["leak_detection"]
    assert leak["total"] == 4 and not leak["has_more"] and not leak["truncated"]
    assert {row["allocEventId"] for row in leak["rows"]} == {0, 1, 2, 500_001}
    assert hashes(root) == before and sha256(source) == source_hash
    evidence = {
        "scope": "clean-wheel producer regression: one full default shard and a final two-event shard",
        "wheel_sha256": runtime.wheel_hash,
        "source_sha256": source_hash,
        "members_sha256": before,
        "events": count,
        "events_per_slice": boundary,
        "slice_event_counts": [500_000, 2],
        "identity": runtime.identity,
        "commands": runtime.commands,
        "read_only_verified": True,
    }
    record_property("dataset_boundary_acceptance", json.dumps(evidence))
    (runtime.evidence_dir / "acceptance.json").write_text(json.dumps(evidence, indent=2))
