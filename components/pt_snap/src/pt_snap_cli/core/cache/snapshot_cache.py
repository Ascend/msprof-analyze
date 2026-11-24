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

"""Portable msinsight cache contract; consumer-owned tables are not parser data."""

from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Any, Dict, List, Tuple, Union

from pt_snap_cli.core.common.validation_budget import (
    ValidationBudget,
    check_budget,
    sqlite_timeout,
    validation_progress,
)

PARSER_HASH_SALT = b"mem_snapshot_parser_v3"
CACHE_CONTRACT_VERSION = 1
TRACE_COLUMNS = (
    "id",
    "action",
    "address",
    "size",
    "stream",
    "allocated",
    "active",
    "reserved",
    "callstack",
)
BLOCK_COLUMNS = ("id", "address", "size", "requestedSize", "state", "allocEventId", "freeEventId")


def source_hashes(source: Path) -> Tuple[str, str]:
    """Return raw and salted SHA-256 in one streaming pass, without unpickling."""
    raw = hashlib.sha256()
    salted = hashlib.sha256(PARSER_HASH_SALT)
    with source.open("rb") as file:
        before = os.fstat(file.fileno())
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            raw.update(chunk)
            salted.update(chunk)
        after = os.fstat(file.fileno())
    current = source.stat()

    def signature(stat: os.stat_result) -> Tuple[int, int, int, int]:
        # Windows fstat/stat disagree on ctime for some files; it is not content identity.
        return stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns

    if signature(before) != signature(after) or signature(after) != signature(current):
        raise ValueError("Snapshot source changed while hashing")
    return raw.hexdigest(), salted.hexdigest()


def _integer(value: Any, minimum: int = 0) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < minimum or value > 2**63 - 1:
        raise ValueError("Invalid nonnegative integer in snapshot manifest")
    return value


def _member(directory: Path, relative: str) -> Path:
    if not isinstance(relative, str) or not relative or "\\" in relative:
        raise ValueError("Invalid snapshot member path")
    path = Path(relative)
    if path.is_absolute() or any(part in (".", "..") for part in relative.split("/")):
        raise ValueError("Snapshot member escapes artifact directory")
    candidate = directory / path
    if not candidate.is_file() or candidate.resolve() != directory.resolve() / path:
        raise ValueError("Missing or aliased snapshot member")
    return candidate


def _validate_table_schema(
    conn: sqlite3.Connection,
    name: str,
    columns: Tuple[str, ...],
) -> None:
    if conn.execute("SELECT type FROM sqlite_master WHERE name=?", (name,)).fetchone() != ("table",):
        raise ValueError(f"Missing parser table: {name}")
    schema = conn.execute(f'PRAGMA table_info("{name}")').fetchall()
    actual = {row[1]: row for row in schema}
    for column in columns:
        kind = "TEXT" if column in ("callstack", "table", "column", "key", "value") else "INTEGER"
        if column not in actual or actual[column][2].upper() != kind:
            raise ValueError(f"Invalid parser column: {name}.{column}")
    if "id" in columns and [row[1] for row in schema if row[5]] != ["id"]:
        raise ValueError(f"Missing parser primary key: {name}.id")


def validate_member_structure(
    path: Path, device: str, start: int, end: int, *, budget: Union[ValidationBudget, None] = None
) -> None:
    """Check required schema and indexed endpoints, without scanning rows/pages."""
    sidecars = [Path(str(path) + suffix) for suffix in ("-wal", "-shm", "-journal")]
    if any(item.is_symlink() for item in sidecars):
        raise ValueError("Snapshot has an aliased sidecar")
    if sidecars[2].exists():
        raise ValueError("Snapshot has a rollback journal; retry later")
    conn = sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True, timeout=sqlite_timeout(budget))
    with closing(conn), validation_progress(conn, budget):
        conn.execute("PRAGMA query_only=ON")
        conn.execute("BEGIN")
        for name, columns in (
            (f"trace_entry_{device}", TRACE_COLUMNS),
            (f"block_{device}", BLOCK_COLUMNS),
            ("dictionary", ("table", "column", "key", "value")),
        ):
            _validate_table_schema(conn, name, columns)
        low = conn.execute(f'SELECT id FROM "trace_entry_{device}" WHERE id>=0 ORDER BY id LIMIT 1').fetchone()  # nosec B608
        high = conn.execute(f'SELECT id FROM "trace_entry_{device}" WHERE id>=0 ORDER BY id DESC LIMIT 1').fetchone()  # nosec B608
        if low != (start,) or high != (end,):
            raise ValueError("Snapshot event range is incomplete")


def parser_members(
    directory: Path,
    manifest: Dict[str, Any],
    *,
    budget: Union[ValidationBudget, None] = None,
) -> Dict[str, str]:
    """Validate the complete manifest and all DBs; never deserialize the source."""
    if _integer(manifest.get("schemaVersion"), 1) != 1:
        raise ValueError("Unsupported snapshot manifest version")
    if (
        manifest.get("status") != "complete"
        or not isinstance(manifest.get("sourceFile"), str)
        or not manifest["sourceFile"]
    ):
        raise ValueError("Snapshot is incomplete")
    capacity = _integer(manifest.get("eventsPerSlice"), 1)
    devices = manifest.get("devices")
    if not isinstance(devices, dict) or not devices:
        raise ValueError("Missing snapshot devices")
    members = {}
    for device, data in devices.items():
        if re.fullmatch(r"0|[1-9][0-9]*", device) is None:
            raise ValueError("Invalid device ID")
        if not isinstance(data, dict):
            raise ValueError("Invalid device inventory")
        count = _integer(data["eventCount"], 1)
        size = _integer(data["sliceCount"], 1)
        if size != (count + capacity - 1) // capacity or len(data["slices"]) != size:
            raise ValueError("Incomplete snapshot slice inventory")
        if sorted(_integer(index) for index in data["readySlices"]) != list(range(size)):
            raise ValueError("Snapshot slices are not ready")
        for index, item in enumerate(data["slices"]):
            check_budget(budget)
            if not isinstance(item, dict):
                raise ValueError(f"manifest.devices.{device}.slices[{index}]: expected object")
            start, end = index * capacity, min((index + 1) * capacity, count) - 1
            if (
                _integer(item["index"]),
                _integer(item["startEventId"]),
                _integer(item["endEventId"]),
            ) != (index, start, end) or item["ready"] is not True:
                raise ValueError("Invalid snapshot slice range")
            relative = item["file"]
            if relative in members:
                raise ValueError("Duplicate snapshot member")
            path = _member(directory, relative)
            validate_member_structure(path, device, start, end, budget=budget)
            members[relative] = ""
    return members


def seal_manifest(directory: Path, manifest: Dict[str, Any], device: Union[int, None] = None) -> None:
    """Record structural inventory and device selection, without content digests."""
    manifest["parserCache"] = {
        "version": CACHE_CONTRACT_VERSION,
        "requestedDevice": device,
        "members": parser_members(directory, manifest),
    }


def _unique_object(pairs: List[Tuple[str, Any]]) -> Dict[str, Any]:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate snapshot manifest key")
        result[key] = value
    return result


def parse_cache_manifest(raw: bytes) -> Dict[str, Any]:
    """Normalize malformed/deep JSON consistently at every compatible import entry."""
    try:
        manifest = json.loads(raw, object_pairs_hook=_unique_object)
    except RecursionError as error:
        raise ValueError("Snapshot manifest nesting is too deep") from error
    if not isinstance(manifest, dict):
        raise ValueError("Invalid snapshot manifest")
    return manifest


def validate_cache(
    directory: Path,
    cache_hash: str,
    device: Union[int, None] = None,
    *,
    budget: Union[ValidationBudget, None] = None,
) -> Dict[str, Any]:
    path = directory / "manifest.json"
    original = path.read_bytes()
    manifest = parse_cache_manifest(original)
    if not cache_hash or manifest.get("cacheHash") != cache_hash:
        raise ValueError("Snapshot source hash or parser salt changed")
    if device is not None and set(manifest["devices"]) != {str(device)}:
        raise ValueError("Snapshot device selection changed")
    for extension in ("parserCache", "ptSnap"):
        if extension in manifest and not isinstance(manifest[extension], dict):
            raise ValueError("Invalid snapshot extension")
    if not isinstance(manifest.get("ptSnap", {}).get("identity", {}), dict):
        raise ValueError("Invalid producer identity")
    # Validate each declaration independently; an absent selection in one seal
    # must not mask a producer's device-filtered export.
    for selection in (
        manifest.get("parserCache", {}),
        manifest.get("ptSnap", {}).get("identity", {}),
    ):
        selected_device = selection.get("requestedDevice")
        if selected_device is None:
            continue
        _integer(selected_device)
        if device is None:
            raise ValueError("Snapshot cache contains only a selected device")
        if selected_device != device or set(manifest["devices"]) != {str(selected_device)}:
            raise ValueError("Snapshot device selection changed")
    members = parser_members(directory, manifest, budget=budget)
    attestation = manifest.get("parserCache")
    # Historical digest declarations are accepted as member inventories only.
    if attestation is not None and (
        _integer(attestation.get("version"), 1) != CACHE_CONTRACT_VERSION
        or not isinstance(attestation.get("members"), dict)
        or set(attestation["members"]) != set(members)
    ):
        raise ValueError("Snapshot parser data changed")
    # Historical producer declarations must list the same manifest members.
    producer = manifest.get("ptSnap", {})
    if "memberHashKind" in producer and producer["memberHashKind"] != "parser-v1":
        raise ValueError("Unsupported member hash contract")
    if producer.get("memberHashKind") == "parser-v1" and (
        not isinstance(producer.get("members"), dict) or set(producer["members"]) != set(members)
    ):
        raise ValueError("Snapshot producer member inventory changed")
    if "members" in producer and producer.get("memberHashKind") != "parser-v1":
        physical = producer["members"]
        if not isinstance(physical, dict) or set(physical) != set(members):
            raise ValueError("Invalid legacy snapshot member inventory")
    if path.read_bytes() != original:
        raise ValueError("Snapshot manifest changed during validation")
    return manifest
