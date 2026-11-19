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

"""Fast independent checks for the nightly clean-wheel scale workload/oracle."""

import json
from pathlib import Path

from pt_snap_cli.api import SnapshotAnalyzer
from pt_snap_cli.core.common.models import ImportOptions
from pt_snap_cli.core.importing.import_service import ImportService
from pt_snap_cli.query import registry
from pt_snap_cli.snapshot.representation import load_snapshot_representation
from pt_snap_cli.snapshot.simulate import SimulateDeviceSnapshot
from test.core.test_dataset_scale_acceptance import _assert_scale_oracle
from test.core.wheel_scale_acceptance import query_cases, sha256, write_scale_source
from test.snapshot.helpers import assert_valid_snapshot


def test_scale_workload_is_replay_valid_at_every_event(tmp_path):
    source = write_scale_source(tmp_path / "input.pkl", 100)
    before = sha256(source)
    simulator = SimulateDeviceSnapshot(load_snapshot_representation(source), 0)
    for remaining in range(100, -1, -1):
        assert simulator.replay_until(remaining)
        assert_valid_snapshot(simulator.device_snapshot)
        expected = (
            (112, 144, 160)[remaining - 1]
            if 1 <= remaining <= 3
            else (48 if remaining == 0 else 160 + (16 if remaining % 3 != 0 else 0))
        )
        assert simulator.device_snapshot.total_activated == expected
    assert sha256(source) == before


def test_small_scale_uses_same_independent_oracle_and_catalog(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    for name in ("PT_SNAP_DB_PATH", "PT_SNAP_QUERY_TIMEOUT"):
        monkeypatch.delenv(name, raising=False)
    # Other contract tests may register custom queries. Give this source-level
    # smoke its own packaged catalog; the wheel subprocess always starts clean.
    monkeypatch.setattr(registry._registry, "_queries", {})
    monkeypatch.setattr(registry._registry, "_factories", {})
    monkeypatch.setattr(registry, "_packaged", {})
    registry._load_all_templates()
    source = write_scale_source(tmp_path / "input.pkl", 100)
    imported = ImportService().import_snapshot(
        ImportOptions(
            source,
            output_dir=tmp_path / "exported",
            format="msinsight",
            events_per_slice=50,
            set_focus=False,
        )
    )
    manifest = json.loads((imported.db_path / "manifest.json").read_text())
    assert manifest["devices"]["0"]["eventCount"] == 100
    with SnapshotAnalyzer(imported.db_path) as analyzer:
        catalog = {entry["name"]: entry for entry in analyzer.list_capabilities()["templates"]}
        cases = query_cases(50)
        assert {case["template"] for case in cases} == set(catalog)
        values = {
            case["name"]: analyzer.execute_query(case["template"], case["params"], exact_total=True)
            for case in cases
            if catalog[case["template"]]["dataset_support"]["supported"]
        }
    _assert_scale_oracle(values, 100, 50)
