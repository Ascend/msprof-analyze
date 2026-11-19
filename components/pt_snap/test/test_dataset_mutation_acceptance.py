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

"""A query may not publish rows/counts assembled from different dataset generations."""

import io
import json
import multiprocessing
import os
import sqlite3
import sys
from collections import Counter
from contextlib import closing, redirect_stderr, redirect_stdout
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from pt_snap_cli.api import SnapshotAnalyzer
from pt_snap_cli.core.common.errors import QueryTimeoutError
from pt_snap_cli.core.dataset import dataset_resolver as resolver
from pt_snap_cli.core.dataset.dataset_sources import DatasetSourceResolver
from test.core.dataset_lifecycle_fixtures import build
from test.dataset_concurrency_support import ISOLATED_ENV, WAIT_SECONDS
from test.test_dataset_focus import hashes


def params_for(shape):
    if shape == "count-only":
        return {"action": 4, "limit": 0}
    return {"order_by": "id", "order_dir": "ASC", "limit": -1}


def paused_query(root, adapter, shape, channel):
    """Observe the first completed shard operation in an actual CLI/API query."""
    original = DatasetSourceResolver.read
    observed = False

    def read(sources, path, statement, values=None):
        nonlocal observed
        result = original(sources, path, statement, values)
        selected = statement.startswith("SELECT MIN(id)") if shape == "count-only" else " WHERE t.id IN (" in statement
        if selected and not observed:
            observed = True
            channel.send({"stage": "first-shard-read", "member": path.name, "rows": len(result)})
            if not channel.poll(WAIT_SECONDS):
                raise TimeoutError("Parent did not release the mutation barrier")
            assert channel.recv() == "continue"
        return result

    try:
        with patch.object(DatasetSourceResolver, "read", read):
            if adapter == "api":
                try:
                    with SnapshotAnalyzer(root) as analyzer:
                        result = analyzer.execute_query("event", params_for(shape), exact_total=True)
                    outcome = {"status": "success", "payload": result}
                except Exception as exc:
                    outcome = {"status": "error", "type": type(exc).__name__, "message": str(exc)}
            else:
                from pt_snap_cli.cli import _safe_call

                sys.argv = [
                    "pt-snap",
                    "query",
                    str(root),
                    "--template-use",
                    "event",
                    "--params",
                    json.dumps(params_for(shape)),
                    "--exact-total",
                    "--json",
                ]
                stdout, stderr = io.StringIO(), io.StringIO()
                with redirect_stdout(stdout), redirect_stderr(stderr):
                    code = _safe_call()
                outcome = {"code": code, "stdout": stdout.getvalue(), "stderr": stderr.getvalue()}
        channel.send(outcome)
    finally:
        channel.close()


@pytest.fixture(autouse=True)
def isolate(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HOME", str(tmp_path))
    for name in ISOLATED_ENV:
        monkeypatch.delenv(name, raising=False)


@pytest.mark.parametrize("cache", ["strong", "immutable"])
@pytest.mark.parametrize("adapter", ["api", "cli-json"])
@pytest.mark.parametrize("shape", ["rows", "count-only"])
@pytest.mark.parametrize("mutate", [False, True], ids=["unchanged", "mutated"])
def test_query_rejects_mid_read_mutation_without_partial_payload(tmp_path, monkeypatch, cache, adapter, shape, mutate):
    if cache == "immutable":
        monkeypatch.setenv("PT_SNAP_DATASET_CACHE", "immutable")
    _, root, _, trace, _ = build(tmp_path, 7)
    before = hashes(root)
    context = multiprocessing.get_context("spawn")
    parent, child = context.Pipe()
    process = context.Process(target=paused_query, args=(root, adapter, shape, child))
    process.start()
    child.close()
    try:
        assert parent.poll(WAIT_SECONDS), "Query did not reach its first completed shard read"
        stage = parent.recv()
        assert stage == {
            "stage": "first-shard-read",
            "member": "slice_00000.db",
            "rows": 1 if shape == "count-only" else 10,
        }
        if mutate:
            # Test-owned artifacts only. The query is already admitted and has
            # consumed real data; update every shard before it can read another.
            statement = (
                "UPDATE trace_entry_0 SET action=7 WHERE id>=0"
                if shape == "count-only"
                else "UPDATE trace_entry_0 SET allocated=allocated+10000 WHERE id>=0"
            )
            for member in sorted(root.glob("device_0/*.db")):
                with closing(sqlite3.connect(member)) as connection, connection:
                    connection.execute(statement)
        expected_hashes = hashes(root)
        assert (expected_hashes != before) == mutate
        parent.send("continue")
        assert parent.poll(WAIT_SECONDS), "Query did not finish after barrier release"
        outcome = parent.recv()
        process.join(WAIT_SECONDS)
        assert process.exitcode == 0
        if mutate:
            if adapter == "api":
                assert outcome == {
                    "status": "error",
                    "type": "DatabaseSchemaError",
                    "message": "Dataset members changed during operation; retry.",
                }
            else:
                assert outcome["code"] == 1 and outcome["stdout"] == ""
                payload = json.loads(outcome["stderr"])
                assert payload["error"]["code"] == "DATABASE_SCHEMA_INVALID"
                assert payload["error"]["message"] == "Dataset members changed during operation; retry."
                assert not {"rows", "total", "returned", "scope"} & payload.keys()
        else:
            if adapter == "api":
                assert outcome["status"] == "success"
                payload = outcome["payload"]
            else:
                assert outcome["code"] == 0 and outcome["stderr"] == ""
                payload = json.loads(outcome["stdout"])
            expected_total = sum(event[1] == 4 for event in trace) if shape == "count-only" else len(trace)
            assert payload["total"] == expected_total and payload["total_is_exact"]
            assert payload["returned"] == (0 if shape == "count-only" else len(trace))
            if shape == "rows":
                assert [(row["id"], row["allocated"]) for row in payload["rows"]] == [
                    (event[0], event[5]) for event in trace
                ]
        # Readers must not modify either the pristine or deliberately changed bytes.
        assert hashes(root) == expected_hashes
    finally:
        parent.close()
        if process.is_alive():
            process.kill()
            process.join(WAIT_SECONDS)
        process.close()


@pytest.mark.parametrize("cache", ["strong", "immutable"])
@pytest.mark.parametrize("temperature", ["cold", "warm"])
@pytest.mark.parametrize("platform", ["native", "simulated-non-posix"])
def test_final_query_guard_hash_work_is_explicit(tmp_path, monkeypatch, cache, temperature, platform, record_property):
    if cache == "immutable":
        monkeypatch.setenv("PT_SNAP_DATASET_CACHE", "immutable")
    if platform == "simulated-non-posix":
        # Exercise the actual conservative policy on every CI OS without
        # changing pathlib's host platform or weakening any source guard.
        monkeypatch.setattr(resolver, "os", SimpleNamespace(name="nt", environ=os.environ))
    metadata_only = cache == "immutable" and resolver.os.name == "posix"
    _, root, _, _, _ = build(tmp_path, 7)
    counts, byte_counts = Counter(), Counter()
    original = resolver._hash_file

    def tracked(path, **kwargs):
        counts[path] += 1
        byte_counts[path] += path.stat().st_size
        return original(path, **kwargs)

    if temperature == "warm":
        resolver.DatasetResolver().inspect(root)
    with SnapshotAnalyzer(root) as analyzer:
        monkeypatch.setattr(resolver, "_hash_file", tracked)
        result = analyzer.execute_query("event", {"limit": 0}, exact_total=True)
    assert result["total"] == 80
    files = [root / "manifest.json", *root.glob("device_0/*.db")]
    # Default strong reuse is content-verified on every OS. Only explicit
    # immutable metadata reuse requires POSIX change times. Otherwise immutable
    # requests repeat cold admission AND the final guard hashes all bytes.
    if cache == "strong":
        member_scans = manifest_scans = 3 if temperature == "cold" else 2
    elif metadata_only:
        member_scans = int(temperature == "cold")
        manifest_scans = 2 * member_scans
    else:
        member_scans, manifest_scans = 2, 3
        assert root not in resolver._VALIDATED
    expected_counts = dict.fromkeys(files, member_scans) if member_scans else {}
    if manifest_scans:
        expected_counts[root / "manifest.json"] = manifest_scans
    assert dict(counts) == expected_counts
    assert sum(byte_counts.values()) == sum(path.stat().st_size * count for path, count in expected_counts.items())
    record_property("query_hash_calls", sum(counts.values()))
    record_property("query_hash_bytes", sum(byte_counts.values()))
    record_property("final_guard_extra_scans", int(not metadata_only))


def test_final_query_guard_uses_same_deadline_and_can_time_out(tmp_path, monkeypatch):
    _, root, _, _, _ = build(tmp_path, 7)
    original = resolver.ResolvedDataset.require_unchanged
    read = DatasetSourceResolver.read
    budgets = []

    def tracked(sources, *args, **kwargs):
        budgets.append(sources.budget)
        return read(sources, *args, **kwargs)

    def expire(dataset, budget=None):
        assert budgets and all(item is budget for item in budgets)
        budget.started -= budget.timeout_s + 1
        return original(dataset, budget)

    monkeypatch.setattr(DatasetSourceResolver, "read", tracked)
    monkeypatch.setattr(resolver.ResolvedDataset, "require_unchanged", expire)
    with SnapshotAnalyzer(root) as analyzer, pytest.raises(QueryTimeoutError):
        analyzer.execute_query("event", {"limit": 0}, exact_total=True, timeout_s=30)
