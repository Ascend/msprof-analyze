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

from pt_snap_cli.snapshot.base import Block, DeviceSnapshot, Segment
from pt_snap_cli.snapshot.simulate.allocator_hook_dispatcher import (
    AllocatorHookDispatcher,
)


class RecordingHooker:
    def __init__(self, name="hook"):
        self.name = name
        self.calls = []

    def _record(self, action, payload, snapshot):
        self.calls.append((self.name, action, payload, snapshot))

    def pre_replay_alloc_block(self, block, snapshot):
        self._record("pre_alloc", block, snapshot)

    def post_replay_alloc_block(self, block, snapshot):
        self._record("post_alloc", block, snapshot)

    def pre_replay_free_block(self, block, snapshot):
        self._record("pre_free", block, snapshot)

    def post_replay_free_block(self, block, snapshot):
        self._record("post_free", block, snapshot)

    def pre_replay_map_or_alloc_segment(self, segment, snapshot):
        self._record("pre_segment_alloc", segment, snapshot)

    def post_replay_map_or_alloc_segment(self, segment, snapshot):
        self._record("post_segment_alloc", segment, snapshot)

    def pre_replay_unmap_or_free_segment(self, segment, snapshot):
        self._record("pre_segment_free", segment, snapshot)

    def post_replay_unmap_or_free_segment(self, segment, snapshot):
        self._record("post_segment_free", segment, snapshot)


def test_dispatcher_register_unregister_and_dispatch_copy_behavior():
    dispatcher = AllocatorHookDispatcher()
    hooker = RecordingHooker()
    snapshot = DeviceSnapshot()
    block = Block(size=16, requested_size=16, address=0x1000)
    segment = Segment(address=0x1000, total_size=0x100, stream=0)

    hooker_id = dispatcher.register_hooker(hooker)
    assert hooker_id in dispatcher.hookers

    dispatcher.pre_replay_alloc_block(block, snapshot)
    dispatcher.post_replay_alloc_block(block, snapshot)
    dispatcher.pre_replay_free_block(block, snapshot)
    dispatcher.post_replay_free_block(block, snapshot, use_copy=True)
    dispatcher.pre_replay_map_or_alloc_segment(segment, snapshot)
    dispatcher.post_replay_map_or_alloc_segment(segment, snapshot)
    dispatcher.pre_replay_unmap_or_free_segment(segment, snapshot)
    dispatcher.post_replay_unmap_or_free_segment(segment, snapshot)

    assert [call[1] for call in hooker.calls] == [
        "pre_alloc",
        "post_alloc",
        "pre_free",
        "post_free",
        "pre_segment_alloc",
        "post_segment_alloc",
        "pre_segment_free",
        "post_segment_free",
    ]
    assert hooker.calls[3][2] is not block
    assert hooker.calls[3][2].address == block.address

    dispatcher.unregister_hooker(hooker_id)
    assert hooker_id not in dispatcher.hookers


def test_dispatcher_unregister_missing_id_is_noop():
    dispatcher = AllocatorHookDispatcher()
    dispatcher.unregister_hooker(12345)
    assert dispatcher.hookers == {}


def test_dispatcher_invokes_callbacks_in_registration_order():
    dispatcher = AllocatorHookDispatcher()
    snapshot = DeviceSnapshot()
    block = Block(size=16, requested_size=16, address=0x1000)
    call_order = []

    class OrderedHooker(RecordingHooker):
        def pre_replay_alloc_block(self, block, snapshot):
            call_order.append(self.name)

    first = OrderedHooker("first")
    second = OrderedHooker("second")
    dispatcher.register_hooker(first)
    dispatcher.register_hooker(second)

    dispatcher.pre_replay_alloc_block(block, snapshot)

    assert call_order == ["first", "second"]
