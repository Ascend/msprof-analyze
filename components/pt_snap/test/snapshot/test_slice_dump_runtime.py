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

import json
import pickle
from pathlib import Path

import pytest

from pt_snap_cli.snapshot.base import DeviceSnapshot, Segment, TraceEntry
from pt_snap_cli.snapshot.representation import load_snapshot_representation, replay_snapshot
from pt_snap_cli.snapshot.simulate import SimulateDeviceSnapshot
from pt_snap_cli.snapshot.tools.slice_dump.dump import run_slice_dump
from pt_snap_cli.snapshot.tools.slice_dump.hooker import SliceDumpHooker
from test.snapshot.helpers import FIXTURE_DIR


@pytest.mark.parametrize(
    "fixture_name",
    ["snapshot_with_empty_cache.pkl", "snapshot_with_empty_cache_expandable.pkl"],
)
def test_upstream_slice_runtime_replays_all_default_slices(tmp_path: Path, fixture_name: str) -> None:
    representation = load_snapshot_representation(FIXTURE_DIR / fixture_name)
    snapshot = SimulateDeviceSnapshot(representation, 0)
    total_entries = len(representation["device_traces"][0])
    expected_slices = max(total_entries // 15000, 4)
    hooker = SliceDumpHooker(str(tmp_path))
    snapshot.register_hooker(hooker)

    assert snapshot.replay()
    outputs = list(tmp_path.glob("*.pkl"))
    assert len(outputs) == expected_slices
    for output in outputs:
        _, _, replayed = _load_replay(output, "pickle", 0)
        assert replayed


def _load_replay(path: Path, snapshot_format: str, device: int):
    representation = load_snapshot_representation(path, snapshot_format)  # type: ignore[arg-type]
    snapshot, replayed = replay_snapshot(representation, device)
    return representation, snapshot, replayed


def _make_snapshot(entries_count: int) -> DeviceSnapshot:
    snapshot = DeviceSnapshot()
    snapshot.device = 0
    snapshot.segments = []
    snapshot.trace_entries = [
        TraceEntry(action="alloc", addr=index, size=1, stream=0, idx=index) for index in range(entries_count)
    ]
    return snapshot


def test_slice_dump_hooker_rejects_invalid_directory(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        SliceDumpHooker(str(tmp_path / "missing"), num_of_slices=1)


def test_slice_dump_hooker_strategy_and_warning_match_upstream(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    hooker = SliceDumpHooker(str(tmp_path), num_of_slices=2, max_entries=3)
    hooker.num_of_events = 10

    hooker._init_splitting_strategy()

    assert hooker.max_entries == 3
    assert hooker.num_of_slices == 4
    assert "single snapshot file exceeds the max_entries limit" in caplog.text


def test_slice_dump_hooker_rejects_strategy_init_before_event_count(tmp_path: Path) -> None:
    hooker = SliceDumpHooker(str(tmp_path), num_of_slices=2, max_entries=3)

    with pytest.raises(RuntimeError, match="before init total entries"):
        hooker._init_splitting_strategy()


def test_slice_dump_hooker_rejects_dump_before_previous_segments(tmp_path: Path) -> None:
    hooker = SliceDumpHooker(str(tmp_path), num_of_slices=2, max_entries=3)

    with pytest.raises(RuntimeError, match="before capturing previous segments"):
        hooker.dump(device=0)


def test_slice_dump_hooker_json_dump_uses_utf8(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    hooker = SliceDumpHooker(str(tmp_path), num_of_slices=2, max_entries=2, dump_type="json")
    hooker.num_of_events = 4
    hooker.prev_segments = []
    hooker.events_buffer = [TraceEntry(action="内存", addr=1, size=2, stream=0, idx=1)]
    real_open = open
    encodings: list[str | None] = []

    def recording_open(*args, **kwargs):
        encodings.append(kwargs.get("encoding"))
        return real_open(*args, **kwargs)

    monkeypatch.setattr("builtins.open", recording_open)

    hooker.dump(device=0)

    assert encodings == ["utf-8"]
    outputs = list(tmp_path.glob("*.json"))
    assert len(outputs) == 1
    payload = json.loads(outputs[0].read_text(encoding="utf-8"))
    assert payload["device_traces"][0][0]["id"] == 1
    assert payload["device_traces"][0][0]["action"] == "内存"


def test_slice_dump_ids_do_not_mutate_origin_and_loading_honors_them(tmp_path: Path) -> None:
    origin = {
        "action": "workspace_snapshot",
        "addr": 1,
        "size": 2,
        "stream": 3,
        "frames": [],
    }
    representation = {"segments": [], "device_traces": [[origin]]}
    snapshot = SimulateDeviceSnapshot(representation, 0)
    hooker = SliceDumpHooker(str(tmp_path), num_of_slices=1, max_entries=1)
    snapshot.register_hooker(hooker)

    assert snapshot.replay()
    assert "id" not in origin
    output = next(tmp_path.glob("*.pkl"))
    loaded = load_snapshot_representation(output)
    assert loaded["device_traces"][0][0]["id"] == 0
    reloaded = SimulateDeviceSnapshot(loaded, 0)
    assert reloaded.device_snapshot.trace_entries[0].idx == 0

    mixed = DeviceSnapshot.from_dict(
        {
            "segments": [],
            "device_traces": [
                [
                    {**origin, "id": 42},
                    {"action": "alloc", "addr": 2, "size": 2, "stream": 3, "frames": []},
                ]
            ],
        },
        0,
    )
    assert [event.idx for event in mixed.trace_entries] == [42, 1]


def test_slice_dump_hooker_resets_buffers_after_dump(tmp_path: Path) -> None:
    hooker = SliceDumpHooker(str(tmp_path), num_of_slices=1, max_entries=1)
    hooker.num_of_events = 1
    hooker.prev_segments = []
    event = TraceEntry(action="alloc", addr=1, size=2, stream=0, idx=1)

    hooker.post_undo_event(event, _make_snapshot(0))

    assert hooker.events_buffer == []
    assert hooker.dump_count == 1


def test_slice_dump_hooker_preserves_state_when_write_fails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    hooker = SliceDumpHooker(str(tmp_path), num_of_slices=1, max_entries=1)
    hooker.num_of_events = 1
    segments: list[Segment] = []
    event = TraceEntry(action="alloc", addr=1, size=2, stream=0, idx=1)
    hooker.prev_segments = segments
    hooker.events_buffer = [event]
    monkeypatch.setattr(
        "pt_snap_cli.snapshot.tools.slice_dump.hooker.save_dict_to_pickle",
        lambda *args, **kwargs: (_ for _ in ()).throw(OSError("disk full")),
    )

    with pytest.raises(OSError, match="disk full"):
        hooker.dump(device=0)

    assert hooker.prev_segments is segments
    assert hooker.events_buffer == [event]
    assert hooker.dump_count == 0


def test_run_slice_dump_retains_upstream_empty_trace_warning_and_return(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    source = tmp_path / "empty.pkl"
    source.write_bytes(pickle.dumps({"segments": [], "device_traces": []}))

    result = run_slice_dump(str(source), dump_dir=str(tmp_path))

    assert result is None
    assert "no event records cannot be replayed or split" in caplog.text


def test_run_slice_dump_rejects_negative_device(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "snapshot.pkl"
    source.write_bytes(
        pickle.dumps(
            {
                "segments": [],
                "device_traces": [[{"action": "alloc", "addr": 1, "size": 1, "stream": 0, "frames": []}]],
            }
        )
    )
    monkeypatch.setattr(
        "pt_snap_cli.snapshot.tools.slice_dump.dump.replay_snapshot",
        lambda *args, **kwargs: pytest.fail("negative device must not replay"),
    )

    result = run_slice_dump(str(source), device=-1, dump_dir=str(tmp_path))

    assert result is None
    assert "specified device -1" in caplog.text
    assert not list(tmp_path.glob("slice_*"))
