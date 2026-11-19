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

"""Guard seed profiles, coverage classification, and the differential oracle itself."""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from pt_snap_cli.api import SnapshotAnalyzer
from pt_snap_cli.core.common.errors import QueryExecutionError
from pt_snap_cli.core.dataset.dataset_support import DATASET_SUPPORT
from pt_snap_cli.query import registry
from test.core.dataset_differential_assertions import compare_case
from test.core.dataset_differential_cases import (
    FRAME_TEMPLATES,
    REGRESSION_SEEDS,
    SUPPORTED_TEMPLATES,
    UNSUPPORTED_TEMPLATES,
    QueryCase,
    capacity_for_seed,
    configured_seeds,
    query_cases,
)
from test.core.dataset_lifecycle_fixtures import EVENT_COUNT, build, shapes, timeline


@pytest.fixture(autouse=True)
def isolate(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.delenv("PT_SNAP_DB_PATH", raising=False)
    monkeypatch.delenv("PT_SNAP_QUERY_TIMEOUT", raising=False)


def test_default_and_nightly_banks_are_stable_unique_and_preserve_regressions():
    default = configured_seeds({})
    nightly = configured_seeds({"PT_SNAP_DIFFERENTIAL_SEEDS": "200"})
    assert len(default) == len(set(default)) == 20
    assert len(nightly) == len(set(nightly)) == 200
    assert default[:8] == REGRESSION_SEEDS
    assert nightly[:20] == default
    assert configured_seeds({"PT_SNAP_DIFFERENTIAL_SEEDS": "1"}) == (0,)
    assert configured_seeds({"PT_SNAP_DIFFERENTIAL_SEED": "0"}) == (0,)
    assert configured_seeds({"PT_SNAP_DIFFERENTIAL_SEED": "8191", "PT_SNAP_DIFFERENTIAL_SEEDS": "200"}) == (8191,)
    assert configured_seeds({"PT_SNAP_DIFFERENTIAL_SEED": str(2**63 - 1)}) == (2**63 - 1,)


@pytest.mark.parametrize(
    "name,values",
    [
        ("PT_SNAP_DIFFERENTIAL_SEEDS", ("", "0", "-1", "200.0", "true", "10001", "bad")),
        ("PT_SNAP_DIFFERENTIAL_SEED", ("", "-1", "1.5", "True", str(2**63), "1,2")),
    ],
)
def test_invalid_seed_configuration_fails_instead_of_silently_skipping(name, values):
    for value in values:
        with pytest.raises(ValueError, match=name):
            configured_seeds({name: value})


def test_query_bank_preserves_original_shapes_and_all_supported_templates(monkeypatch):
    # Text-only SQL differential fixtures cannot serve the structured single-DB
    # oracle; frame paths have their own real-import differential suite.
    assert set(DATASET_SUPPORT) == SUPPORTED_TEMPLATES | FRAME_TEMPLATES
    # Other suites legitimately register custom SQL. Check packaged discovery
    # in a fresh registry, and restore both singleton and identity bookkeeping.
    with monkeypatch.context() as patch:
        patch.setattr(registry.QueryRegistry, "_instance", None)
        patch.setattr(registry, "_registry", registry.QueryRegistry())
        patch.setattr(registry, "_packaged", {})
        registry._load_all_templates()
        assert set(registry.list_queries()) == SUPPORTED_TEMPLATES | FRAME_TEMPLATES | UNSUPPORTED_TEMPLATES
    for seed in configured_seeds({"PT_SNAP_DIFFERENTIAL_SEEDS": "200"}):
        capacity = capacity_for_seed(seed)
        cases = query_cases(seed, capacity)
        assert cases == query_cases(seed, capacity)
        assert [(q.template, q.params) for q in cases[:20]] == shapes(seed)
        assert {q.template for q in cases} == SUPPORTED_TEMPLATES
        assert {q.exact_total for q in cases} == {False, True}
        assert {q.params["include_static"] for q in cases if q.active_oracle} == {False, True}
        for q in cases:
            for key in ("event_id", "min_id", "max_id", "start_id", "end_id"):
                if key in q.params:
                    assert 0 <= q.params[key] < EVENT_COUNT
            if "min_id" in q.params and "max_id" in q.params:
                assert q.params["min_id"] <= q.params["max_id"]
            if "start_id" in q.params:
                assert q.params["start_id"] <= q.params["end_id"]
            if q.slice_index is not None:
                assert q.template in {"event", "allocation", "memory_peak", "allocator_gap"}
                assert 0 <= q.slice_index <= (EVENT_COUNT - 1) // capacity
        traces, blocks = timeline(seed)
        assert (traces, blocks) == timeline(seed)
        for at in range(EVENT_COUNT):
            alive = [b for b in blocks if b["alloc"] <= at and (b["free"] == -1 or b["free"] > at)]
            spans = sorted((b["address"], b["address"] + b["size"]) for b in alive)
            assert all(left[1] <= right[0] for left, right in zip(spans, spans[1:], strict=False)), (seed, at)
            assert sum(b["size"] for b in alive) == traces[at][6]
            assert sum(b["size"] for b in alive if b["request"] == -1 or b["request"] > at) == traces[at][5]


@pytest.mark.parametrize("layout", ("v1", "v2"))
@pytest.mark.parametrize("template", sorted(UNSUPPORTED_TEMPLATES))
def test_unsupported_catalog_templates_reject_separately(tmp_path, layout, template):
    _, dataset, _, _, _ = build(tmp_path, 0, layout=layout)
    params = {"event_id": 0}
    with SnapshotAnalyzer(dataset) as analyzer:
        with pytest.raises(QueryExecutionError, match="Unsupported dataset-global template"):
            analyzer.execute_query(template, params)


@pytest.mark.parametrize("errors", ((True, True), (True, False), (False, True)))
def test_any_unexpected_error_fails_and_records_both_outcomes(tmp_path, errors):
    calls = []

    def analyzer(index):
        def execute(*args, **kwargs):
            calls.append(index)
            if errors[index]:
                raise RuntimeError(f"injected failure {index}")
            return {"rows": []}

        return SimpleNamespace(execute_query=execute)

    with pytest.raises(AssertionError, match="(?s)unexpected query errors.*seed"):
        compare_case(analyzer(0), analyzer(1), QueryCase("error-check", "event"), tmp_path, 31, "v2", 2)
    assert calls == [0, 1]
    saved = json.loads((tmp_path / "differential-failure.json").read_text())
    assert len(saved["errors"]) == sum(errors)
    assert len(saved["outcomes"]) == 2 - sum(errors)
    assert saved["case"]["seed"] == 31 and saved["case"]["format"] == "v2"


def test_native_and_compat_fixtures_share_identical_generated_history(tmp_path):
    left = build(tmp_path, 7, layout="v1", capacity=3)
    right = build(tmp_path, 7, layout="v2", capacity=3)
    assert left[3:] == right[3:]
    first = json.loads((left[0] / "timeline.json").read_text())
    second = json.loads((right[0] / "timeline.json").read_text())
    assert {k: v for k, v in first.items() if k != "format"} == {k: v for k, v in second.items() if k != "format"}
    assert len(first["layout"]) == 27
    assert first["layout"][-1]["hi"] == EVENT_COUNT - 1
