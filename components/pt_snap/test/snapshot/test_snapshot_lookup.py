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

from pt_snap_cli.snapshot.base import Block, BlockState, DeviceSnapshot, Segment
from pt_snap_cli.snapshot.simulate.snapshot_lookup import (
    find_block,
    find_gap_for_alloc_block,
    find_overlapping_segment,
    find_segment,
    is_valid_sub_block,
)


class TestSnapshotLookup(unittest.TestCase):
    @staticmethod
    def make_snapshot(segments: list[Segment]) -> DeviceSnapshot:
        snapshot = DeviceSnapshot()
        snapshot.segments = sorted(segments, key=lambda segment: (segment.address, segment.stream))
        snapshot.trace_entries = []
        snapshot.total_allocated = sum(segment.allocated_size for segment in snapshot.segments)
        snapshot.total_reserved = sum(segment.total_size for segment in snapshot.segments)
        snapshot.total_activated = sum(segment.active_size for segment in snapshot.segments)
        snapshot.device = 0
        return snapshot

    @staticmethod
    def make_segment(address, total_size, stream=0, blocks=None):
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

    @staticmethod
    def make_block(address, size, state=BlockState.ACTIVE_ALLOCATED):
        return Block(size=size, requested_size=size, address=address, state=state)

    def test_find_block_returns_idx_and_block(self):
        block_a = self.make_block(0x1000, 0x100)
        block_b = self.make_block(0x1400, 0x80)
        snapshot = self.make_snapshot([self.make_segment(0x1000, 0x1000, blocks=[block_a, block_b])])

        block_idx, found = find_block(snapshot.segments[0], 0x1400)
        miss_idx, missing = find_block(snapshot.segments[0], 0x1800)

        self.assertEqual(1, block_idx)
        self.assertIs(found, block_b)
        self.assertEqual(-1, miss_idx)
        self.assertIsNone(missing)

    def test_find_segment_returns_idx_and_exact_segment(self):
        snapshot = self.make_snapshot(
            [
                self.make_segment(0x1000, 0x300, stream=0),
                self.make_segment(0x1000, 0x400, stream=1),
                self.make_segment(0x2000, 0x200, stream=0),
            ]
        )

        result_idx, result_segment = find_overlapping_segment(snapshot, 0x1000)
        overlapping_idx, overlapping = find_overlapping_segment(snapshot, 0x1000, stream=0)
        exact_idx, exact = find_segment(snapshot, 0x1000, stream=1)
        missing_idx, missing = find_segment(snapshot, 0x1100, stream=1)

        self.assertIn(result_idx, [0, 1])
        self.assertIsNotNone(result_segment)
        self.assertEqual(0, overlapping_idx)
        self.assertEqual(0x1000, overlapping.address)
        self.assertEqual(1, exact_idx)
        self.assertEqual(1, exact.stream)
        self.assertEqual(-1, missing_idx)
        self.assertIsNone(missing)

    def test_find_overlapping_segment_scans_both_sides_when_overlapping_ranges_exist(self):
        snapshot = self.make_snapshot(
            [
                self.make_segment(0x1000, 0x1000, stream=5),
                self.make_segment(0x1800, 0x100, stream=1),
            ]
        )

        segment_idx, segment = find_overlapping_segment(snapshot, 0x1850, stream=1)

        self.assertEqual(1, segment_idx)
        self.assertIs(segment, snapshot.segments[1])

    def test_find_overlapping_segment_finds_left_side_overlap_when_mid_stream_mismatches(self):
        snapshot = self.make_snapshot(
            [
                self.make_segment(0x1000, 0x900, stream=1),
                self.make_segment(0x1400, 0x1000, stream=5),
            ]
        )

        segment_idx, segment = find_overlapping_segment(snapshot, 0x1850, stream=1)

        self.assertEqual(0, segment_idx)
        self.assertIs(segment, snapshot.segments[0])

    def test_find_overlapping_segment_returns_none_when_overlap_exists_but_stream_missing(self):
        snapshot = self.make_snapshot(
            [
                self.make_segment(0x1000, 0x1000, stream=5),
                self.make_segment(0x1800, 0x100, stream=1),
            ]
        )

        segment_idx, segment = find_overlapping_segment(snapshot, 0x1850, stream=9)

        self.assertEqual(-1, segment_idx)
        self.assertIsNone(segment)

    def test_is_valid_sub_block_checks_range_inclusion(self):
        block = self.make_block(0x1000, 0x200)

        self.assertTrue(is_valid_sub_block(block, 0x1000, 0x100))
        self.assertTrue(is_valid_sub_block(block, 0x1100, 0x100))
        self.assertFalse(is_valid_sub_block(block, 0x0F00, 0x100))
        self.assertFalse(is_valid_sub_block(block, 0x1100, 0x200))

    def test_find_gap_for_alloc_block_returns_insert_position_between_blocks(self):
        block_a = self.make_block(0x1000, 0x100)
        block_b = self.make_block(0x1400, 0x100)
        snapshot = self.make_snapshot([self.make_segment(0x1000, 0x1000, blocks=[block_a, block_b])])

        gap = find_gap_for_alloc_block(snapshot, 0x1200, 0x100, stream=0)

        self.assertIsNotNone(gap)
        segment, insert_idx = gap
        self.assertEqual(0x1000, segment.address)
        self.assertEqual(1, insert_idx)
