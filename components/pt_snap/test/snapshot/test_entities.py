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
from pt_snap_cli.snapshot.simulate.snapshot_lookup import (
    find_block,
    find_overlapping_segment,
    find_segment,
    is_valid_sub_block,
)


class TestFrame(unittest.TestCase):
    def test_from_dict(self):
        frame_dict = {"filename": "test.py", "line": 42, "name": "test_func"}
        frame = Frame.from_dict(frame_dict)
        self.assertEqual(frame.filename, "test.py")
        self.assertEqual(frame.line, 42)
        self.assertEqual(frame.name, "test_func")
        self.assertEqual(frame._origin, frame_dict)

    def test_to_dict_with_origin(self):
        frame_dict = {"filename": "test.py", "line": 42, "name": "test_func"}
        frame = Frame.from_dict(frame_dict)
        self.assertEqual(frame.to_dict(), frame_dict)

    def test_to_dict_without_origin(self):
        frame = Frame()
        frame.filename = "test.py"
        frame.line = 42
        frame.name = "test_func"
        result = frame.to_dict()
        self.assertEqual(result["filename"], "test.py")
        self.assertEqual(result["line"], 42)
        self.assertEqual(result["name"], "test_func")

    def test_origin_default_is_none(self):
        self.assertIsNone(Frame()._origin)


class TestTraceEntry(unittest.TestCase):
    def test_from_dict(self):
        trace_dict = {
            "action": "alloc",
            "addr": 0x1000,
            "size": "1024",
            "stream": "0",
            "frames": [
                {"filename": "test.py", "line": 10, "name": "func_a"},
                {"filename": "test.py", "line": 20, "name": "func_b"},
            ],
        }
        trace = TraceEntry.from_dict(trace_dict)
        self.assertEqual(trace.action, "alloc")
        self.assertEqual(trace.addr, 0x1000)
        self.assertEqual(trace.size, 1024)
        self.assertEqual(trace.stream, 0)
        self.assertEqual(len(trace.frames), 2)
        self.assertEqual(trace.frames[0].filename, "test.py")
        self.assertEqual(trace.frames[1].name, "func_b")

    def test_from_dict_without_frames(self):
        trace_dict = {
            "action": "free_requested",
            "addr": 0x2000,
            "size": "2048",
            "stream": "1",
        }
        trace = TraceEntry.from_dict(trace_dict)
        self.assertEqual(trace.action, "free_requested")
        self.assertEqual(trace.addr, 0x2000)
        self.assertEqual(trace.size, 2048)
        self.assertEqual(len(trace.frames), 0)

    def test_from_dict_loads_oom_without_addr_or_stream(self):
        trace = TraceEntry.from_dict({"action": "oom", "size": 1024, "device_free": 2048, "frames": []})
        self.assertEqual(trace.action, "oom")
        self.assertEqual(trace.addr, -1)
        self.assertEqual(trace.size, 1024)
        self.assertEqual(trace.stream, 0)
        self.assertEqual(trace.device_free, 2048)
        self.assertEqual(trace.frames, [])

    def test_from_dict_requires_action(self):
        with self.assertRaises(KeyError):
            TraceEntry.from_dict({"size": 1024, "frames": []})

    def test_get_callstack(self):
        trace = TraceEntry.from_dict(
            {
                "action": "alloc",
                "addr": 0x1000,
                "size": "1024",
                "stream": "0",
                "frames": [
                    {"filename": "test.py", "line": 10, "name": "func_a"},
                    {"filename": "main.py", "line": 20, "name": "func_b"},
                ],
            }
        )
        callstack = trace.get_callstack()
        self.assertIn("main.py:20 func_b", callstack)
        self.assertIn("test.py:10 func_a", callstack)

    def test_get_callstack_empty_frames(self):
        trace = TraceEntry(action="alloc")
        self.assertEqual(trace.get_callstack(), "")

    def test_raw_frames_match_eager_format_without_mutating_source(self):
        trace_dict = {
            "action": "alloc",
            "addr": 0x1000,
            "size": "1024",
            "stream": "0",
            "id": 27,
            "frames": [
                {"filename": "inner.py", "line": 10, "name": "inner"},
                {"filename": "outer.py", "line": 20, "name": "outer"},
            ],
        }
        original = {**trace_dict, "frames": [dict(frame) for frame in trace_dict["frames"]]}

        eager = TraceEntry.from_dict(trace_dict)
        raw = TraceEntry.from_dict(trace_dict, _raw_frames=True)

        self.assertTrue(all(isinstance(frame, Frame) for frame in eager.frames))
        self.assertEqual(raw.frames, [])
        self.assertIs(raw._raw_frames, trace_dict["frames"])
        self.assertEqual(raw.get_callstack(), eager.get_callstack())
        self.assertEqual(raw.get_callstack(), "outer.py:20 outer\ninner.py:10 inner")
        self.assertEqual(raw.to_dict(include_id=True), eager.to_dict(include_id=True))
        self.assertEqual(raw.idx, 27)
        self.assertEqual(trace_dict, original)

    def test_raw_frames_preserve_empty_missing_and_incomplete_behavior(self):
        base = {"action": "alloc", "addr": 1, "size": 2, "stream": 0}

        self.assertEqual(TraceEntry.from_dict(base, _raw_frames=True).get_callstack(), "")
        self.assertEqual(
            TraceEntry.from_dict({**base, "frames": []}, _raw_frames=True).get_callstack(),
            "",
        )
        incomplete = {**base, "frames": [{"filename": "broken.py", "line": 3}]}
        with self.assertRaises(KeyError):
            TraceEntry.from_dict(incomplete)
        with self.assertRaises(KeyError):
            TraceEntry.from_dict(incomplete, _raw_frames=True)
        with self.assertRaises(TypeError):
            TraceEntry.from_dict({**base, "frames": None}, _raw_frames=True)

    def test_raw_frames_preserve_positional_constructor_and_synthetic_serialization(self):
        origin = {"action": "alloc"}
        trace = TraceEntry("alloc", 1, [], 2, 3, 4, origin, 5)
        raw_frames = [{"filename": "raw.py", "line": 6, "name": "run"}]
        synthetic = TraceEntry(action="alloc", _raw_frames=raw_frames)

        self.assertIs(trace._origin, origin)
        self.assertEqual(trace.idx, 5)
        self.assertIsNone(trace._raw_frames)
        self.assertIs(synthetic.to_dict()["frames"], raw_frames)

    def test_to_dict(self):
        trace_dict = {
            "action": "alloc",
            "addr": 0x1000,
            "size": "1024",
            "stream": "0",
            "frames": [],
        }
        self.assertEqual(TraceEntry.from_dict(trace_dict).to_dict(), trace_dict)


class TestBlock(unittest.TestCase):
    def test_event_index_defaults_are_none(self):
        block = Block()
        self.assertIsNone(block.free_event_idx)
        self.assertIsNone(block.alloc_event_idx)

    def test_from_dict(self):
        block = Block.from_dict(
            {
                "size": 1024,
                "requested_size": 512,
                "address": 0x1000,
                "state": "active_allocated",
                "frames": [{"filename": "test.py", "line": 10, "name": "alloc_func"}],
            }
        )
        self.assertEqual(block.size, 1024)
        self.assertEqual(block.requested_size, 512)
        self.assertEqual(block.address, 0x1000)
        self.assertEqual(block.state, "active_allocated")
        self.assertEqual(len(block.frames), 1)

    def test_build_from_event(self):
        event = TraceEntry.from_dict(
            {
                "action": "alloc",
                "addr": 0x2000,
                "size": "2048",
                "stream": "0",
                "frames": [{"filename": "test.py", "line": 10, "name": "func"}],
            }
        )
        block = Block.build_from_event(event)
        self.assertEqual(block.size, 2048)
        self.assertEqual(block.requested_size, 2048)
        self.assertEqual(block.address, 0x2000)
        self.assertEqual(len(block.frames), 1)

    def test_valid_sub_block(self):
        block = Block(size=1024, address=0x1000)
        self.assertTrue(is_valid_sub_block(block, 0x1000, 512))
        self.assertTrue(is_valid_sub_block(block, 0x1200, 512))
        self.assertTrue(is_valid_sub_block(block, 0x1000, 1024))
        self.assertFalse(is_valid_sub_block(block, 0x900, 512))
        self.assertFalse(is_valid_sub_block(block, 0x1400, 512))
        self.assertFalse(is_valid_sub_block(block, 0x1000, 2048))

    def test_to_dict(self):
        block = Block(
            size=1024,
            requested_size=512,
            address=0x1000,
            state=BlockState.ACTIVE_ALLOCATED,
            frames=[Frame.from_dict({"filename": "test.py", "line": 10, "name": "func"})],
        )
        result = block.to_dict()
        self.assertEqual(result["size"], 1024)
        self.assertEqual(result["requested_size"], 512)
        self.assertEqual(result["address"], 0x1000)
        self.assertEqual(result["state"], BlockState.ACTIVE_ALLOCATED)


class TestSegment(unittest.TestCase):
    def test_optional_defaults(self):
        segment = Segment()
        self.assertEqual(segment.segment_type, "")
        self.assertIsNone(segment._origin)
        self.assertIsNone(segment.free_or_unmap_event_idx)
        self.assertIsNone(segment.alloc_or_map_event_idx)

    @staticmethod
    def _segment_dict(is_expandable=False, blocks=None):
        return {
            "address": 0x10000,
            "total_size": 4096,
            "stream": 0,
            "segment_type": "large",
            "allocated_size": 2048 if blocks else 0,
            "active_size": 3072 if blocks else 0,
            "device": 0,
            "is_expandable": is_expandable,
            "frames": [],
            "blocks": blocks or [],
        }

    def test_from_dict(self):
        segment = Segment.from_dict(
            self._segment_dict(
                blocks=[
                    {
                        "size": 2048,
                        "requested_size": 1024,
                        "address": 0x10000,
                        "state": "active_allocated",
                        "frames": [],
                    },
                    {
                        "size": 2048,
                        "requested_size": 2048,
                        "address": 0x10800,
                        "state": "inactive",
                        "frames": [],
                    },
                ]
            )
        )
        self.assertEqual(segment.address, 0x10000)
        self.assertEqual(segment.total_size, 4096)
        self.assertEqual(segment.allocated_size, 2048)
        self.assertEqual(segment.active_size, 3072)
        self.assertEqual(len(segment.blocks), 2)
        self.assertIs(segment.blocks[0].segment_ptr, segment)
        self.assertIs(segment.blocks[1].segment_ptr, segment)

    def test_from_dict_with_expandable(self):
        self.assertTrue(Segment.from_dict(self._segment_dict(is_expandable=True)).is_expandable)

    def test_build_from_event(self):
        event = TraceEntry.from_dict(
            {
                "action": "segment_alloc",
                "addr": 0x20000,
                "size": "8192",
                "stream": "1",
                "frames": [],
            }
        )
        segment = Segment.build_from_event(event, True)
        self.assertEqual(segment.address, 0x20000)
        self.assertEqual(segment.total_size, 8192)
        self.assertEqual(segment.stream, 1)
        self.assertEqual(len(segment.blocks), 1)
        self.assertEqual(segment.blocks[0].state, BlockState.INACTIVE)
        self.assertIs(segment.blocks[0].segment_ptr, segment)

    def test_build_from_event_expandable(self):
        event = TraceEntry.from_dict(
            {
                "action": "segment_map",
                "addr": 0x30000,
                "size": "16384",
                "stream": "0",
                "frames": [],
            }
        )
        self.assertTrue(Segment.build_from_event(event).is_expandable)

    def test_find_block_returns_idx_and_object(self):
        segment = Segment(address=0x10000, total_size=8192)
        segment.blocks = [
            Block(size=2048, address=0x10000),
            Block(size=2048, address=0x10800),
            Block(size=4096, address=0x11000),
        ]
        for address, expected_idx in (
            (0x10000, 0),
            (0x10800, 1),
            (0x11000, 2),
            (0x10500, 0),
            (0x11500, 2),
        ):
            block_idx, block = find_block(segment, address)
            self.assertEqual(block_idx, expected_idx)
            self.assertIs(block, segment.blocks[expected_idx])
        for address in (0x9000, 0x13000):
            block_idx, block = find_block(segment, address)
            self.assertEqual(block_idx, -1)
            self.assertIsNone(block)

    def test_to_dict(self):
        segment = Segment(
            address=0x10000,
            total_size=4096,
            stream=0,
            segment_type="large",
            allocated_size=2048,
            active_size=2048,
            device=0,
            is_expandable=False,
        )
        result = segment.to_dict()
        self.assertEqual(result["address"], 0x10000)
        self.assertEqual(result["total_size"], 4096)
        self.assertEqual(result["segment_type"], "large")


class TestDeviceSnapshot(unittest.TestCase):
    def test_init_sets_empty_state(self):
        snapshot = DeviceSnapshot()
        self.assertEqual(snapshot.segments, [])
        self.assertEqual(snapshot.trace_entries, [])
        self.assertEqual(snapshot.total_allocated, 0)
        self.assertEqual(snapshot.total_reserved, 0)
        self.assertEqual(snapshot.total_activated, 0)
        self.assertEqual(snapshot.device, 0)

    def test_from_dict(self):
        snapshot = DeviceSnapshot.from_dict(
            {
                "segments": [
                    {
                        "address": 0x10000,
                        "total_size": 4096,
                        "stream": 0,
                        "segment_type": "large",
                        "allocated_size": 2048,
                        "active_size": 2048,
                        "device": 0,
                        "is_expandable": False,
                        "frames": [],
                        "blocks": [
                            {
                                "size": 2048,
                                "requested_size": 1024,
                                "address": 0x10000,
                                "state": "active_allocated",
                                "frames": [],
                            },
                            {
                                "size": 2048,
                                "requested_size": 2048,
                                "address": 0x10800,
                                "state": "inactive",
                                "frames": [],
                            },
                        ],
                    }
                ],
                "device_traces": [
                    [
                        {
                            "action": "alloc",
                            "addr": 0x10000,
                            "size": "1024",
                            "stream": "0",
                            "frames": [],
                        },
                        {
                            "action": "free_requested",
                            "addr": 0x10000,
                            "size": "1024",
                            "stream": "0",
                            "frames": [],
                        },
                    ]
                ],
            },
            0,
        )
        self.assertEqual(len(snapshot.segments), 1)
        self.assertEqual(len(snapshot.trace_entries), 2)
        self.assertEqual(snapshot.total_reserved, 4096)
        self.assertEqual(snapshot.total_allocated, 2048)
        self.assertEqual(snapshot.total_activated, 2048)
        self.assertEqual(snapshot.trace_entries[0].idx, 0)
        self.assertEqual(snapshot.trace_entries[1].idx, 1)
        self.assertTrue(all(isinstance(frame, Frame) for trace in snapshot.trace_entries for frame in trace.frames))

    def test_from_dict_loads_oom_trace_without_addr(self):
        snapshot = DeviceSnapshot.from_dict(
            {
                "segments": [],
                "device_traces": [[{"action": "oom", "size": 1024, "device_free": 2048, "frames": []}]],
            },
            0,
        )
        self.assertEqual(len(snapshot.trace_entries), 1)
        self.assertEqual(snapshot.trace_entries[0].action, "oom")
        self.assertEqual(snapshot.trace_entries[0].addr, -1)
        self.assertEqual(snapshot.trace_entries[0].device_free, 2048)

    def test_find_overlapping_segment_returns_idx_and_matches_containing_segment(self):
        snapshot = DeviceSnapshot()
        snapshot.segments = [
            Segment(address=0x10000, total_size=0x2000),
            Segment(address=0x20000, total_size=0x5000),
            Segment(address=0x30000, total_size=0x1000),
        ]
        for address, expected_idx in ((0x10000, 0), (0x20000, 1), (0x30000, 2)):
            segment_idx, segment = find_overlapping_segment(snapshot, address)
            self.assertEqual(segment_idx, expected_idx)
            self.assertIs(segment, snapshot.segments[expected_idx])
        for address in (0x12000, 0x25000, 0x9000, 0x40000):
            segment_idx, segment = find_overlapping_segment(snapshot, address)
            self.assertEqual(segment_idx, -1)
            self.assertIsNone(segment)

    def test_find_overlapping_segment_returns_idx_and_matches_stream_filtered_segment(self):
        snapshot = DeviceSnapshot()
        snapshot.segments = [
            Segment(address=0x10000, total_size=0x2000, stream=0),
            Segment(address=0x10000, total_size=0x3000, stream=1),
            Segment(address=0x20000, total_size=0x5000, stream=0),
            Segment(address=0x30000, total_size=0x1000, stream=1),
        ]
        result_idx, result_segment = find_overlapping_segment(snapshot, 0x10000)
        self.assertIn(result_idx, [0, 1])
        self.assertIsNotNone(result_segment)
        for address, stream, expected_idx in (
            (0x10000, 0, 0),
            (0x10000, 1, 1),
            (0x20000, 0, 2),
            (0x11000, 1, 1),
        ):
            segment_idx, segment = find_overlapping_segment(snapshot, address, stream=stream)
            self.assertEqual(segment_idx, expected_idx)
            self.assertIs(segment, snapshot.segments[expected_idx])
        for address, stream in ((0x10000, 2), (0x20000, 1)):
            segment_idx, segment = find_overlapping_segment(snapshot, address, stream=stream)
            self.assertEqual(segment_idx, -1)
            self.assertIsNone(segment)
        exact_idx, exact_segment = find_segment(snapshot, 0x30000, stream=1)
        self.assertEqual(exact_idx, 3)
        self.assertIs(exact_segment, snapshot.segments[3])

    def test_to_dict(self):
        result = DeviceSnapshot.from_dict({"segments": [], "device_traces": [[]]}, 0).to_dict()
        self.assertIn("segments", result)
        self.assertIn("device_traces", result)

    def test_from_dict_device_equal_to_trace_count_is_empty(self):
        snapshot = DeviceSnapshot.from_dict({"segments": [], "device_traces": [[]]}, 1)

        self.assertEqual(snapshot.device, 1)
        self.assertEqual(snapshot.trace_entries, [])
