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

import copy

import pytest

from pt_snap_cli.core.splitting import sharded_replay_service
from pt_snap_cli.core.splitting.sharded_replay_service import ShardedReplayService
from pt_snap_cli.snapshot.tools.adaptors import sharded_replay

from ..snapshot.test_sharded_replay import lifecycle_data, write_source


def test_source_loaded_once_and_one_simulator_per_selected_device(tmp_path, monkeypatch):
    data = lifecycle_data()
    data["device_traces"].append(copy.deepcopy(data["device_traces"][0]))
    data["segments"] += [{**copy.deepcopy(segment), "device": 1} for segment in data["segments"]]
    source = write_source(tmp_path, data)
    loads, devices = [], []
    load = sharded_replay_service.load_snapshot_representation
    simulator = sharded_replay.SimulateDeviceSnapshot

    def counted_load(path):
        loads.append(path)
        return load(path)

    def counted_simulator(data, device, **kwargs):
        devices.append(device)
        return simulator(data, device, **kwargs)

    monkeypatch.setattr(sharded_replay_service, "load_snapshot_representation", counted_load)
    monkeypatch.setattr(sharded_replay, "SimulateDeviceSnapshot", counted_simulator)
    result = ShardedReplayService().stage(source, tmp_path / "stage", events_per_slice=1)
    assert loads == [source]
    assert devices == [0, 1]
    assert result.layout == "native-v2" and result.omitted_devices == ()
    assert len(result.slices) == 18


@pytest.mark.parametrize("capacity", [0, -1, True, 1.5])
def test_invalid_capacity_before_load_or_staging(tmp_path, capacity):
    with pytest.raises(ValueError, match="events_per_slice"):
        ShardedReplayService().stage(tmp_path / "missing", tmp_path / "stage", events_per_slice=capacity)
    assert not (tmp_path / "stage").exists()


@pytest.mark.parametrize("device", [-1, True, 1.5, 5])
def test_invalid_or_missing_device_never_creates_stage(tmp_path, device):
    source = write_source(tmp_path, lifecycle_data())
    with pytest.raises(ValueError):
        ShardedReplayService().stage(source, tmp_path / "stage", events_per_slice=2, device=device)
    assert not (tmp_path / "stage").exists()


def test_omitted_empty_devices_disclosed(tmp_path):
    data = lifecycle_data()
    data["device_traces"].append([])
    result = ShardedReplayService().stage(
        write_source(tmp_path, data), tmp_path / "stage", events_per_slice=2, device=0
    )
    assert result.omitted_devices == (1,)


def test_empty_static_only_and_existing_stage_rejected(tmp_path):
    source = write_source(tmp_path, {"segments": [], "device_traces": [[]]})
    with pytest.raises(ValueError, match="trace events"):
        ShardedReplayService().stage(source, tmp_path / "stage", events_per_slice=2)
    existing = tmp_path / "existing"
    existing.mkdir()
    marker = existing / "owner.txt"
    marker.write_text("preserve")
    with pytest.raises(FileExistsError):
        ShardedReplayService().stage(source, existing, events_per_slice=2)
    assert marker.read_text() == "preserve"


def test_symlink_and_dangling_stage_rejected(tmp_path):
    (tmp_path / "actual").mkdir()
    for name, target in [("link", "actual"), ("dangling", "missing")]:
        (tmp_path / name).symlink_to(target)
        with pytest.raises(ValueError, match="non-symlink"):
            ShardedReplayService().stage(tmp_path / "input", tmp_path / name, events_per_slice=1)
    with pytest.raises(ValueError, match="non-symlink"):
        ShardedReplayService().stage(tmp_path / "input", tmp_path / "link" / "child", events_per_slice=1)


@pytest.mark.parametrize("ids", [[0, 0], [1, 0], [-1, 0]])
def test_invalid_native_ids_rejected_without_ready_result(tmp_path, ids):
    data = {
        "segments": [],
        "device_traces": [[{"id": value, "action": "oom", "frames": []} for value in ids]],
    }
    with pytest.raises(ValueError, match="event IDs"):
        ShardedReplayService().stage(write_source(tmp_path, data), tmp_path / "stage", events_per_slice=1)
    assert not list((tmp_path / "stage").iterdir())
