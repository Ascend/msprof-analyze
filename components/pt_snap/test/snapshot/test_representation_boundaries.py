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

"""Representation dispatch, canonical values and real replay entrypoint contracts."""

import copy
import hashlib
import json
from pathlib import Path
from typing import cast

import pytest

from pt_snap_cli.snapshot.base import DeviceSnapshot, Segment, TraceEntry
from pt_snap_cli.snapshot.representation import (
    SnapshotFormat,
    canonical_snapshot_bytes,
    canonical_snapshot_sha256,
    canonicalize_snapshot,
    load_and_replay_snapshot,
    load_snapshot_representation,
    replay_snapshot,
    save_snapshot_representation,
    serialize_snapshot_representation,
)
from pt_snap_cli.snapshot.simulate import AllocatorHooker, SimulateHooker

from .helpers import assert_valid_snapshot


def _representation() -> dict[str, object]:
    frames = [{"filename": "test.py", "name": "allocate", "line": 17}]
    return {
        "segments": [
            {
                "address": 4096,
                "total_size": 64,
                "stream": 0,
                "segment_type": "small",
                "allocated_size": 0,
                "active_size": 0,
                "device": 1,
                "frames": copy.deepcopy(frames),
                "blocks": [],
            }
        ],
        "device_traces": [
            [],
            [
                {
                    "id": 17,
                    "action": "segment_alloc",
                    "addr": 4096,
                    "size": 64,
                    "stream": 0,
                    "frames": frames,
                }
            ],
        ],
        "metadata": {"label": "内存", "ratio": 1.25, "optional": None},
    }


@pytest.mark.parametrize("snapshot_format", ["pickle", "json"])
@pytest.mark.parametrize("valid_replay", [True, False])
def test_dispatch_round_trip_and_replay_preserve_source(
    tmp_path: Path, snapshot_format: SnapshotFormat, valid_replay: bool
) -> None:
    value = _representation()
    if not valid_replay:
        # The event cannot be undone without its segment: replay must report False.
        value["segments"] = []
    original = copy.deepcopy(value)
    path = tmp_path / f"snapshot.{snapshot_format}"
    encoded = serialize_snapshot_representation(value, snapshot_format)
    save_snapshot_representation(value, str(path), snapshot_format)
    assert path.read_bytes() == encoded
    assert load_snapshot_representation(str(path), snapshot_format) == original

    loaded, runtime, replayed = load_and_replay_snapshot(path, snapshot_format, 1)

    assert loaded == original == value
    assert runtime.device == 1
    assert replayed is valid_replay
    assert [entry.idx for entry in runtime.device_snapshot.trace_entries] == ([] if valid_replay else [17])
    assert runtime.device_snapshot.segments == []
    assert runtime.device_snapshot.total_reserved == 0
    assert_valid_snapshot(runtime.device_snapshot)
    assert path.read_bytes() == encoded
    assert list(tmp_path.iterdir()) == [path]


def test_default_dispatch_uses_protocol_four_pickle(tmp_path: Path) -> None:
    value = _representation()
    path = tmp_path / "snapshot.pkl"
    encoded = serialize_snapshot_representation(value)
    assert encoded.startswith(b"\x80\x04")
    save_snapshot_representation(value, path)
    assert path.read_bytes() == encoded
    assert load_snapshot_representation(path) == value


@pytest.mark.parametrize("exists", [True, False])
def test_unsupported_formats_do_not_read_or_overwrite_outputs(tmp_path: Path, exists: bool):
    path = tmp_path / "snapshot.yaml"
    sentinel = b"existing output must be preserved"
    if exists:
        path.write_bytes(sentinel)
    value = _representation()
    original = copy.deepcopy(value)
    unsupported = cast(SnapshotFormat, "yaml")

    with pytest.raises(ValueError, match="Unsupported snapshot format: yaml"):
        load_snapshot_representation(path, unsupported)
    with pytest.raises(ValueError, match="Unsupported snapshot format: yaml"):
        serialize_snapshot_representation(value, unsupported)
    with pytest.raises(ValueError, match="Unsupported snapshot format: yaml"):
        save_snapshot_representation(value, path, unsupported)

    assert value == original
    assert path.exists() is exists
    if exists:
        assert path.read_bytes() == sentinel
    assert list(tmp_path.iterdir()) == ([path] if exists else [])


@pytest.mark.parametrize("value", [None, [], "snapshot", 7, 1.25, True])
def test_json_requires_object_without_rewriting_source(tmp_path: Path, value: object):
    path = tmp_path / "snapshot.json"
    original = json.dumps(value).encode()
    path.write_bytes(original)
    with pytest.raises(ValueError, match=f"actual type: {type(value).__name__}"):
        load_snapshot_representation(path, "json")
    assert path.read_bytes() == original
    assert list(tmp_path.iterdir()) == [path]


def test_canonical_finite_values_preserve_sequence_order_and_utf8():
    value = {"z": (None, True, -7, 1.25, -0.0), "a": {"标签": "内存", "order": [3, 1, 2]}}
    original = copy.deepcopy(value)
    expected = '{"a":{"order":[3,1,2],"标签":"内存"},"z":[null,true,-7,1.25,-0.0]}'.encode()
    assert canonical_snapshot_bytes(value) == expected
    assert canonical_snapshot_sha256(value) == hashlib.sha256(expected).hexdigest()
    assert canonicalize_snapshot(value) == json.loads(expected)
    assert value == original


@pytest.mark.parametrize("value", [float("inf"), float("-inf")])
def test_json_nonfinite_values_do_not_replace_previous_output(tmp_path: Path, value: float):
    path = tmp_path / "snapshot.json"
    path.write_bytes(b"previous output")
    with pytest.raises(ValueError, match="non-finite floats"):
        save_snapshot_representation({"nested": [value]}, path, "json")
    assert path.read_bytes() == b"previous output"
    assert list(tmp_path.iterdir()) == [path]


class _ReplayObserver(SimulateHooker):
    def __init__(self) -> None:
        self.calls: list[tuple[str, int, int]] = []
        self.raw_frames: list[bool] = []

    def pre_undo_event(self, event: TraceEntry, snapshot: DeviceSnapshot) -> bool:
        self.calls.append(("pre", event.idx, snapshot.total_reserved))
        self.raw_frames.append(event._raw_frames is not None)
        return True

    def post_undo_event(self, event: TraceEntry, snapshot: DeviceSnapshot) -> bool:
        self.calls.append(("post", event.idx, snapshot.total_reserved))
        return True


class _AllocatorObserver(AllocatorHooker):
    def __init__(self) -> None:
        self.calls: list[tuple[str, int, int]] = []

    def pre_replay_unmap_or_free_segment(self, segment: Segment, snapshot: DeviceSnapshot):
        self.calls.append(("pre", segment.address, snapshot.total_reserved))

    def post_replay_unmap_or_free_segment(self, segment: Segment, snapshot: DeviceSnapshot):
        self.calls.append(("post", segment.address, snapshot.total_reserved))


@pytest.mark.parametrize(
    ("with_event_hook", "with_allocator_hook"),
    [(False, False), (True, False), (False, True), (True, True)],
)
@pytest.mark.parametrize("raw_frames", [False, True])
def test_replay_entrypoint_registers_optional_hooks_before_real_replay(
    with_event_hook: bool, with_allocator_hook: bool, raw_frames: bool
) -> None:
    value = _representation()
    original = copy.deepcopy(value)
    event_hook = _ReplayObserver()
    allocator_hook = _AllocatorObserver()

    runtime, replayed = replay_snapshot(
        value,
        1,
        hooker=event_hook if with_event_hook else None,
        allocator_hooker=allocator_hook if with_allocator_hook else None,
        _raw_frames=raw_frames,
    )

    assert replayed is True
    assert runtime.device == 1
    assert event_hook.calls == ([("pre", 17, 64), ("post", 17, 0)] if with_event_hook else [])
    assert event_hook.raw_frames == ([raw_frames] if with_event_hook else [])
    assert allocator_hook.calls == ([("pre", 4096, 64), ("post", 4096, 0)] if with_allocator_hook else [])
    assert runtime.device_snapshot.trace_entries == []
    assert runtime.device_snapshot.segments == []
    assert_valid_snapshot(runtime.device_snapshot)
    assert value == original
