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

import gc
import weakref

import pytest

from pt_snap_cli.snapshot.base import TraceEntry
from pt_snap_cli.snapshot.tools.adaptors.database.callstack import CallstackInterner

INNER = {"filename": "inner.py", "line": 10, "name": "inner"}
OUTER = {"filename": "outer.py", "line": 20, "name": "outer"}
EXPECTED_TEXT = "outer.py:20 outer\ninner.py:10 inner"


class WeakrefableFrames(list):
    """List-shaped frame container used to test exemplar retention."""


def _raw_event(frames: list[dict], idx: int = 0) -> TraceEntry:
    return TraceEntry.from_dict(
        {"action": "alloc", "addr": 0x1000, "size": 16, "stream": 0, "id": idx, "frames": frames},
        _raw_frames=True,
    )


def test_interned_text_matches_get_callstack():
    interner = CallstackInterner()
    event = _raw_event([INNER, OUTER])

    assert interner.intern(event) == 0
    assert interner.records() == [{"id": 0, "callstack": EXPECTED_TEXT}]
    assert interner.records()[0]["callstack"] == event.get_callstack()


def test_shared_frame_container_reuses_one_id():
    interner = CallstackInterner()
    frames = [INNER, OUTER]

    first = interner.intern(_raw_event(frames, idx=1))
    second = interner.intern(_raw_event(frames, idx=2))

    assert first == second == 0
    assert len(interner) == 1


def test_distinct_containers_with_equal_frames_reuse_one_id():
    interner = CallstackInterner()

    first = interner.intern(_raw_event([INNER, OUTER], idx=1))
    second = interner.intern(_raw_event([dict(INNER), dict(OUTER)], idx=2))

    assert first == second == 0
    assert len(interner) == 1


def test_different_callstacks_get_different_ids():
    interner = CallstackInterner()

    first = interner.intern(_raw_event([INNER], idx=1))
    second = interner.intern(_raw_event([OUTER], idx=2))

    assert {first, second} == {0, 1}
    assert len(interner) == 2
    assert [record["callstack"] for record in interner.records()] == [
        "inner.py:10 inner",
        "outer.py:20 outer",
    ]


def test_empty_frames_intern_to_empty_text():
    interner = CallstackInterner()

    first = interner.intern(_raw_event([], idx=1))
    second = interner.intern(_raw_event([], idx=2))

    assert first == second == 0
    assert interner.records() == [{"id": 0, "callstack": ""}]


def test_distinct_frame_identities_do_not_produce_a_false_hit():
    """Distinct frame identities must not inherit an unrelated callstack id."""
    interner = CallstackInterner()

    for frames in ([INNER], [OUTER]):
        event = _raw_event(frames)
        interner.intern(event)

    assert len(interner) == 2
    assert [record["callstack"] for record in interner.records()] == [
        "inner.py:10 inner",
        "outer.py:20 outer",
    ]


def test_frame_container_exemplar_stays_alive_for_id_reuse_safety():
    interner = CallstackInterner()
    frames = WeakrefableFrames([INNER])
    frames_ref = weakref.ref(frames)

    interner.intern(_raw_event(frames))
    del frames
    gc.collect()

    assert frames_ref() is not None


def test_eager_frame_objects_intern_to_the_same_text_as_raw_frames():
    interner = CallstackInterner()
    raw = _raw_event([INNER, OUTER], idx=1)
    eager = TraceEntry.from_dict(
        {
            "action": "alloc",
            "addr": 0x1000,
            "size": 16,
            "stream": 0,
            "id": 2,
            "frames": [INNER, OUTER],
        },
    )

    raw_id = interner.intern(raw)
    eager_id = interner.intern(eager)

    assert raw_id == eager_id == 0
    assert len(interner) == 1


def test_original_order_and_recursive_frames_survive_interning():
    interner = CallstackInterner(structured_frames=True)
    interner.intern(_raw_event([INNER, INNER, OUTER]))
    interner.intern(_raw_event([dict(INNER), dict(OUTER)]))
    assert interner.frame_records() == [{"id": 0, **INNER}, {"id": 1, **OUTER}]
    assert interner.stack_frame_records() == [
        {"callstackId": 0, "position": 0, "frameId": 0},
        {"callstackId": 0, "position": 1, "frameId": 0},
        {"callstackId": 0, "position": 2, "frameId": 1},
        {"callstackId": 1, "position": 0, "frameId": 0},
        {"callstackId": 1, "position": 1, "frameId": 1},
    ]


@pytest.mark.parametrize("structured", [False, True])
def test_display_text_collisions_only_remain_distinct_for_structured_stacks(structured):
    interner = CallstackInterner(structured_frames=structured)
    first = _raw_event([{"filename": "x", "line": 1, "name": "f\ny:2 g"}])
    second = _raw_event(
        [
            {"filename": "y", "line": 2, "name": "g"},
            {"filename": "x", "line": 1, "name": "f"},
        ]
    )
    assert first.get_callstack() == second.get_callstack()
    assert (interner.intern(first) != interner.intern(second)) is structured
    assert len(interner) == (2 if structured else 1)


@pytest.mark.parametrize("structured", [False, True])
def test_empty_stack_manifest_only_attests_structured_capture(structured):
    interner = CallstackInterner(structured_frames=structured)
    interner.intern(_raw_event([]))
    interner.intern(_raw_event([INNER, INNER, OUTER]))
    assert interner.stack_manifest_records() == (
        [{"callstackId": 0, "frameCount": 0}, {"callstackId": 1, "frameCount": 3}] if structured else []
    )
    if not structured:
        assert interner.frame_records() == interner.stack_frame_records() == []


@pytest.mark.parametrize(
    "field,value",
    [
        ("line", True),
        ("line", False),
        ("line", 1.0),
        ("line", "1"),
        ("line", None),
        ("filename", 42),
        ("name", False),
    ],
)
@pytest.mark.parametrize("eager", [False, True])
def test_structured_fields_reject_lossy_types_without_changing_native_text(field, value, eager):
    invalid = {**INNER, field: value}
    event = _raw_event([INNER, invalid])
    if eager:
        event = TraceEntry.from_dict(event.to_dict())
    structured = CallstackInterner(structured_frames=True)
    with pytest.raises(ValueError, match="Structured frames require"):
        structured.intern(event)
    assert structured.records() == structured.frame_records() == []
    native = CallstackInterner()
    assert native.intern(event) == 0
    assert native.records() == [{"id": 0, "callstack": event.get_callstack()}]


@pytest.mark.parametrize("eager", [False, True])
def test_structured_identity_preserves_exact_fields_without_normalizing(eager):
    frames = [
        {"filename": "训练:模型.py", "line": -1, "name": "内部\n分配"},
        {"filename": "", "line": 0, "name": ""},
        {"filename": "训练:模型.py", "line": 1, "name": "内部\n分配"},
    ]
    first = _raw_event(frames)
    equal = _raw_event([dict(frame) for frame in frames])
    if eager:
        first = TraceEntry.from_dict(first.to_dict())
    interner = CallstackInterner(structured_frames=True)
    assert interner.intern(first) == interner.intern(equal) == 0
    assert interner.frame_records() == [{"id": index, **frame} for index, frame in enumerate(frames)]
    assert interner.stack_manifest_records() == [{"callstackId": 0, "frameCount": 3}]
