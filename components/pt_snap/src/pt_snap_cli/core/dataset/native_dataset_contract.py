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

"""Original published pt-snap native-v2 protocol; NOT compatibility-v1/msinsight.

Counts/capacity use original positions per device. IDs stay sparse and original.
Only closed, finalized artifacts are accepted; unknown extensions grant no capabilities.
"""

from __future__ import annotations

import json
import re
import sqlite3
from contextlib import closing
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, List, Set, Tuple, Union, cast

from pt_snap_cli.core.common.models import ImportMetadata
from pt_snap_cli.core.common.validation_budget import (
    ValidationBudget,
    check_budget,
    checked_rows,
    sqlite_timeout,
    validation_progress,
)
from pt_snap_cli.core.dataset.dataset_contract import (
    ACTION_NAMES,
    BLOCK_COLUMNS,
    BLOCK_STATES,
    DICTIONARY_COLUMNS,
    TRACE_COLUMNS,
    DatasetContractError,
    DatasetManifest,
    DatasetValidation,
    DeviceRecord,
    QueryScope,
    SliceRecord,
    _array,
    _integer,
    _need,
    _object,
    _safe_file,
    _schema,
    _text,
    _unique_object,
)
from pt_snap_cli.core.dataset.dataset_files import hash_file as _hash_file
from pt_snap_cli.core.dataset.dataset_files import (
    require_readonly_member as _require_readonly_member,
)
from pt_snap_cli.core.importing.import_metadata_contract import metadata_from_mapping
from pt_snap_cli.core.splitting.sharded_replay_service import ShardedReplayResult

NATIVE_FORMAT = "pt-snap-native-v2"
NATIVE_MANIFEST_VERSION = 1
# Semantic contracts, deliberately independent of the installed CLI __version__.
NATIVE_FORMAT_VERSION = 1
NATIVE_IMPORT_VERSION = 1
NATIVE_EXTENSION_VERSION = 2


@dataclass(frozen=True)
class NativeSlice(SliceRecord):
    start_position: int
    end_position: int
    sha256: str


@dataclass(frozen=True)
class NativeManifest(DatasetManifest):
    identity: Dict[str, object]
    metadata: ImportMetadata
    omitted_devices: Tuple[int, ...]


def cache_identity(source_sha256: str, device: Union[int, None], capacity: int) -> Dict[str, object]:
    return {
        "sourceSha256": source_sha256,
        "requestedDevice": device,
        "eventsPerSlice": capacity,
        "outputFormat": NATIVE_FORMAT,
        "manifestContractVersion": NATIVE_MANIFEST_VERSION,
        "formatContractVersion": NATIVE_FORMAT_VERSION,
        "importContractVersion": NATIVE_IMPORT_VERSION,
        "extensionContractVersion": NATIVE_EXTENSION_VERSION,
        "metadataSchemaVersion": 1,
        "importFormatVersion": 2,
    }


def _digest(value: object, loc: str) -> str:
    result = _text(value, loc)
    _need(re.fullmatch(r"[0-9a-f]{64}", result) is not None, loc, "hash", "expected SHA256")
    return result


def parse_native_manifest(value: object, *, budget: Union[ValidationBudget, None] = None) -> NativeManifest:
    check_budget(budget)
    data = _object(value, "manifest")
    _need(data.get("format") == NATIVE_FORMAT, "format", "format", "unsupported native format")
    version = _integer(data.get("schemaVersion"), "schemaVersion", minimum=1)
    _need(
        version == NATIVE_MANIFEST_VERSION,
        "schemaVersion",
        "version",
        "unsupported native manifest",
    )
    _need(data.get("status") == "complete", "status", "building", "complete native dataset required")
    source = _text(data.get("sourceFile"), "sourceFile")
    identity = _object(data.get("identity"), "identity")
    _digest(identity.get("sourceSha256"), "identity.sourceSha256")
    requested = identity.get("requestedDevice")
    if requested is not None:
        _integer(requested, "identity.requestedDevice", maximum=2**31 - 1)
    capacity = _integer(identity.get("eventsPerSlice"), "identity.eventsPerSlice", minimum=1)
    _need(
        identity.get("outputFormat") == NATIVE_FORMAT,
        "identity",
        "format",
        "format identity mismatch",
    )
    for key in (
        "manifestContractVersion",
        "formatContractVersion",
        "importContractVersion",
        "extensionContractVersion",
        "metadataSchemaVersion",
        "importFormatVersion",
    ):
        _integer(identity.get(key), "identity." + key, minimum=1)
    _need(
        set(identity) == set(cache_identity("", None, 1)),
        "identity",
        "fields",
        "identity fields differ",
    )
    try:
        metadata = metadata_from_mapping(_object(data.get("metadata"), "metadata"))
    except (KeyError, TypeError, ValueError) as exc:
        raise DatasetContractError("metadata", "metadata", str(exc)) from exc
    _need(
        (
            metadata.source_sha256,
            metadata.requested_device,
            metadata.metadata_schema_version,
            metadata.import_format_version,
        )
        == (
            identity["sourceSha256"],
            requested,
            identity["metadataSchemaVersion"],
            identity["importFormatVersion"],
        ),
        "metadata",
        "identity",
        "metadata disagrees with dataset identity",
    )
    _need(
        source == metadata.source_name,
        "sourceFile",
        "metadata",
        "source name disagrees with metadata",
    )
    omitted = tuple(
        _integer(v, "omittedDevices", maximum=2**31 - 1)
        for v in checked_rows(_array(data.get("omittedDevices"), "omittedDevices"), budget)
    )
    _need(len(set(omitted)) == len(omitted), "omittedDevices", "duplicate", "duplicate device")
    devices: List[DeviceRecord] = []
    for key, raw in checked_rows(_object(data.get("devices"), "devices").items(), budget):
        loc = f"devices.{key}"
        _need(
            isinstance(key, str) and re.fullmatch(r"0|[1-9][0-9]*", key) is not None,
            loc,
            "device",
            "noncanonical device",
        )
        device_id = _integer(int(key), loc, maximum=2**31 - 1)
        device = _object(raw, loc)
        count = _integer(device.get("eventCount"), loc + ".eventCount", minimum=1)
        records = _array(device.get("slices"), loc + ".slices")
        _need(
            # pylint: disable-next=unidiomatic-typecheck  # Reject bool/subclasses: the contract requires exact scalar types.
            bool(records) and device.get("sliceCount") == len(records) and type(device.get("sliceCount")) is int,
            loc,
            "count",
            "invalid sliceCount",
        )
        ready = tuple(
            _integer(v, loc + ".readySlices")
            for v in checked_rows(_array(device.get("readySlices"), loc + ".readySlices"), budget)
        )
        _need(
            ready == tuple(range(len(records))),
            loc,
            "readiness",
            "all slices must be ready in order",
        )
        slices: List[SliceRecord] = []
        position, last_id = 0, -1
        for index, raw_slice in enumerate(checked_rows(records, budget)):
            item = _object(raw_slice, loc)
            _need(
                # pylint: disable-next=unidiomatic-typecheck  # Reject bool/subclasses: the contract requires exact scalar types.
                type(item.get("index")) is int and item["index"] == index and item.get("ready") is True,
                loc,
                "index",
                "slice index/readiness mismatch",
            )
            start = _integer(item.get("startPosition"), loc + ".startPosition")
            end = _integer(item.get("endPosition"), loc + ".endPosition", minimum=start)
            _need(
                start == position and end - start + 1 <= capacity,
                loc,
                "coverage",
                "invalid positional coverage/capacity",
            )
            # All but the last shard must be full; no omitted positions are allowed.
            _need(
                index == len(records) - 1 or end - start + 1 == capacity,
                loc,
                "capacity",
                "nonfinal slice is not full",
            )
            low = _integer(item.get("startEventId"), loc + ".startEventId", minimum=last_id + 1)
            high = _integer(item.get("endEventId"), loc + ".endEventId", minimum=low)
            file = _text(item.get("file"), loc + ".file")
            _need(
                file == f"device_{device_id}/slice_{index:05d}.db",
                loc,
                "path",
                "noncanonical member",
            )
            slices.append(NativeSlice(index, low, high, file, True, start, end, _digest(item.get("sha256"), loc)))
            position, last_id = end + 1, high
        _need(position == count, loc, "coverage", "positions do not cover eventCount")
        devices.append(DeviceRecord(device_id, count, ready, tuple(slices)))
    _need(bool(devices), "devices", "empty", "event-bearing device required")
    selected = {d.device_id for d in devices}
    _need(not selected.intersection(omitted), "omittedDevices", "device", "selected device is omitted")
    _need(
        requested is None or selected == {requested},
        "identity",
        "device",
        "requested device mismatch",
    )
    return NativeManifest(version, "complete", source, "", capacity, tuple(devices), identity, metadata, omitted)


def read_native_manifest(root: Path) -> NativeManifest:
    try:
        with _safe_file(root, "manifest.json").open(encoding="utf-8") as file:
            return parse_native_manifest(json.load(file, object_pairs_hook=_unique_object))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise DatasetContractError("manifest.json", "read", str(exc)) from exc


def require_native_members(
    root: Path, manifest: NativeManifest, *, budget: Union[ValidationBudget, None] = None
) -> None:
    """Ownership recognition before any replacement: never adopt unknown files/dirs."""
    _need(
        root.resolve() == root and not root.is_symlink(),
        "dataset",
        "path",
        "noncanonical directory",
    )
    expected = {"manifest.json", *(f"device_{d.device_id}" for d in manifest.devices)}
    _need(
        {p.name for p in checked_rows(root.iterdir(), budget)} == expected,
        "dataset",
        "members",
        "unexpected/missing dataset member",
    )
    for device in manifest.devices:
        directory = root / f"device_{device.device_id}"
        _need(
            not directory.is_symlink() and directory.is_dir(),
            str(directory),
            "path",
            "unsafe device directory",
        )
        _need(
            {p.name for p in checked_rows(directory.iterdir(), budget)} == {Path(s.file).name for s in device.slices},
            str(directory),
            "members",
            "unexpected/missing shard",
        )
        for item in checked_rows(device.slices, budget):
            _safe_file(root, item.file)


def validate_native_dataset(
    root: Path, manifest: NativeManifest, *, budget: Union[ValidationBudget, None] = None
) -> DatasetValidation:
    check_budget(budget)
    require_native_members(root, manifest, budget=budget)
    expected_identity = cache_identity(
        manifest.metadata.source_sha256,
        manifest.metadata.requested_device,
        manifest.events_per_slice,
    )
    # Read old text-only artifacts; import reuse still requires the current
    # identity in ImportService. Optional frame support is declared separately.
    extension = manifest.identity.get("extensionContractVersion")
    if extension in (1, NATIVE_EXTENSION_VERSION):
        expected_identity["extensionContractVersion"] = extension
    _need(
        manifest.identity == expected_identity,
        "identity",
        "version",
        "unsupported native semantic contract",
    )
    # Check EVERY member before the FIRST SQLite open. No WAL/sidecars/repair.
    for device in manifest.devices:
        for raw in checked_rows(device.slices, budget):
            item = cast(NativeSlice, raw)
            path = root / item.file
            _require_readonly_member(root, path)
            _need(
                _hash_file(path, budget=budget) == item.sha256,
                item.file,
                "hash",
                "member content changed",
            )
    boundaries = 0
    for device in manifest.devices:
        ids: Set[int] = set()
        lifetimes: Dict[int, Tuple[object, ...]] = {}
        for raw in checked_rows(device.slices, budget):
            item = cast(NativeSlice, raw)
            path = root / item.file
            try:
                conn = sqlite3.connect(path.as_uri() + '?mode=ro', uri=True, timeout=sqlite_timeout(budget))
                with closing(conn), validation_progress(conn, budget):
                    conn.execute("PRAGMA query_only=ON")
                    _need(
                        conn.execute("PRAGMA quick_check").fetchall() == [("ok",)],
                        item.file,
                        "sqlite",
                        "integrity check failed",
                    )
                    trace, block = f"trace_entry_{device.device_id}", f"block_{device.device_id}"
                    names = {
                        row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type IN ('table','view')")
                    }
                    _need(
                        {n for n in names if n.lower().startswith(("trace_entry_", "block_"))} == {trace, block},
                        item.file,
                        "device_tables",
                        "wrong device/table set",
                    )
                    for table, columns in (
                        (trace, TRACE_COLUMNS[:-1] + (("callstackId", "INTEGER"),)),
                        (block, BLOCK_COLUMNS),
                        ("dictionary", DICTIONARY_COLUMNS),
                        ("callstack", (("id", "INTEGER"), ("callstack", "TEXT"))),
                    ):
                        _schema(conn, table, columns, item.file)
                    _need(
                        conn.execute("SELECT type FROM sqlite_master WHERE name='pt_snap_block_reference'").fetchone()
                        == ("table",),
                        item.file,
                        "extension",
                        "finalized reference table required",
                    )
                    reference_columns = conn.execute("PRAGMA table_info(pt_snap_block_reference)").fetchall()
                    _need(
                        tuple((r[1], r[2].upper(), r[5]) for r in reference_columns)
                        == (
                            ("blockId", "INTEGER", 1),
                            ("stream", "INTEGER", 0),
                            ("allocCallstack", "TEXT", 0),
                            ("freeCallstack", "TEXT", 0),
                        ),
                        item.file,
                        "extension",
                        "invalid reference schema",
                    )
                    for table, column, values in (
                        (trace, "action", tuple(enumerate((*ACTION_NAMES, "oom")))),
                        (block, "state", BLOCK_STATES),
                    ):
                        rows = conn.execute(
                            'SELECT "key","value" FROM dictionary WHERE "table"=? AND "column"=?',
                            (table, column),
                        ).fetchall()
                        expected = {(str(k), v) for k, v in values}
                        _need(
                            len(rows) == len(expected) and set(rows) == expected,
                            item.file,
                            "dictionary",
                            "invalid native dictionary",
                        )
                    count, low, high = conn.execute(
                        f'SELECT COUNT(*), MIN(id), MAX(id) FROM "{trace}" WHERE id>=0'  # nosec B608 # SQL structure uses validated integer IDs and fixed/allowlisted schema fragments; values are bound.
                    ).fetchone()
                    _need(
                        (count, low, high)
                        == (
                            item.end_position - item.start_position + 1,
                            item.start_event_id,
                            item.end_event_id,
                        ),
                        item.file,
                        "event_identity",
                        "real IDs/count differ from positions/ranges",
                    )
                    # Manifest intervals are disjoint; avoid a per-shard list
                    # and intersection copy in addition to the device ID set.
                    ids.update(
                        r[0]
                        for r in checked_rows(conn.execute(f'SELECT id FROM "{trace}" WHERE id>=0'), budget)  # nosec B608 # SQL structure uses validated integer IDs and fixed/allowlisted schema fragments; values are bound.
                    )
                    numeric = " OR ".join(f"typeof({name})!='integer'" for name, _ in TRACE_COLUMNS[:-1])
                    invalid = conn.execute(
                        f"SELECT id FROM \"{trace}\" WHERE {numeric} OR action NOT BETWEEN 0 AND 8 OR (id<0 AND action NOT IN (0,2)) OR size<0 OR allocated<0 OR active<0 OR reserved<0 OR typeof(callstackId)!='integer' OR callstackId NOT IN (SELECT id FROM callstack) LIMIT 1"  # nosec B608 # SQL structure uses validated integer IDs and fixed/allowlisted schema fragments; values are bound.
                    ).fetchone()
                    _need(
                        invalid is None,
                        item.file,
                        "event_values",
                        "invalid native event/scalar/callstack",
                    )
                    _need(
                        conn.execute(
                            "SELECT id FROM callstack WHERE typeof(callstack) NOT IN ('text','null') LIMIT 1"
                        ).fetchone()
                        is None,
                        item.file,
                        "callstack",
                        "invalid text stack",
                    )
                    boundaries += conn.execute(f'SELECT COUNT(*) FROM "{trace}" WHERE id<0').fetchone()[0]  # nosec B608 # SQL structure uses validated integer IDs and fixed/allowlisted schema fragments; values are bound.
                    mismatch = conn.execute(
                        f'SELECT b.id FROM "{block}" b WHERE NOT EXISTS '
                        "(SELECT 1 FROM pt_snap_block_reference r WHERE r.blockId=b.id) "
                        "UNION ALL SELECT r.blockId FROM pt_snap_block_reference r "
                        f'WHERE NOT EXISTS (SELECT 1 FROM "{block}" b WHERE b.id=r.blockId) '
                        "LIMIT 1"  # nosec B608 # SQL structure uses validated integer IDs and fixed/allowlisted schema fragments; values are bound.
                    ).fetchone()
                    _need(
                        mismatch is None,
                        item.file,
                        "extension",
                        "reference/block membership differs",
                    )
                    rows = conn.execute(
                        f"SELECT b.*, r.stream, r.allocCallstack, r.freeCallstack "
                        f'FROM "{block}" b JOIN pt_snap_block_reference r ON r.blockId=b.id'  # nosec B608 # SQL structure uses validated integer IDs and fixed/allowlisted schema fragments; values are bound.
                    )
                    for joined in checked_rows(rows, budget):
                        row, ref = joined[:7], joined[7:]
                        bid, address, size, requested, state, alloc, free = row
                        _need(
                            # pylint: disable-next=unidiomatic-typecheck  # Reject bool/subclasses: the contract requires exact scalar types.
                            all(type(v) is int for v in row)
                            and state in (-1, 0, 1)
                            and size >= 0
                            and 0 <= requested <= size
                            and ((alloc == -1 and bid < 0) or (alloc >= 0 and bid == alloc))
                            and (free == -1 or free >= 0 and (alloc == -1 or free >= alloc)),
                            item.file,
                            "block_identity",
                            "unfinalized/invalid block",
                        )
                        _need(
                            # pylint: disable-next=unidiomatic-typecheck  # Reject bool/subclasses: the contract requires exact scalar types.
                            type(ref[0]) is int and all(v is None or isinstance(v, str) for v in ref[1:]),
                            item.file,
                            "extension",
                            "invalid reference values",
                        )
                        signature = (address, size, requested, alloc, free, *ref)
                        _need(
                            bid not in lifetimes or lifetimes[bid] == signature,
                            item.file,
                            "block_identity",
                            "conflicting finalized identity/reference",
                        )
                        lifetimes[bid] = signature
            except sqlite3.DatabaseError as exc:
                raise DatasetContractError(item.file, "sqlite", str(exc)) from exc
            try:
                metadata_conn = sqlite3.connect(path.as_uri() + '?mode=ro', uri=True, timeout=sqlite_timeout(budget))
                with closing(metadata_conn), validation_progress(metadata_conn, budget):
                    metadata_conn.row_factory = sqlite3.Row
                    _need(
                        metadata_conn.execute(
                            "SELECT type FROM sqlite_master WHERE name='pt_snap_metadata'"
                        ).fetchone()[0]
                        == "table",
                        item.file,
                        "metadata",
                        "metadata must be an actual table",
                    )
                    rows = metadata_conn.execute("SELECT * FROM pt_snap_metadata").fetchall()
                    _need(
                        len(rows) == 1
                        and rows[0]["id"] == 1
                        and set(rows[0].keys()) == {"id", *asdict(manifest.metadata)},
                        item.file,
                        "metadata",
                        "invalid metadata row/schema",
                    )
                    metadata = metadata_from_mapping(dict(rows[0]))
                    _need(
                        metadata == manifest.metadata,
                        item.file,
                        "metadata",
                        "member metadata differs from manifest",
                    )
            except (sqlite3.DatabaseError, KeyError, TypeError, ValueError) as exc:
                raise DatasetContractError(item.file, "metadata", str(exc)) from exc
            _require_readonly_member(root, path)
            _need(
                _hash_file(path, budget=budget) == item.sha256,
                item.file,
                "hash",
                "member changed during validation",
            )
        _need(
            len(ids) == device.event_count
            and all(
                v == -1 or v in ids for lifetime in checked_rows(lifetimes.values(), budget) for v in lifetime[3:5]
            ),
            "devices",
            "event_identity",
            "count/lifetime references not in original device scope",
        )
    return DatasetValidation(manifest, sum(d.event_count for d in manifest.devices), boundaries)


def validate_native_scope(scope: QueryScope, manifest: NativeManifest) -> None:
    if scope.kind == "event_range":
        device = next((d for d in manifest.devices if d.device_id == scope.device_id), None)
        # pylint: disable-next=unidiomatic-typecheck  # Reject bool/subclasses: the contract requires exact scalar types.
        _need(type(scope.device_id) is int and device is not None, "scope", "device", "unknown device")
        assert device is not None  # nosec B101 # Internal invariant after validation; not an input security check.
        _need(scope.slice_index is None, "scope", "selector", "unexpected slice selector")
        start = _integer(
            scope.start_event_id,
            "scope.start_event_id",
            minimum=device.slices[0].start_event_id,
            maximum=device.slices[-1].end_event_id,
        )
        _integer(
            scope.end_event_id,
            "scope.end_event_id",
            minimum=start,
            maximum=device.slices[-1].end_event_id,
        )
    else:
        scope.validate(manifest)


def build_native_manifest(result: ShardedReplayResult, metadata: ImportMetadata, capacity: int) -> Dict[str, object]:
    devices: Dict[str, object] = {}
    for device in sorted({item.device for item in result.slices}):
        slices = [s for s in result.slices if s.device == device]
        devices[str(device)] = {
            "eventCount": sum(s.end_position - s.start_position + 1 for s in slices),
            "sliceCount": len(slices),
            "readySlices": list(range(len(slices))),
            "slices": [
                {
                    "index": s.index,
                    "startPosition": s.start_position,
                    "endPosition": s.end_position,
                    "startEventId": s.start_event_id,
                    "endEventId": s.end_event_id,
                    "file": s.file.relative_to(result.directory).as_posix(),
                    "ready": True,
                    "sha256": _hash_file(s.file),
                }
                for s in slices
            ],
        }
    return {
        "format": NATIVE_FORMAT,
        "schemaVersion": NATIVE_MANIFEST_VERSION,
        "status": "complete",
        "sourceFile": metadata.source_name,
        "identity": cache_identity(metadata.source_sha256, metadata.requested_device, capacity),
        "metadata": asdict(metadata),
        "omittedDevices": list(result.omitted_devices),
        "extensions": {"ptSnapOrderedFrames": {"version": 2}},
        "devices": devices,
    }
