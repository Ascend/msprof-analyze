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

from typing import Any, Dict

from ....base import Block, TraceEntry
from .callstack import CallstackInterner
from .defs import BlockFieldDefs, EventFieldDefs


def make_default_id_counter(start: int = -1):
    count = start

    def next_id():
        nonlocal count
        current = count
        count -= 1
        return current

    return next_id


def get_timestamp_by_event_idx(event_idx: int) -> int:
    return event_idx * 10 if event_idx is not None else -1


next_default_block_id = make_default_id_counter()
next_default_event_id = make_default_id_counter()


def event2record(
    event: TraceEntry,
    allocated: int = 0,
    active: int = 0,
    reserved: int = 0,
    *,
    callstacks: CallstackInterner,
) -> Dict[str, Any]:
    return {
        EventFieldDefs.ID: (event.idx if event.idx is not None else next_default_event_id()),
        EventFieldDefs.ACTION: event.action,
        EventFieldDefs.ADDR: event.addr,
        EventFieldDefs.SIZE: event.size,
        EventFieldDefs.STREAM: event.stream,
        EventFieldDefs.ALLOCATED: allocated,
        EventFieldDefs.ACTIVE: active,
        EventFieldDefs.RESERVED: reserved,
        EventFieldDefs.CALLSTACK_ID: callstacks.intern(event),
    }


def block2record(block: Block) -> Dict[str, Any]:
    return {
        BlockFieldDefs.ID: (block.alloc_event_idx if block.alloc_event_idx is not None else next_default_block_id()),
        BlockFieldDefs.ADDR: block.address,
        BlockFieldDefs.SIZE: block.size,
        BlockFieldDefs.REQUESTED_SIZE: block.requested_size,
        BlockFieldDefs.STATE: block.state,
        BlockFieldDefs.ALLOC_EVENT_ID: (block.alloc_event_idx if block.alloc_event_idx is not None else -1),
        BlockFieldDefs.FREE_EVENT_ID: (block.free_event_idx if block.free_event_idx is not None else -1),
    }
