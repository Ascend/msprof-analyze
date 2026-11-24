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

# The allocator callbacks are intentionally optional no-ops for partial hook implementations.
# ruff: noqa: B024, B027

from abc import ABC, abstractmethod

from ..base import Block, DeviceSnapshot, Segment, TraceEntry


class SimulateHooker(ABC):
    @abstractmethod
    def pre_undo_event(self, wait4undo_event: TraceEntry, current_snapshot: DeviceSnapshot) -> bool:
        """
            【READONLY】在回放事件前回调，此时事件列表**并未POP**出该事件
        :param wait4undo_event: 【只读】待回放的事件（仍在事件列表中）
        :param current_snapshot: 【只读】当前的内存块快照
        :return 返回true继续执行，返回false将中断
        """
        pass

    @abstractmethod
    def post_undo_event(self, already_undo_event: TraceEntry, current_snapshot: DeviceSnapshot) -> bool:
        """
            【READONLY】在回放事件后回调，此时snapshot已经将该事件从事件列表中丢弃，且segments已回放到事件发生前
        :param already_undo_event: 已回放的事件
        :param current_snapshot: 【只读】当前内存快照
        :return 返回true继续执行，返回false将中断
        """
        pass


class AllocatorHooker(ABC):
    def pre_replay_alloc_block(self, wait4alloc_block: Block, current_snapshot: DeviceSnapshot):
        """
            在**回放时**分配一个内存块**前**回调，对应一个内存块释放事件回滚前
        :param wait4alloc_block: 待分配的block
        :param current_snapshot: 【只读】当前内存快照
        """
        pass

    def post_replay_alloc_block(self, allocated_block: Block, current_snapshot: DeviceSnapshot):
        """
            在**回放时**分配一个内存块**后**回调，对应一个内存块释放事件回滚后
        :param allocated_block: 【只读】新分配的block
        :param current_snapshot:【只读】分配block前内存快照
        """
        pass

    def pre_replay_free_block(self, wait4free_block: Block, current_snapshot: DeviceSnapshot):
        """
            在**回放时**释放一个内存块**前**回调，对应一个内存块申请事件回滚前
        :param wait4free_block: 【只读】待释放的block
        :param current_snapshot: 【只读】释放block前内存快照
        """
        pass

    def post_replay_free_block(self, released_block: Block, current_snapshot: DeviceSnapshot):
        """
            在回放时，释放一个内存块**后**回调，对应一个内存块申请事件回滚后
        :param released_block: 【副本】已释放的block（副本）
        :param current_snapshot: 【只读】释放block后内存快照
        """
        pass

    def pre_replay_map_or_alloc_segment(self, wait4alloc_map_segment: Segment, current_snapshot: DeviceSnapshot):
        """
            在回放时，分配或映射一个内存段**前**回调，对应一个内存段释放或unmap事件回滚前
        :param wait4alloc_map_segment: 【只读】待分配或map的内存段
        :param current_snapshot: 分配或map内存段前的内存快照
        """
        pass

    def post_replay_map_or_alloc_segment(self, allocated_mapped_segment: Segment, current_snapshot: DeviceSnapshot):
        """
            在回放时，分配或映射一个内存段**后**回调，对应一个内存段释放或unmap事件回滚后
        :param allocated_mapped_segment:【副本】已分配或map的内存段
        :param current_snapshot: 分配或map内存段后的内存快照
        """
        pass

    def pre_replay_unmap_or_free_segment(self, wait4release_segment: Segment, current_snapshot: DeviceSnapshot):
        """
            在回放时，释放或unmap一个内存段**前**回调，对应一个内存段申请或map事件前
        :param wait4release_segment:【只读】待释放的内存段
        :param current_snapshot: 释放或unmap内存段前的内存快照
        """
        pass

    def post_replay_unmap_or_free_segment(self, released_segment: Segment, current_snapshot: DeviceSnapshot):
        """
            在回放时，释放或unmap一个内存段**后**回调，对应一个内存段申请或map事件后
        :param released_segment:【副本】已释放的内存段
        :param current_snapshot: 释放或unmap内存段后的内存快照
        """
        pass
