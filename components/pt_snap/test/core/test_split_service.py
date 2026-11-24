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

from __future__ import annotations

import pickle
import shutil
from contextlib import contextmanager
from dataclasses import FrozenInstanceError
from pathlib import Path
from typing import Any

import pytest

import pt_snap_cli.core.splitting.split_service as split_module
from pt_snap_cli.core import SplitResult as ExportedSplitResult
from pt_snap_cli.core.common.errors import SplitError
from pt_snap_cli.core.common.models import SplitOptions
from pt_snap_cli.core.splitting.split_service import SplitService
from pt_snap_cli.snapshot.representation import (
    canonical_snapshot_bytes,
    canonical_snapshot_sha256,
    load_json_representation,
    load_pickle_representation,
    load_snapshot_representation,
    replay_snapshot,
    save_json_representation,
    save_pickle_representation,
    serialize_json_representation,
    serialize_pickle_representation,
)
from pt_snap_cli.snapshot.simulate import SimulateDeviceSnapshot
from pt_snap_cli.snapshot.tools.adaptors.snapshot2db import DumpEventHooker
from pt_snap_cli.snapshot.tools.slice_dump.hooker import SliceDumpHooker
from test.snapshot.golden_observations import ACTION_VALUE_MAP
from test.snapshot.helpers import FIXTURE_DIR, assert_valid_snapshot
from test.snapshot.test_file_util import UNSAFE_PICKLE_PAYLOAD, write_unsafe_reduce_pickle

MULTI_DEVICE = FIXTURE_DIR / "snapshot_with_multi_devices.pkl"


def _options(tmp_path: Path, **changes: object) -> SplitOptions:
    values: dict[str, object] = {
        "snapshot_file": MULTI_DEVICE,
        "output": tmp_path / "split",
        "slices": 2,
    }
    values.update(changes)
    return SplitOptions(**values)  # type: ignore[arg-type]


def _events(paths: tuple[Path, ...], snapshot_format: str, device: int) -> list[dict]:
    events: list[dict] = []
    for path in paths:
        representation = load_snapshot_representation(path, snapshot_format)  # type: ignore[arg-type]
        nonempty = [index for index, entries in enumerate(representation["device_traces"]) if entries]
        assert nonempty == [device]
        events.extend(representation["device_traces"][device])
    return events


def _without_ids(representation: dict[str, Any], device: int) -> dict[str, Any]:
    normalized = pickle.loads(pickle.dumps(representation))
    for event in normalized["device_traces"][device]:
        event.pop("id", None)
    return normalized


def _snapshot_state(snapshot: SimulateDeviceSnapshot) -> tuple[bytes, int, int, int]:
    device_snapshot = snapshot.device_snapshot
    return (
        canonical_snapshot_bytes([segment.to_dict() for segment in device_snapshot.segments]),
        device_snapshot.total_allocated,
        device_snapshot.total_activated,
        device_snapshot.total_reserved,
    )


def _assert_slice_invariants(paths: tuple[Path, ...], source: Path, snapshot_format: str, device: int) -> None:
    original = load_snapshot_representation(source)
    original_events = original["device_traces"][device]
    original_snapshot = SimulateDeviceSnapshot(original, device)
    original_initial = _snapshot_state(original_snapshot)
    assert_valid_snapshot(original_snapshot.device_snapshot)
    assert original_snapshot.replay()
    original_final = _snapshot_state(original_snapshot)

    combined: list[dict[str, Any]] = []
    states: list[tuple[tuple[bytes, int, int, int], tuple[bytes, int, int, int]]] = []
    for path in paths:
        representation = load_snapshot_representation(path, snapshot_format)  # type: ignore[arg-type]
        entries = representation["device_traces"][device]
        assert entries
        combined.extend(entries)
        snapshot = SimulateDeviceSnapshot(representation, device)
        assert [event.idx for event in snapshot.device_snapshot.trace_entries] == [entry["id"] for entry in entries]
        assert_valid_snapshot(snapshot.device_snapshot)
        before = _snapshot_state(snapshot)
        assert snapshot.replay()
        assert_valid_snapshot(snapshot.device_snapshot)
        states.append((before, _snapshot_state(snapshot)))

    assert [event["id"] for event in combined] == list(range(len(original_events)))
    for event, original_event in zip(combined, original_events, strict=True):
        assert {key: value for key, value in event.items() if key != "id"} == original_event
        assert event["action"] == original_event["action"]
        assert event["frames"] == original_event["frames"]
        assert event["stream"] == original_event["stream"]
    assert states[0][1] == original_final
    assert states[-1][0] == original_initial
    for previous, current in zip(states, states[1:], strict=False):
        assert current[1] == previous[0]


def _database_observation(
    snapshot_path: Path, snapshot_format: str, device: int, db_path: Path
) -> tuple[list[tuple[Any, ...]], list[tuple[Any, ...]], tuple[int, int, int]]:
    representation = load_snapshot_representation(snapshot_path, snapshot_format)  # type: ignore[arg-type]
    hooker = DumpEventHooker(str(db_path), [device])
    _, replayed = replay_snapshot(
        representation,
        device,
        hooker=hooker,
        allocator_hooker=hooker,
    )
    assert replayed
    hooker.flush(device)
    hooker.flush_callstacks()
    connection = hooker.db_handler.db.conn
    trace_rows = connection.execute(
        f"SELECT t.id, t.action, t.address, t.size, t.stream, "
        f"t.allocated, t.active, t.reserved, c.callstack "
        f"FROM trace_entry_{device} t JOIN callstack c ON c.id = t.callstackId "
        f"ORDER BY t.id"
    ).fetchall()
    block_rows = connection.execute(
        f"SELECT id, address, size, requestedSize, state, allocEventId, freeEventId FROM block_{device} ORDER BY id"
    ).fetchall()
    peaks = connection.execute(
        f"SELECT MAX(allocated), MAX(active), MAX(reserved) FROM trace_entry_{device}"
    ).fetchone()

    source_entries = representation["device_traces"][device]
    expected_actions = {entry["id"]: ACTION_VALUE_MAP[entry["action"]] for entry in source_entries}
    positive_trace_rows = [row for row in trace_rows if row[0] >= 0]
    assert {row[0]: row[1] for row in positive_trace_rows} == expected_actions
    positive_ids = set(expected_actions)
    positive_blocks = [row for row in block_rows if row[0] >= 0]
    assert all(row[0] in positive_ids and row[5] in positive_ids for row in positive_blocks)
    assert all(row[6] == -1 or row[6] in positive_ids for row in positive_blocks)
    negative_event_ids = [row[0] for row in trace_rows if row[0] < 0]
    negative_block_ids = [row[0] for row in block_rows if row[0] < 0]
    assert len(negative_event_ids) == len(set(negative_event_ids))
    assert len(negative_block_ids) == len(set(negative_block_ids))

    normalized_trace = [((-1,) + row[1:]) if row[0] < 0 else row for row in trace_rows]
    normalized_blocks = [((-1,) + row[1:]) if row[0] < 0 else row for row in block_rows]
    return normalized_trace, normalized_blocks, peaks


def test_split_options_are_frozen_and_error_has_exception_semantics(tmp_path: Path) -> None:
    options = _options(tmp_path)
    error = SplitError("argument", MULTI_DEVICE, "invalid")

    with pytest.raises(FrozenInstanceError):
        options.slices = 3  # type: ignore[misc]

    assert error.args == (str(error),)
    restored = pickle.loads(pickle.dumps(error))
    assert (restored.phase, restored.source_path, restored.detail) == (
        error.phase,
        error.source_path,
        error.detail,
    )

    @contextmanager
    def passthrough():
        yield

    with pytest.raises(SplitError) as caught:
        with passthrough():
            raise error
    assert caught.value is error


def test_split_all_devices_independently_with_deterministic_names(tmp_path: Path) -> None:
    result = SplitService().split(_options(tmp_path))

    assert isinstance(result, ExportedSplitResult)
    assert result.devices == (0, 1)
    assert [path.name for path in result.files] == [
        "snapshot_with_multi_devices__device-0__slice-0.pkl",
        "snapshot_with_multi_devices__device-0__slice-1.pkl",
        "snapshot_with_multi_devices__device-1__slice-0.pkl",
        "snapshot_with_multi_devices__device-1__slice-1.pkl",
    ]
    original = load_snapshot_representation(MULTI_DEVICE)
    for device in result.devices:
        paths = tuple(path for path in result.files if f"device-{device}" in path.name)
        assert [
            {key: value for key, value in event.items() if key != "id"} for event in _events(paths, "pickle", device)
        ] == original["device_traces"][device]
        _assert_slice_invariants(paths, MULTI_DEVICE, "pickle", device)


@pytest.mark.parametrize(
    ("fixture_name", "snapshot_format"),
    [
        ("snapshot_1768383987920985470.pkl", "pickle"),
        ("snapshot_expandable.pkl", "json"),
        ("snapshot_with_empty_cache.pkl", "pickle"),
    ],
)
def test_slice_event_and_boundary_state_invariants(tmp_path: Path, fixture_name: str, snapshot_format: str) -> None:
    source = FIXTURE_DIR / fixture_name
    result = SplitService().split(
        _options(
            tmp_path,
            snapshot_file=source,
            output=tmp_path / f"{source.stem}-{snapshot_format}",
            device=0,
            format=snapshot_format,
        )
    )

    _assert_slice_invariants(result.files, source, snapshot_format, 0)


def test_split_selected_device_with_max_entries(tmp_path: Path) -> None:
    result = SplitService().split(_options(tmp_path, slices=None, max_entries=3000, device=1))

    assert result.devices == (1,)
    assert len(result.files) == 4
    representations = [load_snapshot_representation(path) for path in result.files]
    assert all(len(value["device_traces"][1]) <= 3000 for value in representations)
    assert all(not value["device_traces"][0] for value in representations)


def test_pickle_and_json_have_equal_canonical_bytes_and_sha(tmp_path: Path) -> None:
    pickle_result = SplitService().split(_options(tmp_path, output=tmp_path / "pickle", device=0))
    json_result = SplitService().split(_options(tmp_path, output=tmp_path / "json", device=0, format="json"))

    for pickle_path, json_path in zip(pickle_result.files, json_result.files, strict=True):
        pickle_value = load_snapshot_representation(pickle_path, "pickle")
        json_value = load_snapshot_representation(json_path, "json")
        assert canonical_snapshot_bytes(pickle_value) == canonical_snapshot_bytes(json_value)
        assert canonical_snapshot_sha256(pickle_value) == canonical_snapshot_sha256(json_value)
        assert json_path.read_bytes() == canonical_snapshot_bytes(json_value)

        pickle_db = _database_observation(pickle_path, "pickle", 0, tmp_path / f"{pickle_path.name}.db")
        json_db = _database_observation(json_path, "json", 0, tmp_path / f"{json_path.name}.db")
        assert pickle_db == json_db
        trace_rows, block_rows, peaks = pickle_db
        assert peaks[0] <= peaks[1] <= peaks[2]
        assert any(row[0] < 0 for row in trace_rows)
        assert any(row[0] < 0 for row in block_rows)


def test_product_matches_upstream_ranges_and_counts_with_intentional_names(
    tmp_path: Path,
) -> None:
    representation = load_snapshot_representation(MULTI_DEVICE)
    upstream_dir = tmp_path / "upstream"
    upstream_dir.mkdir()
    upstream_snapshot = SimulateDeviceSnapshot(representation, 1)
    upstream_snapshot.register_hooker(SliceDumpHooker(str(upstream_dir), num_of_slices=2, max_entries=9700))
    assert upstream_snapshot.replay()
    upstream_files = sorted(
        upstream_dir.glob("*.pkl"),
        key=lambda path: int(path.stem.rsplit("_", 2)[-2]),
    )

    product = SplitService().split(_options(tmp_path, output=tmp_path / "product", device=1))

    assert product.devices == (1,)
    assert len(product.files) == len(upstream_files) == 2
    assert all(path.name.startswith("slice_") and "_entry_" in path.name for path in upstream_files)
    assert [path.name for path in product.files] == [
        "snapshot_with_multi_devices__device-1__slice-0.pkl",
        "snapshot_with_multi_devices__device-1__slice-1.pkl",
    ]
    for upstream_path, product_path in zip(upstream_files, product.files, strict=True):
        extended_upstream = load_snapshot_representation(upstream_path)
        product_representation = load_snapshot_representation(product_path)
        assert canonical_snapshot_bytes(_without_ids(extended_upstream, 1)) == (
            canonical_snapshot_bytes(_without_ids(product_representation, 1))
        )
        pinned_upstream_shape = _without_ids(extended_upstream, 1)
        assert all("id" not in event for event in pinned_upstream_shape["device_traces"][1])
        assert all("id" in event for event in product_representation["device_traces"][1])


@pytest.mark.parametrize(
    ("changes", "phase"),
    [
        ({"slices": None}, "argument"),
        ({"max_entries": 2}, "argument"),
        ({"slices": 0}, "argument"),
        ({"slices": -1}, "argument"),
        ({"format": "pkl"}, "argument"),
        ({"device": -1}, "device"),
        ({"device": 7}, "device"),
    ],
)
def test_invalid_boundaries_fail_before_engine(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    changes: dict[str, object],
    phase: str,
) -> None:
    called = False

    def unexpected_engine(*args: object, **kwargs: object) -> None:
        nonlocal called
        called = True

    monkeypatch.setattr("pt_snap_cli.core.splitting.split_service.replay_snapshot", unexpected_engine)
    with pytest.raises(SplitError, match=phase):
        SplitService().split(_options(tmp_path, **changes))
    assert not called


def test_path_boundaries_and_conflict_fail_before_load(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source_dir = tmp_path / "source.pkl"
    source_dir.mkdir()
    wrong_suffix = tmp_path / "source.bin"
    wrong_suffix.write_bytes(b"x")
    parent_file = tmp_path / "parent"
    parent_file.write_bytes(b"x")
    existing = tmp_path / "existing"
    existing.mkdir()
    existing_file = tmp_path / "existing-file"
    existing_file.write_bytes(b"owned")
    broken_link = tmp_path / "broken-link"
    cases = [
        _options(tmp_path, snapshot_file=tmp_path / "missing.pkl"),
        _options(tmp_path, snapshot_file=source_dir),
        _options(tmp_path, snapshot_file=wrong_suffix),
        _options(tmp_path, output=tmp_path / "missing" / "split"),
        _options(tmp_path, output=parent_file / "split"),
        _options(tmp_path, output=existing),
        _options(tmp_path, output=existing_file),
    ]
    try:
        broken_link.symlink_to(tmp_path / "missing-target", target_is_directory=True)
    except OSError:
        pass
    else:
        cases.append(_options(tmp_path, output=broken_link))
    called = False

    def unexpected_load(*args: object, **kwargs: object) -> None:
        nonlocal called
        called = True

    monkeypatch.setattr("pt_snap_cli.core.splitting.split_service.load_snapshot_representation", unexpected_load)
    for options in cases:
        with pytest.raises(SplitError):
            SplitService().split(options)
    assert not called


def test_malformed_pickle_is_load_engine_phase(tmp_path: Path) -> None:
    source = tmp_path / "malformed.pkl"
    source.write_bytes(b"not pickle")

    with pytest.raises(SplitError, match="load/engine") as caught:
        SplitService().split(_options(tmp_path, snapshot_file=source))
    assert str(source) in str(caught.value)
    assert not (tmp_path / "split").exists()


def test_unsafe_pickle_global_is_load_engine_phase(tmp_path: Path) -> None:
    source = write_unsafe_reduce_pickle(tmp_path / "evil.pkl")

    with pytest.raises(SplitError, match="unsafe pickle") as caught:
        SplitService().split(_options(tmp_path, snapshot_file=source))
    assert caught.value.phase == "load/engine"
    assert "Unsafe pickle" in caught.value.detail
    assert str(source) in str(caught.value)
    assert UNSAFE_PICKLE_PAYLOAD["executed"] is False
    assert not (tmp_path / "split").exists()


def test_no_nonempty_device_is_device_phase(tmp_path: Path) -> None:
    source = tmp_path / "empty.pkl"
    source.write_bytes(pickle.dumps({"segments": [], "device_traces": [[], []]}))

    with pytest.raises(SplitError, match="device"):
        SplitService().split(_options(tmp_path, snapshot_file=source))
    assert not (tmp_path / "split").exists()


def test_workspace_marker_splits_and_replays(tmp_path: Path) -> None:
    source = tmp_path / "workspace.pkl"
    source.write_bytes(
        pickle.dumps(
            {
                "segments": [],
                "device_traces": [
                    [
                        {
                            "action": "workspace_snapshot",
                            "addr": 1,
                            "size": 1,
                            "stream": 0,
                            "frames": [],
                        }
                    ]
                ],
            }
        )
    )

    result = SplitService().split(_options(tmp_path, snapshot_file=source, slices=1))

    assert len(result.files) == 1
    assert load_snapshot_representation(result.files[0])["device_traces"][0][0]["action"] == ("workspace_snapshot")


def test_generated_validation_failure_cleans_owned_stage(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    real_replay = split_module.replay_snapshot
    calls = 0

    def fail_generated_replay(*args: object, **kwargs: object):
        nonlocal calls
        calls += 1
        if calls > 1:
            raise ValueError("generated invalid")
        return real_replay(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(split_module, "replay_snapshot", fail_generated_replay)
    with pytest.raises(SplitError, match="generated-validation"):
        SplitService().split(_options(tmp_path, device=0))
    assert not (tmp_path / "split").exists()
    assert not list(tmp_path.glob(".split.pt-snap-*"))


@pytest.mark.parametrize("missing_device", [False, True])
def test_generated_slice_requires_nonempty_target_device_before_replay(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, missing_device: bool
) -> None:
    real_save = split_module.save_snapshot_representation
    real_replay = split_module.replay_snapshot
    replay_calls = 0

    def save_without_target_events(representation: dict[str, Any], path: Path, snapshot_format: str) -> None:
        damaged = pickle.loads(pickle.dumps(representation))
        damaged["device_traces"] = [] if missing_device else [[]]
        real_save(damaged, path, snapshot_format)  # type: ignore[arg-type]

    monkeypatch.setattr(split_module, "save_snapshot_representation", save_without_target_events)

    def track_replay(*args: object, **kwargs: object):
        nonlocal replay_calls
        replay_calls += 1
        if replay_calls > 1:
            pytest.fail("generated slice must not replay")
        return real_replay(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(split_module, "replay_snapshot", track_replay)

    with pytest.raises(SplitError, match="generated slice has no trace entries for device 0"):
        SplitService().split(_options(tmp_path, device=0))
    assert replay_calls == 1
    assert not (tmp_path / "split").exists()
    assert not list(tmp_path.glob(".split.pt-snap-*"))


def test_engine_failure_is_mapped_and_cleans_owned_stage(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_engine(*args: object, **kwargs: object) -> None:
        raise RuntimeError("engine failed")

    monkeypatch.setattr("pt_snap_cli.core.splitting.split_service.replay_snapshot", fail_engine)
    with pytest.raises(SplitError, match="load/engine"):
        SplitService().split(_options(tmp_path, device=0))
    assert not (tmp_path / "split").exists()
    assert not list(tmp_path.glob(".split.pt-snap-*"))


def test_publication_failure_is_mapped_and_cleans_owned_stage(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_publish(*args: object, **kwargs: object) -> None:
        raise OSError("publish failed")

    monkeypatch.setattr(SplitService, "_publish_directory", staticmethod(fail_publish))
    with pytest.raises(SplitError, match="publication"):
        SplitService().split(_options(tmp_path, device=0))
    assert not (tmp_path / "split").exists()
    assert not list(tmp_path.glob(".split.pt-snap-*"))


@pytest.mark.parametrize(
    ("failure", "phase", "detail"),
    [
        ("engine", "load/engine", "engine primary"),
        ("generated", "generated-validation", "generated primary"),
        ("publication", "publication", "publication primary"),
    ],
)
def test_cleanup_failure_never_masks_primary_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure: str,
    phase: str,
    detail: str,
) -> None:
    if failure == "engine":
        monkeypatch.setattr(
            "pt_snap_cli.core.splitting.split_service.replay_snapshot",
            lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError(detail)),
        )
    elif failure == "generated":
        real_replay = split_module.replay_snapshot
        replay_calls = 0

        def fail_generated_replay(*args: object, **kwargs: object):
            nonlocal replay_calls
            replay_calls += 1
            if replay_calls > 1:
                raise ValueError(detail)
            return real_replay(*args, **kwargs)  # type: ignore[arg-type]

        monkeypatch.setattr(split_module, "replay_snapshot", fail_generated_replay)
    else:
        monkeypatch.setattr(
            SplitService,
            "_publish_directory",
            staticmethod(lambda *args: (_ for _ in ()).throw(OSError(detail))),
        )

    real_rmtree = shutil.rmtree

    def fail_stage_cleanup(path: Path, *args: object, **kwargs: object) -> None:
        if Path(path).name.startswith(".split.pt-snap-"):
            raise OSError("cleanup secondary")
        real_rmtree(path, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr("pt_snap_cli.core.splitting.split_service.shutil.rmtree", fail_stage_cleanup)
    with pytest.raises(SplitError) as caught:
        SplitService().split(_options(tmp_path, device=0))
    assert caught.value.phase == phase
    assert detail in caught.value.detail
    assert "cleanup secondary" not in str(caught.value)


def test_stage_substitution_is_not_cleaned_and_primary_error_survives(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    substituted: Path | None = None

    def replace_stage(
        self: SplitService,
        representation: dict[str, object],
        source: Path,
        stage: Path,
        device: int,
        slices: int | None,
        max_entries: int | None,
        output_format: str,
    ) -> list[Path]:
        nonlocal substituted
        shutil.rmtree(stage)
        stage.mkdir()
        (stage / "other-owner.txt").write_text("preserve", encoding="utf-8")
        substituted = stage
        raise SplitError("load/engine", source, "stage substitution primary")

    monkeypatch.setattr(SplitService, "_slice_device", replace_stage)
    with pytest.raises(SplitError, match="stage substitution primary") as caught:
        SplitService().split(_options(tmp_path, device=0))
    assert caught.value.phase == "load/engine"
    assert substituted is not None
    assert (substituted / "other-owner.txt").read_text(encoding="utf-8") == "preserve"


def test_stage_identity_closes_descriptor_when_fstat_fails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    if split_module.os.name == "nt":
        pytest.skip("Windows does not open a staging directory descriptor")
    real_open = split_module.os.open
    real_fstat = split_module.os.fstat
    descriptors: list[int] = []

    def recording_open(*args: object) -> int:
        descriptor = real_open(*args)  # type: ignore[arg-type]
        if args[0] == tmp_path:
            descriptors.append(descriptor)
        return descriptor

    def fail_stage_fstat(descriptor: int) -> object:
        if descriptor in descriptors:
            raise OSError("fstat failed")
        return real_fstat(descriptor)

    with pytest.raises(OSError, match="fstat failed"):
        # os is a process-wide module: do not inject faults into pytest's own
        # file inspection, and restore it before pytest handles the exception.
        with monkeypatch.context() as patch:
            patch.setattr(split_module.os, "open", recording_open)
            patch.setattr(split_module.os, "fstat", fail_stage_fstat)
            SplitService._stage_identity(tmp_path)

    assert len(descriptors) == 1
    with pytest.raises(OSError):
        real_fstat(descriptors[0])


@pytest.mark.parametrize("nonempty", [False, True])
def test_publication_race_does_not_replace_or_merge_destination(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, nonempty: bool
) -> None:
    real_publish = SplitService._publish_directory

    def race(stage: Path, destination: Path) -> None:
        destination.mkdir()
        if nonempty:
            (destination / "racer.txt").write_text("racer", encoding="utf-8")
        real_publish(stage, destination)

    monkeypatch.setattr(SplitService, "_publish_directory", staticmethod(race))
    with pytest.raises(SplitError, match="publication"):
        SplitService().split(_options(tmp_path, device=0))
    assert (tmp_path / "split").is_dir()
    assert list((tmp_path / "split").iterdir()) == ([tmp_path / "split" / "racer.txt"] if nonempty else [])
    assert not list(tmp_path.glob(".split.pt-snap-*"))


def test_publication_file_race_is_not_replaced(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    real_publish = SplitService._publish_directory

    def race(stage: Path, destination: Path) -> None:
        destination.write_text("racer", encoding="utf-8")
        real_publish(stage, destination)

    monkeypatch.setattr(SplitService, "_publish_directory", staticmethod(race))
    with pytest.raises(SplitError, match="publication"):
        SplitService().split(_options(tmp_path, device=0))
    assert (tmp_path / "split").read_text(encoding="utf-8") == "racer"
    assert not list(tmp_path.glob(".split.pt-snap-*"))


@pytest.mark.parametrize("broken", [False, True])
def test_publication_symlink_race_is_not_replaced(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, broken: bool
) -> None:
    probe = tmp_path / "probe"
    try:
        probe.symlink_to(tmp_path / "probe-target", target_is_directory=True)
    except OSError:
        pytest.skip("directory symlinks are unavailable")
    probe.unlink()

    target = tmp_path / "target"
    if not broken:
        target.mkdir()
    real_publish = SplitService._publish_directory
    original_targets = []

    def race(stage: Path, destination: Path) -> None:
        destination.symlink_to(target, target_is_directory=True)
        original_targets.append(destination.readlink())
        real_publish(stage, destination)

    monkeypatch.setattr(SplitService, "_publish_directory", staticmethod(race))
    with pytest.raises(SplitError, match="publication"):
        SplitService().split(_options(tmp_path, device=0))
    assert (tmp_path / "split").is_symlink()
    # Windows reports an extended-length target; compare before/after exactly.
    assert [(tmp_path / "split").readlink()] == original_targets
    assert not list(tmp_path.glob(".split.pt-snap-*"))


def test_linux_symbol_absence_fails_before_load_engine_or_stage(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(split_module.sys, "platform", "linux")
    monkeypatch.setattr(split_module.ctypes, "CDLL", lambda *args, **kwargs: object())
    monkeypatch.setattr(
        split_module,
        "load_snapshot_representation",
        lambda *args, **kwargs: pytest.fail("source must not load"),
    )
    monkeypatch.setattr(
        split_module.tempfile,
        "mkdtemp",
        lambda *args, **kwargs: pytest.fail("stage must not be created"),
    )

    with pytest.raises(SplitError, match="publication") as caught:
        SplitService().split(_options(tmp_path, device=0))
    assert "renameat2(RENAME_NOREPLACE) is unavailable" in caught.value.detail
    assert not list(tmp_path.glob(".split.pt-snap-*"))


class _FakeRename:
    def __init__(self) -> None:
        self.calls: list[tuple[object, ...]] = []
        self.argtypes: object = None
        self.restype: object = None

    def __call__(self, *args: object) -> int:
        self.calls.append(args)
        return 0


@pytest.mark.parametrize(
    ("platform", "symbol", "expected"),
    [
        ("linux", "renameat2", (-100, b"stage", -100, b"destination", 1)),
        ("darwin", "renamex_np", (b"stage", b"destination", 4)),
    ],
)
def test_platform_no_replace_constants_and_calls(
    monkeypatch: pytest.MonkeyPatch,
    platform: str,
    symbol: str,
    expected: tuple[object, ...],
) -> None:
    rename = _FakeRename()
    library = type("FakeLibrary", (), {symbol: rename})()
    monkeypatch.setattr(split_module.sys, "platform", platform)
    monkeypatch.setattr(split_module.ctypes, "CDLL", lambda *args, **kwargs: library)

    SplitService._preflight_publication()
    SplitService._publish_directory(Path("stage"), Path("destination"))

    assert rename.calls == [expected]


def test_canonicalization_rejects_unsupported_values() -> None:
    for value in ({1: "bad"}, {"x": float("nan")}, {"x": object()}):
        with pytest.raises(ValueError):
            canonical_snapshot_bytes(value)


def test_explicit_pickle_json_representation_apis_round_trip(tmp_path: Path) -> None:
    value = {"tuple": (1, 2), "unicode": "内存", "ordered": [3, 1, 2]}
    pickle_path = tmp_path / "value.pkl"
    json_path = tmp_path / "value.json"

    save_pickle_representation(value, pickle_path)
    save_json_representation(value, json_path)

    assert pickle_path.read_bytes() == serialize_pickle_representation(value)
    assert json_path.read_bytes() == serialize_json_representation(value)
    assert canonical_snapshot_bytes(load_pickle_representation(pickle_path)) == canonical_snapshot_bytes(
        load_json_representation(json_path)
    )
