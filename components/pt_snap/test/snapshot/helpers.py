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

from __future__ import annotations

from pathlib import Path

from pt_snap_cli.snapshot.base import BlockState, DeviceSnapshot, Segment

FIXTURE_DIR = Path(__file__).parents[1] / "fixtures" / "snapshots"


def assert_valid_segment(segment: Segment) -> None:
    assert segment.active_size >= segment.allocated_size
    assert segment.total_size >= segment.active_size
    allocated = 0
    activated = 0
    for block in segment.blocks:
        assert block.size > 0
        if block.state != BlockState.INACTIVE:
            activated += block.size
            if block.state == BlockState.ACTIVE_ALLOCATED:
                allocated += block.size
        assert block.segment_ptr is segment
    assert allocated == segment.allocated_size
    assert activated == segment.active_size


def assert_valid_segments(segments: list[Segment]) -> None:
    previous_start = -1
    previous_end = 0
    for segment in segments:
        segment_start = segment.address
        segment_end = segment.address + segment.total_size
        assert previous_start < previous_end <= segment_start < segment_end
        assert_valid_segment(segment)
        previous_start = segment_start
        previous_end = segment_end


def assert_valid_snapshot(snapshot: DeviceSnapshot) -> None:
    assert_valid_segments(snapshot.segments)
    assert sum(segment.total_size for segment in snapshot.segments) == snapshot.total_reserved
    assert sum(segment.allocated_size for segment in snapshot.segments) == snapshot.total_allocated
    assert sum(segment.active_size for segment in snapshot.segments) == snapshot.total_activated
