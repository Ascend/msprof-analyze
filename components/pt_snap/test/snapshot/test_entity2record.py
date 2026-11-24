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

from pt_snap_cli.snapshot.base import Block, Frame, TraceEntry
from pt_snap_cli.snapshot.tools.adaptors.database.callstack import CallstackInterner
from pt_snap_cli.snapshot.tools.adaptors.database.defs import (
    BlockFieldDefs,
    EventFieldDefs,
)
from pt_snap_cli.snapshot.tools.adaptors.database.entity2record import (
    block2record,
    event2record,
    get_timestamp_by_event_idx,
    make_default_id_counter,
)


def test_make_default_id_counter_counts_down_from_start():
    next_id = make_default_id_counter(-3)

    assert next_id() == -3
    assert next_id() == -4


def test_get_timestamp_by_event_idx_handles_none():
    assert get_timestamp_by_event_idx(None) == -1
    assert get_timestamp_by_event_idx(7) == 70


def test_event2record_uses_generated_default_id_when_missing():
    event = TraceEntry(action="alloc", addr=0x1000, size=16, stream=0, idx=None)

    record = event2record(event, allocated=1, active=2, reserved=3, callstacks=CallstackInterner())

    assert record[EventFieldDefs.ID] < 0
    assert record[EventFieldDefs.ALLOCATED] == 1
    assert record[EventFieldDefs.ACTIVE] == 2
    assert record[EventFieldDefs.RESERVED] == 3


def test_block2record_uses_generated_default_id_when_missing():
    block = Block(size=16, requested_size=8, address=0x1000, state="active_allocated")

    record = block2record(block)

    assert record[BlockFieldDefs.ID] < 0
    assert record[BlockFieldDefs.ALLOC_EVENT_ID] == -1
    assert record[BlockFieldDefs.FREE_EVENT_ID] == -1


def test_records_preserve_totals_state_ids_and_callstack_serialization():
    event = TraceEntry(
        action="alloc",
        addr=0x2000,
        size=32,
        stream=4,
        idx=9,
        frames=[
            Frame.from_dict({"filename": "inner.py", "line": 10, "name": "inner"}),
            Frame.from_dict({"filename": "outer.py", "line": 20, "name": "outer"}),
        ],
    )
    block = Block(
        size=32,
        requested_size=24,
        address=0x2000,
        state="active_pending_free",
        alloc_event_idx=9,
        free_event_idx=12,
    )

    callstacks = CallstackInterner()
    event_record = event2record(event, allocated=100, active=120, reserved=256, callstacks=callstacks)
    block_record = block2record(block)

    assert event_record == {
        "id": 9,
        "action": "alloc",
        "address": 0x2000,
        "size": 32,
        "stream": 4,
        "allocated": 100,
        "active": 120,
        "reserved": 256,
        "callstackId": 0,
    }
    assert callstacks.records() == [{"id": 0, "callstack": "outer.py:20 outer\ninner.py:10 inner"}]
    assert block_record == {
        "id": 9,
        "address": 0x2000,
        "size": 32,
        "requestedSize": 24,
        "state": "active_pending_free",
        "allocEventId": 9,
        "freeEventId": 12,
    }


def test_synthetic_ids_remain_negative_and_monotonically_decrease():
    next_id = make_default_id_counter()

    ids = [next_id() for _ in range(4)]

    assert ids == [-1, -2, -3, -4]
    assert all(identifier < 0 for identifier in ids)
