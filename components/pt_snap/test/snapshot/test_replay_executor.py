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

import pytest

from pt_snap_cli.snapshot.base import BlockState, TraceEntry
from pt_snap_cli.snapshot.simulate.replay_executor import ReplayExecutor


class FakeAllocator:
    def __init__(self):
        self.calls = []

    def alloc_block(self, block):
        self.calls.append(("alloc_block", block))
        return True

    def active_block(self, event):
        self.calls.append(("active_block", event))
        return True

    def free_block(self, event):
        self.calls.append(("free_block", event))
        return True

    def alloc_or_map_segment(self, segment, merge=False):
        self.calls.append(("alloc_or_map_segment", segment, merge))
        return True

    def free_segment(self, event):
        self.calls.append(("free_segment", event))
        return True

    def unmap_segment(self, event):
        self.calls.append(("unmap_segment", event))
        return True


class FakeLogger:
    def __init__(self):
        self.messages = []

    def warning(self, message, *args, **kwargs):
        self.messages.append(message)


def make_event(action, addr=0x1000, size=0x100, stream=0, idx=1):
    return TraceEntry(action=action, addr=addr, size=size, stream=stream, idx=idx)


class TestReplayExecutor(unittest.TestCase):
    def setUp(self):
        self.allocator = FakeAllocator()
        self.logger = FakeLogger()
        self.executor = ReplayExecutor(self.allocator, self.logger)

    def test_execute_free_event_maps_to_alloc_block(self):
        event = make_event("free")

        result = self.executor.execute(event)

        self.assertTrue(result)
        call = self.allocator.calls[0]
        self.assertEqual("alloc_block", call[0])
        self.assertEqual(event.addr, call[1].address)

    def test_execute_segment_unmap_maps_to_alloc_or_map_segment_with_merge(self):
        event = make_event("segment_unmap", addr=0x2000, size=0x400)

        result = self.executor.execute(event)

        self.assertTrue(result)
        call = self.allocator.calls[0]
        self.assertEqual("alloc_or_map_segment", call[0])
        self.assertTrue(call[2])
        self.assertEqual(event.idx, call[1].free_or_unmap_event_idx)

    def test_execute_unknown_event_warns_and_skips(self):
        event = make_event("unknown_action")

        result = self.executor.execute(event)

        self.assertTrue(result)
        self.assertEqual([], self.allocator.calls)
        self.assertEqual(1, len(self.logger.messages))
        self.assertIn("Skip event", self.logger.messages[0])


@pytest.mark.parametrize(
    ("action", "method", "extra"),
    [
        ("free", "alloc_block", BlockState.ACTIVE_ALLOCATED),
        ("free_completed", "alloc_block", BlockState.ACTIVE_PENDING_FREE),
        ("free_requested", "active_block", None),
        ("alloc", "free_block", None),
        ("segment_free", "alloc_or_map_segment", False),
        ("segment_unmap", "alloc_or_map_segment", True),
        ("segment_alloc", "free_segment", None),
        ("segment_map", "unmap_segment", None),
    ],
)
def test_execute_dispatches_every_allocator_branch(action, method, extra):
    allocator = FakeAllocator()
    logger = FakeLogger()
    event = make_event(action, idx=17)

    assert ReplayExecutor(allocator, logger).execute(event) is True

    call = allocator.calls[0]
    assert call[0] == method
    if action in {"free", "free_completed"}:
        assert call[1].state == extra
    elif action in {"segment_free", "segment_unmap"}:
        assert call[1].free_or_unmap_event_idx == 17
        assert call[2] is extra
    assert logger.messages == []


@pytest.mark.parametrize("action", ["oom", "snapshot", "workspace_snapshot", "unknown_action"])
def test_execute_preserves_skipped_event_baseline(action):
    allocator = FakeAllocator()
    logger = FakeLogger()
    event = make_event(action)

    assert ReplayExecutor(allocator, logger).execute(event) is True

    assert allocator.calls == []
    assert logger.messages == [f"Skip event{event.to_dict()} during replay."]
