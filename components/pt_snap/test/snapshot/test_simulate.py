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

import logging
import os
import unittest
from collections import Counter
from pathlib import Path

import pytest

from pt_snap_cli.snapshot.base import BlockState
from pt_snap_cli.snapshot.simulate import SimulateDeviceSnapshot, SimulateHooker
from pt_snap_cli.snapshot.simulate.hooker_defs import AllocatorHooker
from pt_snap_cli.snapshot.simulate.snapshot_lookup import find_overlapping_segment
from pt_snap_cli.snapshot.util.file_util import load_pickle_to_dict
from pt_snap_cli.snapshot.util.logger import restore_logs, suppress_logs

from .golden_observations import FIXTURE_REPLAY_GOLDEN
from .helpers import FIXTURE_DIR, assert_valid_segments, assert_valid_snapshot


class ReplayEventHooker(SimulateHooker):
    def __init__(self, valid_interval=100):
        self.replay_count = 0
        self.valid_interval = valid_interval

    def pre_undo_event(self, wait4undo_event, current_snapshot):
        return True

    def post_undo_event(self, already_undo_event, current_snapshot):
        if self.replay_count % self.valid_interval == 0:
            assert_valid_segments(current_snapshot.segments)
        self.replay_count += 1
        return True


class ReplayBlockHooker(AllocatorHooker):
    def __init__(self, test_util):
        self.test_util = test_util
        self._segment = None
        self.pre_seg_allocated_size = 0
        self.pre_seg_active_size = 0
        self.pre_snapshot_total_allocated_size = 0
        self.pre_snapshot_total_active_size = 0

    def pre_replay_alloc_block(self, wait4alloc_block, current_snapshot):
        super().pre_replay_alloc_block(wait4alloc_block, current_snapshot)
        self.test_util.assertNotEqual(wait4alloc_block.state, BlockState.INACTIVE)
        segment_idx, self._segment = find_overlapping_segment(current_snapshot, wait4alloc_block.address)
        self.test_util.assertTrue(0 <= segment_idx < len(current_snapshot.segments))
        self.pre_seg_allocated_size = self._segment.allocated_size
        self.pre_seg_active_size = self._segment.active_size
        self.pre_snapshot_total_allocated_size = current_snapshot.total_allocated
        self.pre_snapshot_total_active_size = current_snapshot.total_activated

    def post_replay_alloc_block(self, allocated_block, current_snapshot):
        super().post_replay_alloc_block(allocated_block, current_snapshot)
        self.test_util.assertEqual(self.pre_seg_active_size + allocated_block.size, self._segment.active_size)
        self.test_util.assertEqual(
            self.pre_snapshot_total_active_size + allocated_block.size,
            current_snapshot.total_activated,
        )
        if allocated_block.state == BlockState.ACTIVE_ALLOCATED:
            self.test_util.assertEqual(
                self.pre_seg_allocated_size + allocated_block.size,
                self._segment.allocated_size,
            )
            self.test_util.assertEqual(
                self.pre_snapshot_total_allocated_size + allocated_block.size,
                current_snapshot.total_allocated,
            )


class TestSimulate(unittest.TestCase):
    snapshot_path = FIXTURE_DIR / "snapshot_1768383987920985470.pkl"
    expandable_path = FIXTURE_DIR / "snapshot_expandable.pkl"
    empty_cache_path = FIXTURE_DIR / "snapshot_with_empty_cache.pkl"
    expandable_empty_cache_path = FIXTURE_DIR / "snapshot_with_empty_cache_expandable.pkl"

    @classmethod
    def setUpClass(cls):
        if os.getenv("UT_VERBOSE_LOG") != "1":
            suppress_logs()

    @classmethod
    def tearDownClass(cls):
        restore_logs()

    @staticmethod
    def get_simulate_snapshot(snapshot_path: Path):
        return SimulateDeviceSnapshot(load_pickle_to_dict(snapshot_path), 0)

    def _assert_block_hook_replay(self, path):
        snapshot = self.get_simulate_snapshot(path)
        assert_valid_segments(snapshot.device_snapshot.segments)
        snapshot.register_allocator_hooker(ReplayBlockHooker(self))
        self.assertTrue(snapshot.replay())

    def _assert_event_hook_replay(self, path):
        snapshot = self.get_simulate_snapshot(path)
        snapshot.register_hooker(ReplayEventHooker())
        self.assertTrue(snapshot.replay())

    def test_block_hooker_in_snapshot(self):
        self._assert_block_hook_replay(self.snapshot_path)

    def test_block_hooker_in_expandable_snapshot(self):
        self._assert_block_hook_replay(self.expandable_path)

    def test_block_hooker_in_snapshot_with_empty_cache(self):
        self._assert_block_hook_replay(self.empty_cache_path)

    def test_block_hooker_in_expandable_snapshot_with_empty_cache(self):
        self._assert_block_hook_replay(self.expandable_empty_cache_path)

    def test_replay_snapshot(self):
        self._assert_event_hook_replay(self.snapshot_path)

    def test_replay_expandable_snapshot(self):
        self._assert_event_hook_replay(self.expandable_path)

    def test_replay_snapshot_with_empty_cache(self):
        self._assert_event_hook_replay(self.empty_cache_path)

    def test_replay_expandable_snapshot_with_empty_cache(self):
        self._assert_event_hook_replay(self.expandable_empty_cache_path)


class Hooker:
    def __init__(self, pre=True, post=True):
        self.pre = pre
        self.post = post
        self.calls = []

    def pre_undo_event(self, event, snapshot):
        self.calls.append(("pre", event.idx))
        return self.pre

    def post_undo_event(self, event, snapshot):
        self.calls.append(("post", event.idx))
        return self.post


class MinimalAllocatorHooker:
    pass


def make_snapshot_dict(action="alloc", with_segment=False):
    payload = {
        "segments": [],
        "device_traces": [[{"action": action, "addr": 1, "size": 1, "stream": 0, "frames": []}]],
    }
    if with_segment:
        payload["segments"] = [
            {
                "address": 1,
                "total_size": 16,
                "stream": 0,
                "segment_type": "small",
                "allocated_size": 0,
                "active_size": 0,
                "device": 0,
                "is_expandable": False,
                "frames": [],
                "blocks": [],
            }
        ]
    return payload


def _inactive_workspace_segment(addr, size, stream):
    return {
        "address": addr,
        "total_size": size,
        "stream": stream,
        "segment_type": "small",
        "allocated_size": 0,
        "active_size": 0,
        "device": 0,
        "is_expandable": False,
        "frames": [],
        "blocks": [
            {
                "size": size,
                "requested_size": size,
                "state": "inactive",
                "address": addr,
                "frames": [],
            }
        ],
    }


def _workspace_triplet(addr, size, stream):
    return [
        {
            "action": "workspace_snapshot",
            "addr": addr,
            "size": size,
            "stream": stream,
            "frames": [],
        },
        {
            "action": "segment_alloc",
            "addr": addr,
            "size": size,
            "stream": stream,
            "frames": [],
        },
        {"action": "alloc", "addr": addr, "size": size, "stream": stream, "frames": []},
    ]


def make_torch_npu_workspace_snapshot(
    *, addr=1000, size=4096, stream=1, segment_size=None, extra_segments=None, extra_events=None
):
    segment_size = size if segment_size is None else segment_size
    segments = [_inactive_workspace_segment(addr, segment_size, stream)]
    if extra_segments:
        segments.extend(extra_segments)
    events = _workspace_triplet(addr, size, stream)
    if extra_events:
        events.extend(extra_events)
    return {"segments": segments, "device_traces": [events]}


def _segment_by_addr_stream(snapshot, addr, stream):
    matches = [
        segment for segment in snapshot.device_snapshot.segments if segment.address == addr and segment.stream == stream
    ]
    assert len(matches) == 1
    return matches[0]


def assert_dump_time_workspace_pool(snapshot, *, addr=1000, size=4096, stream=1):
    assert snapshot.simulated_allocator_context.workspace_flag is True
    segment = _segment_by_addr_stream(snapshot, addr, stream)
    assert segment.allocated_size == size
    assert segment.active_size == size
    assert len(segment.blocks) == 1
    block = segment.blocks[0]
    assert block.state == BlockState.ACTIVE_ALLOCATED
    assert block.address == addr
    assert block.size == size
    assert_valid_snapshot(snapshot.device_snapshot)


def test_simulate_device_snapshot_raises_on_empty_snapshot():
    with pytest.raises(RuntimeError):
        SimulateDeviceSnapshot({}, 0)


def test_simulate_device_snapshot_sets_workspace_flag_from_first_event():
    snapshot = SimulateDeviceSnapshot(make_torch_npu_workspace_snapshot(), 0)
    device = snapshot.device_snapshot

    assert snapshot.simulated_allocator_context.workspace_flag is True
    assert_dump_time_workspace_pool(snapshot)
    assert device.total_allocated == 4096
    assert device.total_activated == 4096
    assert device.total_reserved == 4096


def test_raw_workspace_adaptation_preserves_segment_frames():
    frame = {"filename": "workspace.py", "line": 7, "name": "reserve"}
    data = make_torch_npu_workspace_snapshot()
    data["segments"][0]["frames"] = [frame]

    snapshot = SimulateDeviceSnapshot(data, 0, _raw_frames=True)

    block = snapshot.device_snapshot.segments[0].blocks[0]
    assert block._raw_frames == [frame]
    assert block.to_dict()["frames"] == [frame]


def test_simulate_register_unregister_hookers_and_allocator_hookers():
    snapshot = SimulateDeviceSnapshot(make_snapshot_dict(), 0)
    hooker = Hooker()
    allocator_hooker = MinimalAllocatorHooker()

    hook_id = snapshot.register_hooker(hooker)
    allocator_id = snapshot.register_allocator_hooker(allocator_hooker)
    snapshot.unregister_hooker(hook_id)
    snapshot.unregister_allocator_hooker(allocator_id)

    assert hook_id not in snapshot.hookers
    assert allocator_id not in snapshot.simulated_allocator.dispatcher.hookers


def test_simulate_replay_stops_when_pre_hook_returns_false():
    snapshot = SimulateDeviceSnapshot(make_snapshot_dict(), 0)
    hooker = Hooker(pre=False)
    snapshot.register_hooker(hooker)

    assert snapshot.replay() is False
    assert hooker.calls == [("pre", 0)]


def test_simulate_replay_stops_when_post_hook_returns_false():
    snapshot = SimulateDeviceSnapshot(make_snapshot_dict("free", with_segment=True), 0)
    hooker = Hooker(post=False)
    snapshot.register_hooker(hooker)

    assert snapshot.replay() is False
    assert hooker.calls == [("pre", 0), ("post", 0)]


def snapshot_observation(snapshot):
    device_snapshot = snapshot.device_snapshot
    return (
        len(device_snapshot.segments),
        sum(len(segment.blocks) for segment in device_snapshot.segments),
        len(device_snapshot.trace_entries),
        device_snapshot.total_allocated,
        device_snapshot.total_activated,
        device_snapshot.total_reserved,
    )


@pytest.mark.parametrize(("fixture_name", "device"), FIXTURE_REPLAY_GOLDEN)
def test_fixture_replay_matches_pre_relocation_golden(fixture_name, device):
    golden = FIXTURE_REPLAY_GOLDEN[(fixture_name, device)]
    snapshot = SimulateDeviceSnapshot(load_pickle_to_dict(FIXTURE_DIR / fixture_name), device)

    assert snapshot_observation(snapshot) == golden["initial"]
    assert Counter(event.action for event in snapshot.device_snapshot.trace_entries) == golden["actions"]
    assert_valid_snapshot(snapshot.device_snapshot)

    assert snapshot.replay() is True
    assert snapshot_observation(snapshot) == golden["final"]
    assert_valid_snapshot(snapshot.device_snapshot)


def test_multi_device_fixture_keeps_device_state_isolated():
    data = load_pickle_to_dict(FIXTURE_DIR / "snapshot_with_multi_devices.pkl")
    device_zero = SimulateDeviceSnapshot(data, 0)
    device_one = SimulateDeviceSnapshot(data, 1)
    device_one_before = snapshot_observation(device_one)

    assert device_zero.replay() is True

    assert snapshot_observation(device_one) == device_one_before
    assert snapshot_observation(device_zero) != snapshot_observation(device_one)


def test_minimal_workspace_input_corrects_dump_time_state_before_replay(caplog):
    snapshot = SimulateDeviceSnapshot(make_torch_npu_workspace_snapshot(), 0)

    assert_dump_time_workspace_pool(snapshot)
    with caplog.at_level(logging.WARNING, logger="ALLOCATOR"):
        assert snapshot.replay() is True
    assert "workspace scenario tolerance" not in caplog.text
    assert snapshot.device_snapshot.trace_entries == []
    assert snapshot.device_snapshot.segments == []
    assert snapshot.device_snapshot.total_allocated == 0
    assert snapshot.device_snapshot.total_activated == 0
    assert snapshot.device_snapshot.total_reserved == 0


def test_incomplete_workspace_marker_keeps_tolerance_flag_and_skip_behavior():
    snapshot = SimulateDeviceSnapshot(make_snapshot_dict("workspace_snapshot"), 0)

    assert snapshot.simulated_allocator_context.workspace_flag is True
    assert snapshot.replay() is True
    assert snapshot.device_snapshot.trace_entries == []


def test_workspace_adapt_multiple_stream_groups_before_replay():
    data = {
        "segments": [
            _inactive_workspace_segment(1000, 4096, 1),
            _inactive_workspace_segment(10000, 8192, 2),
        ],
        "device_traces": [_workspace_triplet(1000, 4096, 1) + _workspace_triplet(10000, 8192, 2)],
    }
    snapshot = SimulateDeviceSnapshot(data, 0)

    assert_dump_time_workspace_pool(snapshot, addr=1000, size=4096, stream=1)
    assert_dump_time_workspace_pool(snapshot, addr=10000, size=8192, stream=2)
    assert snapshot.device_snapshot.total_allocated == 12288
    assert snapshot.device_snapshot.total_activated == 12288


def test_workspace_adapt_warns_and_stops_when_segment_missing(caplog):
    data = {
        "segments": [_inactive_workspace_segment(2000, 8192, 2)],
        "device_traces": [_workspace_triplet(1000, 4096, 1) + _workspace_triplet(2000, 8192, 2)],
    }
    with caplog.at_level(logging.WARNING, logger="LOAD"):
        snapshot = SimulateDeviceSnapshot(data, 0)

    assert "Workspace snapshot at addr 1000 (stream 1) not found" in caplog.text
    later = _segment_by_addr_stream(snapshot, 2000, 2)
    assert later.allocated_size == 0
    assert later.active_size == 0
    assert later.blocks == []


def test_workspace_adapt_keeps_earlier_group_when_later_group_is_missing(caplog):
    data = {
        "segments": [
            _inactive_workspace_segment(1000, 4096, 1),
            _inactive_workspace_segment(10000, 8192, 2),
        ],
        "device_traces": [_workspace_triplet(1000, 4096, 1) + _workspace_triplet(2000, 8192, 2)],
    }
    with caplog.at_level(logging.WARNING, logger="LOAD"):
        snapshot = SimulateDeviceSnapshot(data, 0)

    assert_dump_time_workspace_pool(snapshot, addr=1000, size=4096, stream=1)
    later = _segment_by_addr_stream(snapshot, 10000, 2)
    assert later.allocated_size == 0
    assert later.active_size == 0
    assert later.blocks == []
    assert snapshot.device_snapshot.total_allocated == 4096
    assert snapshot.device_snapshot.total_activated == 4096
    assert snapshot.device_snapshot.total_reserved == 12288
    warnings = [record for record in caplog.records if record.levelno == logging.WARNING]
    assert len(warnings) == 1
    assert "Workspace snapshot at addr 2000 (stream 2) not found" in caplog.text


def test_workspace_adapt_warns_and_skips_when_size_mismatches(caplog):
    data = make_torch_npu_workspace_snapshot(size=4096, segment_size=8192)
    with caplog.at_level(logging.WARNING, logger="LOAD"):
        snapshot = SimulateDeviceSnapshot(data, 0)

    assert "does not match segment total_size" in caplog.text
    segment = _segment_by_addr_stream(snapshot, 1000, 1)
    assert segment.allocated_size == 0
    assert segment.active_size == 0
    assert segment.blocks == []
    assert snapshot.device_snapshot.total_allocated == 0
    assert snapshot.simulated_allocator_context.workspace_flag is True


def test_workspace_adapt_skips_inconsistent_triplet_so_replay_keeps_tolerance(caplog):
    data = make_torch_npu_workspace_snapshot()
    data["device_traces"][0][2]["size"] = 8192
    with caplog.at_level(logging.WARNING):
        snapshot = SimulateDeviceSnapshot(data, 0)

    segment = _segment_by_addr_stream(snapshot, 1000, 1)
    assert segment.allocated_size == 0
    assert segment.blocks == []
    assert "internally inconsistent" in caplog.text
    assert snapshot.replay() is True
    assert "workspace scenario tolerance" in caplog.text


def test_workspace_adapt_skips_when_segment_still_has_live_blocks(caplog):
    data = {
        "segments": [
            {
                "address": 1000,
                "total_size": 4096,
                "stream": 1,
                "segment_type": "small",
                "allocated_size": 1024,
                "active_size": 1024,
                "device": 0,
                "is_expandable": False,
                "frames": [],
                "blocks": [
                    {
                        "size": 1024,
                        "requested_size": 1024,
                        "state": "active_allocated",
                        "address": 1000,
                        "frames": [],
                    },
                    {
                        "size": 3072,
                        "requested_size": 3072,
                        "state": "inactive",
                        "address": 2048,
                        "frames": [],
                    },
                ],
            }
        ],
        "device_traces": [
            _workspace_triplet(1000, 4096, 1)
            + [{"action": "alloc", "addr": 1000, "size": 1024, "stream": 1, "frames": []}]
        ],
    }
    with caplog.at_level(logging.WARNING, logger="LOAD"):
        snapshot = SimulateDeviceSnapshot(data, 0)

    segment = _segment_by_addr_stream(snapshot, 1000, 1)
    assert len(segment.blocks) == 1
    assert segment.blocks[0].size == 1024
    assert segment.blocks[0].state == BlockState.ACTIVE_ALLOCATED
    assert segment.allocated_size == 1024
    assert snapshot.device_snapshot.total_allocated == 1024
    assert "still has 1 live block" in caplog.text


def test_simulate_replay_skips_oom_event_loaded_without_addr():
    snapshot = SimulateDeviceSnapshot(
        {
            "segments": [],
            "device_traces": [[{"action": "oom", "size": 1024, "device_free": 2048, "frames": []}]],
        },
        0,
    )

    assert [event.action for event in snapshot.device_snapshot.trace_entries] == ["oom"]
    assert snapshot.device_snapshot.trace_entries[0].addr == -1
    assert snapshot.replay() is True
    assert snapshot.device_snapshot.trace_entries == []
