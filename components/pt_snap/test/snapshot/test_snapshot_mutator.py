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

import unittest

from pt_snap_cli.snapshot.base import (
    Block,
    BlockState,
    DeviceSnapshot,
    Frame,
    Segment,
    TraceEntry,
)
from pt_snap_cli.snapshot.simulate import snapshot_mutator
from pt_snap_cli.snapshot.simulate.allocator_context import AllocatorContext
from pt_snap_cli.snapshot.simulate.simulated_caching_allocator import (
    SimulatedCachingAllocator,
)

from .helpers import assert_valid_segment, assert_valid_segments, assert_valid_snapshot


def make_snapshot(segments=None, trace_entries=None):
    snapshot = DeviceSnapshot()
    snapshot.segments = sorted(segments or [], key=lambda segment: (segment.address, segment.stream))
    snapshot.trace_entries = list(trace_entries or [])
    snapshot.total_allocated = sum(segment.allocated_size for segment in snapshot.segments)
    snapshot.total_activated = sum(segment.active_size for segment in snapshot.segments)
    snapshot.total_reserved = sum(segment.total_size for segment in snapshot.segments)
    snapshot.device = 0
    return snapshot


def make_segment(address=0x1000, total_size=0x1000, stream=0, blocks=None):
    segment = Segment(
        address=address,
        total_size=total_size,
        stream=stream,
        segment_type="large",
        allocated_size=0,
        active_size=0,
        blocks=[],
    )
    for block in blocks or []:
        block.segment_ptr = segment
        segment.blocks.append(block)
        segment.active_size += block.size
        if block.state == BlockState.ACTIVE_ALLOCATED:
            segment.allocated_size += block.size
    return segment


def make_block(address=0x1000, size=0x100, state=BlockState.ACTIVE_ALLOCATED):
    return Block(size=size, requested_size=size, address=address, state=state)


def make_event(action, addr, size, stream=0, idx=0):
    return TraceEntry(action=action, addr=addr, size=size, stream=stream, idx=idx)


def make_allocator(segments, trace_entries=None):
    return SimulatedCachingAllocator(AllocatorContext(make_snapshot(segments, trace_entries)))


def test_detach_block_returns_false_when_block_has_no_segment():
    snapshot = make_snapshot()
    block = make_block()

    assert snapshot_mutator.detach_block(snapshot, block) is False
    assert_valid_segments(snapshot.segments)


def test_detach_block_uses_supplied_index():
    first = make_block(0x1000, 0x100)
    second = make_block(0x1200, 0x100)
    segment = make_segment(0x1000, 0x1000, blocks=[first, second])
    snapshot = make_snapshot([segment])

    assert snapshot_mutator.detach_block(snapshot, second, 1) is True
    assert segment.blocks == [first]
    assert second.segment_ptr is None
    assert_valid_snapshot(snapshot)


def test_remove_segment_uses_supplied_index():
    first = make_segment(0x1000, 0x100)
    second_block = make_block(0x1200, 0x40)
    second = make_segment(0x1200, 0x100, blocks=[second_block])
    snapshot = make_snapshot([first, second])

    snapshot_mutator.remove_segment(snapshot, second, 1)

    assert snapshot.segments == [first]
    assert second_block.segment_ptr is None
    assert snapshot.total_reserved == 0x100


def test_promote_pending_free_block_returns_false_without_segment():
    snapshot = make_snapshot()
    block = make_block(state=BlockState.ACTIVE_PENDING_FREE)

    assert snapshot_mutator.promote_pending_free_block(snapshot, block) is False
    assert_valid_segments(snapshot.segments)


def test_merge_mapped_segment_merges_left_and_right_adjacent_segments_when_present():
    left = make_segment(0x1000, 0x100)
    right = make_segment(0x1300, 0x100)
    new_segment = make_segment(0x1100, 0x200)
    right_block = make_block(0x1300, 0x80)
    right_block.segment_ptr = right
    right.blocks.append(right_block)
    right.active_size = right_block.size
    right.allocated_size = right_block.size
    snapshot = make_snapshot([left, right])

    assert snapshot_mutator.merge_mapped_segment(snapshot, new_segment, 0, 1) is True
    assert len(snapshot.segments) == 1
    merged = snapshot.segments[0]
    assert merged.total_size == 0x400
    assert right_block.segment_ptr is merged
    assert_valid_segments(snapshot.segments)


def test_merge_mapped_segment_merges_right_adjacent_segment_without_left_neighbor():
    right = make_segment(0x1300, 0x100)
    new_segment = make_segment(0x1100, 0x200)
    right_block = make_block(0x1300, 0x80)
    right_block.segment_ptr = right
    right.blocks.append(right_block)
    right.active_size = right_block.size
    right.allocated_size = right_block.size
    snapshot = make_snapshot([right])

    assert snapshot_mutator.merge_mapped_segment(snapshot, new_segment, -1, 0) is True
    assert len(snapshot.segments) == 1
    merged = snapshot.segments[0]
    assert merged.address == 0x1100
    assert merged.total_size == 0x300
    assert right_block.segment_ptr is merged
    assert_valid_segments(snapshot.segments)


def test_merge_mapped_segment_returns_false_when_no_adjacent_segments_exist():
    snapshot = make_snapshot()
    new_segment = make_segment(0x1100, 0x200)

    assert snapshot_mutator.merge_mapped_segment(snapshot, new_segment, -1, -1) is False
    assert snapshot.segments == []
    assert_valid_segments(snapshot.segments)


def test_split_or_shrink_segment_uses_middle_split_branch():
    segment = make_segment(0x1000, 0x1000)
    segment.frames = [Frame.from_dict({"filename": "alloc.py", "line": 4, "name": "run"})]
    left_block = make_block(0x1000, 0x100)
    right_block = make_block(0x1800, 0x100)
    left_block.segment_ptr = segment
    right_block.segment_ptr = segment
    segment.blocks = [left_block, right_block]
    segment.active_size = left_block.size + right_block.size
    segment.allocated_size = left_block.size + right_block.size
    snapshot = make_snapshot([segment])

    assert snapshot_mutator.split_or_shrink_segment(snapshot, 0, 0x1400, 0x100) is True
    assert len(snapshot.segments) == 2
    assert all(part.frames is segment.frames for part in snapshot.segments)
    assert all(isinstance(part.frames[0], Frame) for part in snapshot.segments)
    assert_valid_segments(snapshot.segments)


def test_split_or_shrink_segment_preserves_raw_frames():
    raw_frames = [{"filename": "alloc.py", "line": 4, "name": "run"}]
    segment = make_segment(0x1000, 0x1000)
    segment._raw_frames = raw_frames
    snapshot = make_snapshot([segment])

    assert snapshot_mutator.split_or_shrink_segment(snapshot, 0, 0x1400, 0x100) is True
    assert len(snapshot.segments) == 2
    assert all(part._raw_frames is raw_frames for part in snapshot.segments)
    assert all(part.to_dict()["frames"] is raw_frames for part in snapshot.segments)


def test_increase_and_decrease_reserved_update_snapshot_totals():
    snapshot = make_snapshot()

    snapshot_mutator.increase_reserved(snapshot, 64)
    snapshot_mutator.decrease_reserved(snapshot, 24)

    assert snapshot.total_reserved == 40


class TestSnapshotMutatorState(unittest.TestCase):
    def test_attach_and_detach_block_keep_totals_consistent(self):
        snapshot = make_snapshot([])
        segment = make_segment(0x1000, 0x1000)
        snapshot_mutator.insert_segment(snapshot, segment)
        block = make_block(0x1200, 0x100)

        snapshot_mutator.attach_block(snapshot, segment, block, 0)

        self.assertIs(block.segment_ptr, segment)
        self.assertEqual(0x100, segment.active_size)
        self.assertEqual(0x100, segment.allocated_size)
        self.assertEqual(0x100, snapshot.total_activated)
        self.assertEqual(0x100, snapshot.total_allocated)
        assert_valid_snapshot(snapshot)

        self.assertTrue(snapshot_mutator.detach_block(snapshot, block))
        self.assertIsNone(block.segment_ptr)
        self.assertEqual([], segment.blocks)
        self.assertEqual(0, segment.active_size)
        self.assertEqual(0, segment.allocated_size)
        self.assertEqual(0, snapshot.total_activated)
        self.assertEqual(0, snapshot.total_allocated)
        assert_valid_snapshot(snapshot)

    def test_insert_and_remove_segment_keep_reserved_consistent(self):
        snapshot = make_snapshot([])
        segment = make_segment(0x2000, 0x400)

        snapshot_mutator.insert_segment(snapshot, segment)

        self.assertEqual(1, len(snapshot.segments))
        self.assertEqual(0x400, snapshot.total_reserved)
        assert_valid_snapshot(snapshot)

        snapshot_mutator.remove_segment(snapshot, segment)

        self.assertEqual([], snapshot.segments)
        self.assertEqual(0, snapshot.total_reserved)
        assert_valid_snapshot(snapshot)

    def test_alloc_block_updates_segment_and_snapshot_totals(self):
        segment = make_segment(0x1000, 0x1000)
        allocator = make_allocator([segment])
        allocator.ctx.set_current_undo_event(make_event("free", 0x1200, 0x100, idx=7))
        new_block = make_block(0x1200, 0x100)

        allocated = allocator.alloc_block(new_block)

        self.assertTrue(allocated)
        self.assertEqual(0x100, segment.active_size)
        self.assertEqual(0x100, segment.allocated_size)
        self.assertEqual(0x100, allocator.ctx.device_snapshot.total_activated)
        self.assertEqual(0x100, allocator.ctx.device_snapshot.total_allocated)
        self.assertEqual(7, new_block.free_event_idx)
        self.assertIs(new_block.segment_ptr, segment)
        assert_valid_segment(segment)
        assert_valid_snapshot(allocator.ctx.device_snapshot)

    def test_free_block_updates_segment_and_snapshot_totals(self):
        block = make_block(0x1200, 0x100)
        segment = make_segment(0x1000, 0x1000, blocks=[block])
        allocator = make_allocator([segment])
        event = make_event("alloc", 0x1200, 0x100, idx=8)

        freed = allocator.free_block(event)

        self.assertTrue(freed)
        self.assertEqual([], segment.blocks)
        self.assertEqual(0, segment.active_size)
        self.assertEqual(0, segment.allocated_size)
        self.assertEqual(0, allocator.ctx.device_snapshot.total_activated)
        self.assertEqual(0, allocator.ctx.device_snapshot.total_allocated)
        assert_valid_snapshot(allocator.ctx.device_snapshot)

    def test_active_block_promotes_pending_free_block(self):
        block = make_block(0x1200, 0x100, state=BlockState.ACTIVE_PENDING_FREE)
        segment = make_segment(0x1000, 0x1000, blocks=[block])
        allocator = make_allocator([segment])
        event = make_event("free_requested", 0x1200, 0x100)

        activated = allocator.active_block(event)

        self.assertTrue(activated)
        self.assertEqual(BlockState.ACTIVE_ALLOCATED, block.state)
        self.assertEqual(0x100, segment.allocated_size)
        self.assertEqual(0x100, allocator.ctx.device_snapshot.total_allocated)
        assert_valid_segment(segment)
        assert_valid_snapshot(allocator.ctx.device_snapshot)

    def test_workspace_flag_tolerates_missing_block_on_free(self):
        segment = make_segment(0x1000, 0x1000)
        allocator = make_allocator([segment])
        allocator.ctx.workspace_flag = True
        event = make_event("alloc", 0x1200, 0x100)

        tolerated = allocator.free_block(event)

        self.assertTrue(tolerated)
        self.assertEqual(0, allocator.ctx.device_snapshot.total_allocated)
        self.assertEqual(0, allocator.ctx.device_snapshot.total_activated)
        assert_valid_snapshot(allocator.ctx.device_snapshot)

    def test_alloc_or_map_segment_updates_reserved_for_non_merge(self):
        allocator = make_allocator([])
        allocator.ctx.set_current_undo_event(make_event("segment_free", 0x2000, 0x400, idx=5))
        segment = make_segment(0x2000, 0x400)

        allocated = allocator.alloc_or_map_segment(segment, merge=False)

        self.assertTrue(allocated)
        self.assertEqual(1, len(allocator.ctx.device_snapshot.segments))
        self.assertEqual(0x400, allocator.ctx.device_snapshot.total_reserved)
        self.assertEqual(5, segment.free_or_unmap_event_idx)
        assert_valid_snapshot(allocator.ctx.device_snapshot)

    def test_alloc_or_map_segment_merge_keeps_snapshot_invariants(self):
        left = make_segment(0x1000, 0x100)
        allocator = make_allocator([left])
        allocator.ctx.set_current_undo_event(make_event("segment_free", 0x1100, 0x80, idx=9))
        new_segment = make_segment(0x1100, 0x80)

        allocated = allocator.alloc_or_map_segment(new_segment, merge=True)

        self.assertTrue(allocated)
        self.assertEqual(1, len(allocator.ctx.device_snapshot.segments))
        self.assertEqual(0x180, allocator.ctx.device_snapshot.total_reserved)
        assert_valid_snapshot(allocator.ctx.device_snapshot)

    def test_alloc_or_map_segment_merge_finds_neighbors_across_streams(self):
        left = make_segment(0x1000, 0x100, stream=0)
        same_start_other_stream = make_segment(0x1000, 0x100, stream=1)
        right = make_segment(0x1200, 0x100, stream=0)
        same_end_other_stream = make_segment(0x1200, 0x100, stream=1)
        allocator = make_allocator([left, same_start_other_stream, right, same_end_other_stream])
        new_segment = make_segment(0x1100, 0x100, stream=0)

        assert allocator.alloc_or_map_segment(new_segment, merge=True) is True

        stream_zero_segments = [segment for segment in allocator.ctx.device_snapshot.segments if segment.stream == 0]
        assert len(stream_zero_segments) == 1
        assert stream_zero_segments[0].address == 0x1000
        assert stream_zero_segments[0].total_size == 0x300
        assert len(allocator.ctx.device_snapshot.segments) == 3
        assert allocator.ctx.device_snapshot.total_reserved == 0x500

    def test_alloc_or_map_segment_merge_scans_past_shorter_cross_stream_segment(self):
        left = make_segment(0x1000, 0x100, stream=0)
        shorter_other_stream = make_segment(0x1000, 0x80, stream=1)
        allocator = make_allocator([left, shorter_other_stream])
        new_segment = make_segment(0x1100, 0x100, stream=0)

        assert allocator.alloc_or_map_segment(new_segment, merge=True) is True

        stream_zero_segments = [segment for segment in allocator.ctx.device_snapshot.segments if segment.stream == 0]
        assert len(stream_zero_segments) == 1
        assert stream_zero_segments[0].address == 0x1000
        assert stream_zero_segments[0].total_size == 0x200

    def test_alloc_or_map_segment_merge_scans_shared_right_endpoint_group(self):
        other_stream = make_segment(0x1200, 0x100, stream=0)
        right = make_segment(0x1200, 0x100, stream=1)
        allocator = make_allocator([other_stream, right])
        new_segment = make_segment(0x1100, 0x100, stream=1)

        assert allocator.alloc_or_map_segment(new_segment, merge=True) is True

        stream_one_segments = [segment for segment in allocator.ctx.device_snapshot.segments if segment.stream == 1]
        assert len(stream_one_segments) == 1
        assert stream_one_segments[0].address == 0x1100
        assert stream_one_segments[0].total_size == 0x200

    def test_left_shrink_reinserts_segment_in_address_order(self):
        segment = make_segment(0x1000, 0x1000, stream=0)
        first_later_segment = make_segment(0x1800, 0x100, stream=1)
        second_later_segment = make_segment(0x1850, 0x100, stream=2)
        snapshot = make_snapshot([segment, first_later_segment, second_later_segment])

        assert snapshot_mutator.split_or_shrink_segment(snapshot, 0, 0x1000, 0x900) is True

        assert [(item.address, item.stream) for item in snapshot.segments] == [
            (0x1800, 1),
            (0x1850, 2),
            (0x1900, 0),
        ]

    def test_left_shrink_removes_segment_when_fully_consumed(self):
        segment = make_segment(0x1000, 0x100)
        snapshot = make_snapshot([segment])

        assert snapshot_mutator.split_or_shrink_segment(snapshot, 0, 0x1000, 0x100) is True
        assert snapshot.segments == []

    def test_unmap_segment_keeps_snapshot_invariants(self):
        segment = make_segment(0x1000, 0x200)
        allocator = make_allocator([segment])
        map_event = make_event("segment_map", 0x1000, 0x80, idx=10)

        unmapped = allocator.unmap_segment(map_event)

        self.assertTrue(unmapped)
        self.assertEqual(0x180, allocator.ctx.device_snapshot.total_reserved)
        assert_valid_snapshot(allocator.ctx.device_snapshot)
