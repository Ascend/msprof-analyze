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

import pytest

from pt_snap_cli.snapshot.simulate import snapshot_mutator

from .helpers import assert_valid_snapshot
from .test_snapshot_mutator import (
    make_allocator,
    make_block,
    make_event,
    make_segment,
    make_snapshot,
)


@pytest.mark.parametrize(
    ("operation", "address", "size", "stream", "workspace", "expected"),
    [
        ("free_block", 0x3000, 0x100, 0, False, False),
        ("free_block", 0x1400, 0x100, 0, False, False),
        ("free_block", 0x1000, 0x200, 0, False, False),
        ("active_block", 0x3000, 0x100, 0, False, False),
        ("active_block", 0x1400, 0x100, 0, False, False),
        ("active_block", 0x1000, 0x100, 0, False, False),
        ("active_block", 0x1000, 0x100, 0, True, True),
        ("free_segment", 0x3000, 0x1000, 0, False, False),
        ("free_segment", 0x1000, 0x800, 0, False, False),
        ("free_segment", 0x1000, 0x1000, 0, False, False),
        ("unmap_segment", 0x3000, 0x100, 0, False, False),
        ("unmap_segment", 0x1800, 0x1000, 0, False, False),
        ("unmap_segment", 0x1000, 0x100, 1, False, False),
    ],
)
def test_invalid_replay_preserves_state(operation, address, size, stream, workspace, expected):
    allocator = make_allocator([make_segment(blocks=[make_block()])])
    snapshot = allocator.ctx.device_snapshot
    before = snapshot.to_dict()
    allocator.ctx.workspace_flag = workspace
    assert getattr(allocator, operation)(make_event("alloc", address, size, stream)) is expected
    assert snapshot.to_dict() == before
    assert_valid_snapshot(snapshot)


def test_overlapping_allocation_is_rejected_without_mutation():
    allocator = make_allocator([make_segment(blocks=[make_block()])])
    before = allocator.ctx.device_snapshot.to_dict()
    assert allocator.alloc_block(make_block()) is False
    assert allocator.ctx.device_snapshot.to_dict() == before
    assert_valid_snapshot(allocator.ctx.device_snapshot)


@pytest.mark.parametrize(("target", "source"), [(-1, 1), (2, 1), (0, -1), (0, 2), (0, 0)])
def test_invalid_merge_indices_preserve_segments(target, source):
    snapshot = make_snapshot([make_segment(0x1000, 0x100), make_segment(0x1100, 0x100)])
    before = snapshot.to_dict()
    assert snapshot_mutator._merge_segments(snapshot, target, source) is False
    assert snapshot.to_dict() == before
    assert_valid_snapshot(snapshot)


@pytest.mark.parametrize(("address", "stream"), [(0x1200, 0), (0x1100, 1)])
def test_incompatible_merge_preserves_segments(address, stream):
    snapshot = make_snapshot([make_segment(0x1000, 0x100), make_segment(address, 0x100, stream)])
    before = snapshot.to_dict()
    assert snapshot_mutator._merge_segments(snapshot, 0, 1) is False
    assert snapshot.to_dict() == before
    assert_valid_snapshot(snapshot)


@pytest.mark.parametrize(
    ("index", "address", "size", "direction"),
    [
        (-1, 0x1000, 0x100, "left"),
        (1, 0x1000, 0x100, "left"),
        (0, 0x1000, 0x100, "invalid"),
        (0, 0xF00, 0x100, "left"),
        (0, 0x1F00, 0x200, "right"),
        (0, 0x1000, 0x100, "left"),
        (0, 0x1000, 0x1000, "right"),
    ],
)
def test_invalid_shrink_preserves_live_block(index, address, size, direction):
    snapshot = make_snapshot([make_segment(blocks=[make_block()])])
    before = snapshot.to_dict()
    assert snapshot_mutator._shrink_segment(snapshot, index, address, size, direction) is False
    assert snapshot.to_dict() == before
    assert_valid_snapshot(snapshot)
