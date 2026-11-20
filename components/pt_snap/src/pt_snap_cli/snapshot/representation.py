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

# pyright: reportAny=error, reportExplicitAny=error, reportUnknownArgumentType=error, reportUnknownVariableType=error, reportUnknownMemberType=error

import hashlib
import json
import math
import pickle  # nosec B403 # Trusted snapshot format; restricted loader and consent boundary are documented.
from pathlib import Path
from typing import Dict, List, Tuple, Union, cast

from typing_extensions import Literal

from .simulate import AllocatorHooker, SimulateDeviceSnapshot, SimulateHooker

# pylint: disable-next=useless-import-alias  # Public re-export, also explicit for static type checkers.
from .util.file_util import UnsafePickleError as UnsafePickleError
from .util.file_util import load_pickle_to_dict, save_dict_to_pickle

SnapshotFormat = Literal["pickle", "json"]


def load_pickle_representation(snapshot_file: Union[str, Path]) -> Dict[str, object]:
    """Load a trusted pickle snapshot representation."""
    return cast(Dict[str, object], load_pickle_to_dict(Path(snapshot_file)))


def load_json_representation(snapshot_file: Union[str, Path]) -> Dict[str, object]:
    """Load a JSON snapshot representation."""
    with Path(snapshot_file).open(encoding="utf-8") as stream:
        value = cast(object, json.load(stream))
    if not isinstance(value, dict):
        raise ValueError(f"The content of the JSON file is not of type dict, actual type: {type(value).__name__}")
    return cast(Dict[str, object], value)


def load_snapshot_representation(
    snapshot_file: Union[str, Path], snapshot_format: SnapshotFormat = "pickle"
) -> Dict[str, object]:
    """Load either supported representation through one dispatch point."""
    if snapshot_format == "pickle":
        return load_pickle_representation(snapshot_file)
    if snapshot_format == "json":
        return load_json_representation(snapshot_file)
    raise ValueError(f"Unsupported snapshot format: {snapshot_format}")


def serialize_snapshot_representation(
    representation: Dict[str, object], snapshot_format: SnapshotFormat = "pickle"
) -> bytes:
    """Serialize a snapshot in its supported pickle or normalized JSON form."""
    if snapshot_format == "pickle":
        return serialize_pickle_representation(representation)
    if snapshot_format == "json":
        return serialize_json_representation(representation)
    raise ValueError(f"Unsupported snapshot format: {snapshot_format}")


def serialize_pickle_representation(representation: Dict[str, object]) -> bytes:
    """Serialize the complete runtime-coupled pickle representation."""
    return pickle.dumps(representation, protocol=4)


def serialize_json_representation(representation: Dict[str, object]) -> bytes:
    """Serialize the normalized inspectable JSON representation."""
    return canonical_snapshot_bytes(representation)


def save_pickle_representation(representation: Dict[str, object], snapshot_file: Union[str, Path]) -> None:
    """Save a trusted pickle snapshot using the retained protocol."""
    save_dict_to_pickle(representation, Path(snapshot_file), protocol=4)


def save_json_representation(representation: Dict[str, object], snapshot_file: Union[str, Path]) -> None:
    """Save normalized compact UTF-8 JSON."""
    _ = Path(snapshot_file).write_bytes(serialize_json_representation(representation))


def save_snapshot_representation(
    representation: Dict[str, object],
    snapshot_file: Union[str, Path],
    snapshot_format: SnapshotFormat = "pickle",
) -> None:
    """Save a snapshot representation without caller-specific format behavior."""
    path = Path(snapshot_file)
    if snapshot_format == "pickle":
        save_pickle_representation(representation, path)
        return
    if snapshot_format == "json":
        save_json_representation(representation, path)
        return
    raise ValueError(f"Unsupported snapshot format: {snapshot_format}")


def canonicalize_snapshot(value: object) -> object:
    """Normalize supported snapshot values without changing semantic list order."""
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("Canonical snapshots do not support non-finite floats.")
        return value
    if isinstance(value, dict):
        normalized: Dict[str, object] = {}
        mapping = cast(Dict[object, object], value)
        if not all(isinstance(key, str) for key in mapping):
            raise ValueError("Canonical snapshots require string dictionary keys.")
        for key in sorted(cast(Dict[str, object], mapping)):
            normalized[key] = canonicalize_snapshot(mapping[key])
        return normalized
    if isinstance(value, (list, tuple)):
        return [canonicalize_snapshot(item) for item in cast(Union[List[object], Tuple[object, ...]], value)]
    raise ValueError(f"Canonical snapshots do not support {type(value).__name__} values.")


def canonical_snapshot_bytes(representation: object) -> bytes:
    """Return canonical UTF-8 JSON bytes for representation equivalence."""
    return json.dumps(
        canonicalize_snapshot(representation),
        sort_keys=True,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
    ).encode("utf-8")


def canonical_snapshot_sha256(representation: object) -> str:
    """Return the SHA256 of the canonical snapshot bytes."""
    return hashlib.sha256(canonical_snapshot_bytes(representation)).hexdigest()


def replay_snapshot(
    representation: Dict[str, object],
    device: int,
    *,
    hooker: Union[SimulateHooker, None] = None,
    allocator_hooker: Union[AllocatorHooker, None] = None,
    _raw_frames: bool = False,
) -> Tuple[SimulateDeviceSnapshot, bool]:
    """Construct and replay one device through the shared snapshot runtime."""
    snapshot = SimulateDeviceSnapshot(representation, device, _raw_frames=_raw_frames)
    if hooker is not None:
        _ = snapshot.register_hooker(hooker)
    if allocator_hooker is not None:
        _ = snapshot.register_allocator_hooker(allocator_hooker)
    return snapshot, snapshot.replay()


def load_and_replay_snapshot(
    snapshot_file: Union[str, Path],
    snapshot_format: SnapshotFormat,
    device: int,
) -> Tuple[Dict[str, object], SimulateDeviceSnapshot, bool]:
    """Load and replay either format through the shared validation entrypoint."""
    representation = load_snapshot_representation(snapshot_file, snapshot_format)
    snapshot, replayed = replay_snapshot(representation, device)
    return representation, snapshot, replayed
