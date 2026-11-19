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

"""P0 sharded SnapshotDB contract, independent of import/query execution.

Original pt-snap implementation of the documented interoperability facts at
Ascend/msinsight revision 101f65b877a267ffd5f66ea3834706057ba243e5.
No upstream implementation is copied.
"""

from __future__ import annotations

import json
import re
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Tuple, Union, cast

from typing_extensions import Literal

from pt_snap_cli._compat import zip_strict
from pt_snap_cli.core.common.errors import DatabaseSchemaError
from pt_snap_cli.core.common.validation_budget import (
    ValidationBudget,
    check_budget,
    checked_rows,
    sqlite_timeout,
    validation_progress,
)
from pt_snap_cli.core.dataset.dataset_files import readonly_member_uri, require_readonly_member

MANIFEST_SCHEMA_VERSION = 1
MSINSIGHT_REVISION = "101f65b877a267ffd5f66ea3834706057ba243e5"
ACTION_NAMES = (
    "segment_map",
    "segment_unmap",
    "segment_alloc",
    "segment_free",
    "alloc",
    "free_requested",
    "free_completed",
    "workspace_snapshot",
)
BLOCK_STATES = ((-1, "inactive"), (0, "active_pending_free"), (1, "active_allocated"))
TRACE_COLUMNS = tuple(
    (name, "INTEGER") for name in ("id", "action", "address", "size", "stream", "allocated", "active", "reserved")
) + (("callstack", "TEXT"),)
BLOCK_COLUMNS = tuple(
    (name, "INTEGER") for name in ("id", "address", "size", "requestedSize", "state", "allocEventId", "freeEventId")
)
DICTIONARY_COLUMNS = tuple((name, "TEXT") for name in ("table", "column", "key", "value"))


class DatasetContractError(ValueError):
    """A validation failure with a stable code and manifest/file location."""

    def __init__(self, location: str, code: str, detail: str):
        self.location = location
        self.code = code
        super().__init__(f"{location}: {code}: {detail}")


def _need(condition: bool, location: str, code: str, detail: str) -> None:
    if not condition:
        raise DatasetContractError(location, code, detail)


def _object(value: object, location: str) -> Dict[str, object]:
    _need(isinstance(value, dict), location, "type", "expected object")
    return cast(Dict[str, object], value)


def _array(value: object, location: str) -> List[object]:
    _need(isinstance(value, list), location, "type", "expected array")
    return cast(List[object], value)


def _integer(value: object, location: str, minimum: int = 0, maximum: int = 2**63 - 1) -> int:
    # pylint: disable-next=unidiomatic-typecheck  # Reject bool/subclasses: the contract requires exact scalar types.
    _need(type(value) is int, location, "type", "expected integer (not boolean)")
    number = cast(int, value)
    _need(minimum <= number <= maximum, location, "range", "integer out of range")
    return number


def _text(value: object, location: str, *, empty: bool = False) -> str:
    _need(isinstance(value, str), location, "type", "expected string")
    text = cast(str, value)
    _need(empty or bool(text), location, "range", "string must not be empty")
    return text


@dataclass(frozen=True)
class SliceRecord:
    index: int
    start_event_id: int
    end_event_id: int
    file: str
    ready: bool


@dataclass(frozen=True)
class DeviceRecord:
    device_id: int
    event_count: int
    ready_slices: Tuple[int, ...]
    slices: Tuple[SliceRecord, ...]


@dataclass(frozen=True)
class DatasetManifest:
    schema_version: int
    status: str
    source_file: str
    cache_hash: str
    events_per_slice: int
    devices: Tuple[DeviceRecord, ...]

    def require_complete(self) -> None:
        _need(self.status == "complete", "status", "building", "complete dataset required")
        for device in self.devices:
            _need(
                all(item.ready for item in device.slices),
                f"devices.{device.device_id}.readySlices",
                "not_ready",
                "complete requires every slice ready after finalization",
            )


def parse_manifest(
    value: object, *, require_complete: bool = True, budget: Union[ValidationBudget, None] = None
) -> DatasetManifest:
    """Validate JSON-shaped data; inspection may explicitly accept building.

    Unknown extension declarations are ignored, never promoted to capabilities.
    This does not check files; use validate_dataset for finalized artifacts.
    """
    check_budget(budget)
    data = _object(value, "manifest")
    version = _integer(data.get("schemaVersion"), "schemaVersion", maximum=2**31 - 1)
    _need(version == MANIFEST_SCHEMA_VERSION, "schemaVersion", "version", "unsupported base version")
    status = _text(data.get("status"), "status")
    _need(status in ("building", "complete"), "status", "status", "unknown publication state")
    source = _text(data.get("sourceFile"), "sourceFile")
    cache_hash = _text(data.get("cacheHash"), "cacheHash", empty=True)
    capacity = _integer(data.get("eventsPerSlice"), "eventsPerSlice", minimum=1)
    devices_data = _object(data.get("devices"), "devices")
    _need(bool(devices_data), "devices", "empty", "at least one event-bearing device required")
    devices: List[DeviceRecord] = []
    for key, device_value in checked_rows(devices_data.items(), budget):
        location = f"devices.{key}"
        _need(
            isinstance(key, str) and re.fullmatch(r"0|[1-9][0-9]*", key) is not None,
            location,
            "device",
            "expected canonical nonnegative device ID",
        )
        device_id = _integer(int(key), location, maximum=2**31 - 1)
        device = _object(device_value, location)
        count = _integer(device.get("eventCount"), location + ".eventCount", minimum=1)
        size = _integer(device.get("sliceCount"), location + ".sliceCount", minimum=1, maximum=2**31 - 1)
        ready = tuple(
            _integer(item, location + ".readySlices", maximum=size - 1)
            for item in checked_rows(_array(device.get("readySlices"), location + ".readySlices"), budget)
        )
        _need(
            len(set(ready)) == len(ready),
            location + ".readySlices",
            "duplicate",
            "duplicate ready index",
        )
        records = _array(device.get("slices"), location + ".slices")
        _need(
            len(records) == size,
            location + ".sliceCount",
            "count",
            "sliceCount differs from slices",
        )
        slices: List[SliceRecord] = []
        expected_start = 0
        for index, raw in enumerate(checked_rows(records, budget)):
            loc = f"{location}.slices[{index}]"
            item = _object(raw, loc)
            number = _integer(item.get("index"), loc + ".index", maximum=2**31 - 1)
            _need(number == index, loc + ".index", "index", "indices must match array order")
            start = _integer(item.get("startEventId"), loc + ".startEventId")
            end = _integer(item.get("endEventId"), loc + ".endEventId", minimum=start)
            _need(start == expected_start, loc, "coverage", "ranges must cover continuously from zero")
            _need(end - start + 1 <= capacity, loc, "capacity", "slice exceeds eventsPerSlice")
            file = _text(item.get("file"), loc + ".file")
            _need(
                not any(part in ("", ".", "..") for part in file.split("/"))
                and not any(char in file for char in ("\\", ":", "\0")),
                loc + ".file",
                "path",
                "unsafe relative path",
            )
            _need(
                file == f"device_{device_id}/slice_{index:05d}.db",
                loc + ".file",
                "path",
                "file must match device and slice index",
            )
            is_ready = item.get("ready")
            # pylint: disable-next=unidiomatic-typecheck  # Reject bool/subclasses: the contract requires exact scalar types.
            _need(type(is_ready) is bool, loc + ".ready", "type", "expected boolean")
            _need(
                is_ready == (index in ready),
                loc + ".ready",
                "readiness",
                "ready disagrees with readySlices",
            )
            slices.append(SliceRecord(index, start, end, file, cast(bool, is_ready)))
            expected_start = end + 1
        _need(
            expected_start == count,
            location + ".eventCount",
            "coverage",
            "ranges do not cover eventCount",
        )
        devices.append(DeviceRecord(device_id, count, ready, tuple(slices)))
    manifest = DatasetManifest(version, status, source, cache_hash, capacity, tuple(devices))
    # Even inspection must reject a contradictory complete publication.
    if require_complete or status == "complete":
        manifest.require_complete()
    return manifest


def validate_event_ids(event_ids: Iterable[int]) -> int:
    """Producer precondition: actual real-event positions, not max(id)+1.

    Boundary rows are a separate input category. No renumbering is performed.
    """
    count = 0
    for position, value in enumerate(event_ids):
        number = _integer(value, f"events[{position}]")
        _need(
            number == position,
            f"events[{position}]",
            "event_identity",
            "compatibility requires original real IDs 0..N-1; do not silently renumber",
        )
        count += 1
    _need(count > 0, "events", "empty", "empty/static-only devices cannot use compatibility v1")
    return count


@dataclass(frozen=True)
class QueryScope:
    """Selector contract only; not a cross-slice query executor."""

    kind: Literal["dataset", "device", "slice", "event_range"]
    device_id: Union[int, None] = None
    slice_index: Union[int, None] = None
    start_event_id: Union[int, None] = None
    end_event_id: Union[int, None] = None

    def validate(self, manifest: DatasetManifest) -> None:
        manifest.require_complete()
        loc = "scope"
        _need(self.kind in ("dataset", "device", "slice", "event_range"), loc, "kind", "unknown scope")
        if self.kind == "dataset":
            _need(
                all(
                    value is None
                    for value in (
                        self.device_id,
                        self.slice_index,
                        self.start_event_id,
                        self.end_event_id,
                    )
                ),
                loc,
                "selector",
                "dataset has no selectors",
            )
            return
        device_id = _integer(self.device_id, loc + ".device_id", maximum=2**31 - 1)
        device = next((item for item in manifest.devices if item.device_id == device_id), None)
        _need(device is not None, loc, "device", "unknown device")
        assert device is not None  # nosec B101 # Internal invariant after validation; not an input security check.
        if self.kind == "slice":
            _integer(self.slice_index, loc + ".slice_index", maximum=len(device.slices) - 1)
        else:
            _need(self.slice_index is None, loc, "selector", "slice index only valid for slice scope")
        if self.kind == "event_range":
            start = _integer(self.start_event_id, loc + ".start_event_id", maximum=device.event_count - 1)
            _integer(
                self.end_event_id,
                loc + ".end_event_id",
                minimum=start,
                maximum=device.event_count - 1,
            )
        else:
            _need(
                self.start_event_id is None and self.end_event_id is None,
                loc,
                "selector",
                "unexpected range",
            )


@dataclass(frozen=True)
class DatasetValidation:
    manifest: DatasetManifest
    real_event_count: int
    boundary_event_count: int
    text_callstacks: bool = True
    structured_frames: bool = False
    query_execution: bool = False


def _unique_object(pairs: List[Tuple[str, object]]) -> Dict[str, object]:
    result: Dict[str, object] = {}
    for key, value in pairs:
        _need(key not in result, "manifest." + key, "duplicate", "duplicate JSON member")
        result[key] = value
    return result


def _safe_file(root: Path, relative: str) -> Path:
    path = root / relative
    for part in (
        root,
        *[root.joinpath(*Path(relative).parts[:i]) for i in range(1, len(Path(relative).parts) + 1)],
    ):
        _need(not part.is_symlink(), relative, "path", "symlink is not an artifact member")
    _need(path.is_file(), relative, "missing", "artifact file missing")
    return path


def _schema(
    conn: sqlite3.Connection,
    table: str,
    columns: Tuple[Tuple[str, str], ...],
    loc: str,
    *,
    allow_extra_columns: bool = False,
) -> None:
    kind = conn.execute("SELECT type FROM sqlite_master WHERE name=?", (table,)).fetchone()
    _need(kind == ("table",), loc, "table", f"{table} must be an actual table, not a view")
    rows = conn.execute(f'PRAGMA table_info("{table}")').fetchall()
    _need(
        tuple((row[1], row[2].upper()) for row in rows[: len(columns)]) == columns
        and (allow_extra_columns or len(rows) == len(columns)),
        loc,
        "columns",
        f"{table} column order/types differ from base contract",
    )
    if table != "dictionary":
        _need(
            tuple(row[5] for row in rows) == (1,) + (0,) * (len(rows) - 1),
            loc,
            "primary_key",
            f"{table}.id must be the sole primary key",
        )


def _validate_slice(
    conn: sqlite3.Connection,
    device: DeviceRecord,
    item: SliceRecord,
    identities: Dict[Tuple[int, int], Tuple[object, ...]],
    budget: Union[ValidationBudget, None] = None,
) -> int:
    loc = item.file
    trace, block = f"trace_entry_{device.device_id}", f"block_{device.device_id}"
    tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type IN ('table','view')")}
    relevant = {name for name in tables if name.lower().startswith(("trace_entry_", "block_"))}
    _need(relevant == {trace, block}, loc, "device_tables", "device/table set mismatch")
    _need(
        "callstack" not in {name.lower() for name in tables},
        loc,
        "layout",
        "v1 must not contain native v2 callstack table",
    )
    for table, columns in (
        (trace, TRACE_COLUMNS),
        (block, BLOCK_COLUMNS),
        ("dictionary", DICTIONARY_COLUMNS),
    ):
        _schema(conn, table, columns, loc, allow_extra_columns=True)
    for table, column, values in (
        (trace, "action", tuple(enumerate(ACTION_NAMES))),
        (block, "state", BLOCK_STATES),
    ):
        rows = conn.execute(
            'SELECT "key", "value" FROM dictionary WHERE "table"=? AND "column"=?', (table, column)
        ).fetchall()
        expected = {(str(key), name) for key, name in values}
        _need(
            len(rows) == len(expected) and set(rows) == expected,
            loc,
            "dictionary",
            f"invalid {table}.{column} mapping",
        )
    count, low, high = conn.execute(f'SELECT COUNT(*), MIN(id), MAX(id) FROM "{trace}" WHERE id>=0').fetchone()  # nosec B608 # SQL structure uses validated integer IDs and fixed/allowlisted schema fragments; values are bound.
    _need(
        (count, low, high) == (item.end_event_id - item.start_event_id + 1, item.start_event_id, item.end_event_id),
        loc,
        "event_identity",
        "real rows differ from declared contiguous interval",
    )
    bad = conn.execute(
        f'SELECT id FROM "{trace}" WHERE action NOT BETWEEN 0 AND 7 OR action IS NULL '
        "OR typeof(action) != 'integer' OR (id<0 AND action NOT IN (0,2)) LIMIT 1"  # nosec B608 # SQL structure uses validated integer IDs and fixed/allowlisted schema fragments; values are bound.
    ).fetchone()
    _need(bad is None, loc, "event_action", "unknown action or invalid boundary event")
    invalid_types = " OR ".join(f"typeof({name}) != 'integer'" for name, _ in TRACE_COLUMNS[:-1])
    bad = conn.execute(
        f'SELECT id FROM "{trace}" WHERE {invalid_types} '
        "OR size<0 OR allocated<0 OR active<0 OR reserved<0 "
        "OR typeof(callstack) NOT IN ('text','null') LIMIT 1"  # nosec B608 # SQL structure uses validated integer IDs and fixed/allowlisted schema fragments; values are bound.
    ).fetchone()
    _need(bad is None, loc, "event_values", "invalid scalar type or negative byte metric")
    boundary_count = conn.execute(f'SELECT COUNT(*) FROM "{trace}" WHERE id<0').fetchone()[0]  # nosec B608 # SQL structure uses validated integer IDs and fixed/allowlisted schema fragments; values are bound.
    selected = ",".join(f'"{name}"' for name, _ in BLOCK_COLUMNS)
    for row in checked_rows(conn.execute(f'SELECT {selected} FROM "{block}"'), budget):  # nosec B608 # SQL structure uses validated integer IDs and fixed/allowlisted schema fragments; values are bound.
        block_id, address, size, requested, state, alloc, free = row
        for name, value in zip_strict(
            ("id", "address", "size", "requestedSize", "state", "allocEventId", "freeEventId"),
            row,
        ):
            _integer(value, f"{loc}.{block}.{block_id}.{name}", minimum=-(2**63))
        _need(
            state in (-1, 0, 1) and size >= 0 and 0 <= requested <= size,
            loc,
            "block",
            "invalid state/size",
        )
        _need(
            (alloc == -1 and block_id < 0) or (0 <= alloc < device.event_count and block_id == alloc),
            loc,
            "block_identity",
            "resolved ID must equal allocation; unresolved ID must be negative",
        )
        _need(
            free == -1 or (0 <= free < device.event_count and (alloc == -1 or free >= alloc)),
            loc,
            "lifecycle",
            "invalid free sentinel or lifecycle order",
        )
        identity = (device.device_id, block_id)
        # State describes the slice observation and may differ; identity/lifetime do not.
        signature = (address, size, requested, alloc, free)
        _need(
            identity not in identities or identities[identity] == signature,
            loc,
            "block_identity",
            "same cross-slice ID has conflicting identity/lifetime",
        )
        identities[identity] = signature
    return cast(int, boundary_count)


def validate_dataset(directory: Union[Path, str], *, budget: Union[ValidationBudget, None] = None) -> DatasetValidation:
    """Read a complete compatibility-v1 dataset without migration or pickle.

    Checks are validation, not a filesystem sandbox or concurrent publication lock.
    Missing pt_snap_metadata/extension tables are valid external base artifacts.
    """
    check_budget(budget)
    root = Path(directory).absolute()
    _need(
        root.resolve() == root and not root.is_symlink(),
        "dataset",
        "path",
        "canonical non-symlink directory required",
    )
    try:
        path = _safe_file(root, "manifest.json")
        with path.open(encoding="utf-8") as source:
            data: object = json.load(source, object_pairs_hook=_unique_object)
        manifest = parse_manifest(data, budget=budget)
        # Preflight ALL members before the first SQLite open, also for callers
        # using this bare P0 validator rather than DatasetResolver.
        for device in manifest.devices:
            for item in checked_rows(device.slices, budget):
                member = _safe_file(root, item.file)
                try:
                    require_readonly_member(root, member, immutable=True)
                except DatabaseSchemaError as exc:
                    raise DatasetContractError(item.file, "transport", str(exc)) from exc
        identities: Dict[Tuple[int, int], Tuple[object, ...]] = {}
        boundaries = 0
        for device in manifest.devices:
            for item in checked_rows(device.slices, budget):
                db_path = _safe_file(root, item.file)
                try:
                    conn = sqlite3.connect(readonly_member_uri(db_path), uri=True, timeout=sqlite_timeout(budget))
                    with closing(conn), validation_progress(conn, budget):
                        conn.execute("PRAGMA query_only=ON")
                        conn.execute("BEGIN")
                        _need(
                            conn.execute("PRAGMA quick_check").fetchall() == [("ok",)],
                            item.file,
                            "integrity",
                            "SQLite member failed integrity check",
                        )
                        boundaries += _validate_slice(conn, device, item, identities, budget)
                except sqlite3.DatabaseError as exc:
                    raise DatasetContractError(item.file, "sqlite", str(exc)) from exc
        return DatasetValidation(manifest, sum(item.event_count for item in manifest.devices), boundaries)
    except RecursionError as exc:
        raise DatasetContractError("manifest.json", "read", "manifest nesting is too deep") from exc
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise DatasetContractError("manifest.json", "read", str(exc)) from exc
