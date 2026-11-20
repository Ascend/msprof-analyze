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

"""A full zero-sized inner rank window remains conservative until exact COUNT."""

import json
from pathlib import Path

import pytest

from pt_snap_cli.api import SnapshotAnalyzer
from pt_snap_cli.core.dataset.dataset_resolver import DatasetResolver
from pt_snap_cli.core.dataset.query import dataset_attribution
from test.core.dataset_lifecycle_fixtures import db, native_dataset, row


@pytest.fixture(autouse=True)
def isolate(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.delenv("PT_SNAP_DB_PATH", raising=False)
    monkeypatch.delenv("PT_SNAP_QUERY_TIMEOUT", raising=False)


def zero_rank_pair(tmp_path, layout, kind):
    """Small explicit empty/static/dynamic/mixed histories, independent of RNG."""
    dataset = tmp_path / "dataset"
    (dataset / "device_0").mkdir(parents=True)
    static = {
        "id": -1,
        "address": 100,
        "size": 16,
        "requestedSize": 16,
        "alloc": -1,
        "free": -1,
        "stack": None,
    }
    dynamic = {
        "id": 0,
        "address": 200,
        "size": 32,
        "requestedSize": 32,
        "alloc": 0,
        "free": -1,
        "stack": "dynamic",
    }
    blocks = {"empty": [], "static": [static], "dynamic": [dynamic], "mixed": [static, dynamic]}[kind]
    active = sum(b["size"] for b in blocks)
    trace = [
        (0, 4, 200, 32, 0, active, active, 256, "dynamic"),
        (1, 7, 0, 0, 0, active, active, 256, None),
    ]
    rows = [row(b, 1) for b in blocks]
    slices = []
    for index in range(2):
        file = f"device_0/slice_{index:05d}.db"
        db(dataset / file, [trace[index]], rows)
        slices.append(
            {
                "index": index,
                "startEventId": index,
                "endEventId": index,
                "file": file,
                "ready": True,
            }
        )
    manifest = {
        "schemaVersion": 1,
        "status": "complete",
        "sourceFile": "/synthetic/no-pickle",
        "cacheHash": "",
        "eventsPerSlice": 1,
        "devices": {"0": {"eventCount": 2, "sliceCount": 2, "readySlices": [0, 1], "slices": slices}},
    }
    (dataset / "manifest.json").write_text(json.dumps(manifest))
    single = tmp_path / "single.db"
    db(single, trace, rows)
    if layout == "v2":
        native_dataset(dataset, single, trace, blocks, manifest, 0, 1)
    assert DatasetResolver().inspect(dataset).callstack_layout == layout
    return dataset, single


@pytest.mark.parametrize("layout", ("v1", "v2"))
@pytest.mark.parametrize("kind", ("empty", "static", "dynamic", "mixed"))
@pytest.mark.parametrize("route", ("sql", "fallback"))
def test_zero_rank_is_conservative_until_exact_count(tmp_path, monkeypatch, layout, kind, route):
    dataset, single = zero_rank_pair(tmp_path, layout, kind)
    original_reduce = dataset_attribution.reduce_active
    calls = []

    def reduce(*args):
        calls.append(route)
        if route == "fallback":
            return None
        result = original_reduce(*args)
        assert result is not None
        return result

    monkeypatch.setattr(dataset_attribution, "reduce_active", reduce)
    with SnapshotAnalyzer(dataset) as actual, SnapshotAnalyzer(single) as reference:
        for include_static in (False, True):
            params = {"event_id": 1, "top_n": 0, "include_static": include_static}
            dynamic = int(kind in ("dynamic", "mixed"))
            static = int(include_static and kind in ("static", "mixed"))
            for exact in (False, True):
                got = actual.execute_query("active_memory_callstack_at_event", params, exact_total=exact)
                want = reference.execute_query("active_memory_callstack_at_event", params, exact_total=exact)
                expected = {
                    "returned": static,
                    "total": static + dynamic if exact else static,
                    "has_more": bool(dynamic) if exact else True,
                    "truncated": bool(dynamic) if exact else True,
                    "total_is_exact": exact,
                }
                for result in (got, want):
                    assert {key: result[key] for key in expected} == expected
                    assert all(r["category"] == "static" for r in result["rows"])
                keys = set(want["rows"][0]) if want["rows"] else set()
                assert [{k: r[k] for k in keys} for r in got["rows"]] == want["rows"]
    assert calls == [route] * 4
