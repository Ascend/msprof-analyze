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

"""Resolve finalized compatibility datasets above the single-DB Context layer.

Original local reader of the P0 contract; no pickle, migration or producer code.
Native-v2 private replay staging is not a dataset until the native publisher closes,
attests and validates its complete versioned manifest.
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
import sqlite3
from collections import OrderedDict
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
from threading import RLock
from typing import Dict, List, Tuple, Union

from pt_snap_cli.core.cache.snapshot_cache import (
    parse_cache_manifest,
    validate_cache,
)
from pt_snap_cli.core.common.errors import (
    DatabaseSchemaError,
    InvalidDeviceError,
    InvalidParameterError,
    QueryCancelledError,
    QueryTimeoutError,
)
from pt_snap_cli.core.common.validation_budget import (
    ValidationBudget,
    check_budget,
    checked_rows,
    sqlite_timeout,
    validation_progress,
)
from pt_snap_cli.core.dataset.dataset_contract import (
    DatasetContractError,
    DatasetManifest,
    DatasetValidation,
    DeviceRecord,
    QueryScope,
    _unique_object,
    parse_manifest,
    validate_dataset,
)
from pt_snap_cli.core.dataset.dataset_files import hash_file as _hash_file
from pt_snap_cli.core.dataset.dataset_files import readonly_member_uri
from pt_snap_cli.core.dataset.dataset_files import (
    require_readonly_member as _require_readonly_member,
)
from pt_snap_cli.core.dataset.dataset_support import DATASET_SUPPORT
from pt_snap_cli.core.dataset.native_dataset_contract import (
    NATIVE_FORMAT,
    NativeManifest,
    NativeSlice,
    parse_native_manifest,
    require_native_members,
    validate_native_dataset,
    validate_native_scope,
)
from pt_snap_cli.core.importing.validation_receipts import (
    import_validation_active,
    load_receipt,
    receipts_enabled,
    save_receipt,
)

_FileStamp = Tuple[int, int, int, int, int, int, int]
_Generation = Tuple[Tuple[str, _FileStamp], ...]


@dataclass(frozen=True)
class ResolvedDataset:
    root: Path
    validation: DatasetValidation
    fingerprint: str
    ordered_frames_version: Union[int, None] = None
    generation: Union[_Generation, None] = None
    content_verified: bool = True

    def require_unchanged(self, budget: Union[ValidationBudget, None] = None) -> None:
        """Guard a reused report/query resolution without repeating full validation."""
        if _root(self.root) != self.root:
            raise DatabaseSchemaError("Dataset path changed during operation; retry.")
        try:
            current = _generation(self.root, self.validation.manifest, budget)
            if self.generation is None or current != self.generation:
                raise DatabaseSchemaError("Dataset members changed during operation; retry.")
            if self.content_verified and not _cacheable(current):
                if (
                    _content_fingerprint(self.root, self.validation.manifest, budget) != self.fingerprint
                    or _generation(self.root, self.validation.manifest, budget) != current
                ):
                    raise DatabaseSchemaError("Dataset content changed during operation; retry.")
        except (DatasetContractError, OSError) as exc:
            raise DatabaseSchemaError(f"Dataset changed during operation: {exc}") from exc

    @property
    def device_ids(self) -> List[int]:
        return sorted(item.device_id for item in self.validation.manifest.devices)

    @property
    def callstack_layout(self) -> str:
        return "v2" if isinstance(self.validation.manifest, NativeManifest) else "v1"

    @property
    def callstack_layout_error(self) -> None:
        return None

    def device(self, device_id: Union[int, None] = None) -> DeviceRecord:
        selected = self.device_ids[0] if device_id is None else device_id
        for device in self.validation.manifest.devices:
            # pylint: disable-next=unidiomatic-typecheck  # Reject bool/subclasses: the contract requires exact scalar types.
            if type(selected) is int and device.device_id == selected:
                return device
        raise InvalidDeviceError(f"Device {selected} not found. Available: {self.device_ids}")

    def paths(self, scope: QueryScope) -> Tuple[Path, ...]:
        """Address all matching slices; this does not execute/aggregate queries."""
        try:
            manifest = self.validation.manifest
            if isinstance(manifest, NativeManifest):
                validate_native_scope(scope, manifest)
            else:
                scope.validate(manifest)
        except DatasetContractError as exc:
            raise InvalidParameterError(str(exc)) from exc
        return tuple(
            self.root / item.file
            for device in self.validation.manifest.devices
            if scope.device_id is None or device.device_id == scope.device_id
            for item in device.slices
            if (scope.slice_index is None or item.index == scope.slice_index)
            and (scope.start_event_id is None or item.end_event_id >= scope.start_event_id)
            and (scope.end_event_id is None or item.start_event_id <= scope.end_event_id)
        )

    def to_dict(self) -> Dict[str, object]:
        manifest = self.validation.manifest
        return {
            "manifest_path": str(self.root / "manifest.json"),
            "schema_version": manifest.schema_version,
            "status": manifest.status,
            "format": NATIVE_FORMAT if isinstance(manifest, NativeManifest) else "compatibility-v1",
            "fingerprint": self.fingerprint,
            "real_event_count": self.validation.real_event_count,
            "boundary_event_count": self.validation.boundary_event_count,
            "text_callstacks": True,
            "structured_frames": False,
            "cross_slice_queries": True,
            "supported_queries": dict(DATASET_SUPPORT),
            "cross_slice_sources": True,
            "ordered_frames_reader_version": 2,
            "structured_frames_scope": "validation_only; query source coverage is separate",
            "devices": [
                {
                    "device_id": device.device_id,
                    "event_count": device.event_count,
                    "slices": [
                        {
                            "index": item.index,
                            "first_event_id": item.start_event_id,
                            "last_event_id": item.end_event_id,
                            "db_path": str(self.root / item.file),
                        }
                        for item in device.slices
                    ],
                }
                for device in sorted(manifest.devices, key=lambda item: item.device_id)
            ],
        }


# This is deliberately process-local, bounded, and contains no open connections.
# Default reuse verifies all content bytes; metadata alone never proves integrity.
# Skipping byte scans requires the explicit immutable-publication contract.
_CACHE_LIMIT = 16


@dataclass(frozen=True)
class _ValidatedEntry:
    generation: _Generation
    resolved: ResolvedDataset
    # Only admissions bracketed by content hashes can seed default reuse.
    content_verified: bool


_VALIDATED: OrderedDict[Path, _ValidatedEntry] = OrderedDict()
_CACHE_LOCK = RLock()


def _stamp(path: Path) -> _FileStamp:
    stat = path.stat()
    return (
        stat.st_dev,
        stat.st_ino,
        stat.st_size,
        stat.st_mtime_ns,
        stat.st_ctime_ns,
        stat.st_mode,
        stat.st_nlink,
    )


def _root(path: Union[Path, str]) -> Union[Path, None]:
    candidate = Path(path).expanduser().absolute()
    if not candidate.is_dir() and candidate.name != "manifest.json":
        return None
    root = candidate if candidate.is_dir() else candidate.parent
    if candidate.is_symlink() or root.resolve() != root:
        raise DatabaseSchemaError("Dataset must use canonical non-symlink paths.")
    if (root / "manifest.json").is_symlink():
        raise DatabaseSchemaError("Dataset manifest must not be a symlink.")
    if not (root / "manifest.json").is_file():
        raise DatabaseSchemaError("Dataset manifest.json must be a regular file.")
    return root


def _generation(root: Path, manifest: DatasetManifest, budget: Union[ValidationBudget, None]) -> _Generation:
    """Always recheck aliases, transport, and membership before trusting a hit."""
    check_budget(budget)
    if isinstance(manifest, NativeManifest):
        require_native_members(root, manifest, budget=budget)
    stamps = [(".", _stamp(root)), ("manifest.json", _stamp(root / "manifest.json"))]
    for device in checked_rows(manifest.devices, budget):
        directory = f"device_{device.device_id}"
        if (root / directory).is_symlink():
            raise DatabaseSchemaError("Dataset device directory must not be a symlink.")
        stamps.append((directory, _stamp(root / directory)))
        for item in checked_rows(device.slices, budget):
            member = root / item.file
            _require_readonly_member(root, member, immutable=not isinstance(manifest, NativeManifest))
            stamps.append((item.file, _stamp(member)))
            wal = Path(str(member) + "-wal")
            if wal.exists():
                stamps.append((item.file + "-wal", _stamp(wal)))
    check_budget(budget)
    return tuple(stamps)


def _prepare_compatibility_transport(
    root: Path, manifest: DatasetManifest, budget: Union[ValidationBudget, None]
) -> None:
    """Establish read-only WAL sidecars before capturing physical change tokens."""
    for device in checked_rows(manifest.devices, budget):
        for item in checked_rows(device.slices, budget):
            member = root / item.file
            with member.open("rb") as source:
                header = source.read(20)
            if header[18:20] != b"\x02\x02" or Path(str(member) + "-wal").exists():
                continue
            try:
                conn = sqlite3.connect(readonly_member_uri(member), uri=True, timeout=sqlite_timeout(budget))
                with closing(conn), validation_progress(conn, budget):
                    conn.execute("SELECT name FROM sqlite_master LIMIT 1").fetchone()
            except sqlite3.DatabaseError as exc:
                raise DatabaseSchemaError(f"Cannot open dataset member: {exc}") from exc


def _cacheable(generation: _Generation) -> bool:
    # This is a caller contract, not an automatic inference from OS or filesystem
    # metadata. Windows ctime historically means creation time, so stay strong.
    return (
        os.environ.get("PT_SNAP_DATASET_CACHE") == "immutable"
        and os.name == "posix"
        and all(stamp[4] > 0 for _, stamp in generation)
    )


def _content_fingerprint(
    root: Path,
    manifest: DatasetManifest,
    budget: Union[ValidationBudget, None],
    *,
    manifest_hash: Union[str, None] = None,
) -> str:
    """Strong verification for pinned operations without repeating row validation."""
    digest = hashlib.sha256()
    digest.update((manifest_hash or _hash_file(root / "manifest.json", budget=budget)).encode("ascii"))
    for device in checked_rows(manifest.devices, budget):
        for item in checked_rows(device.slices, budget):
            digest.update(item.file.encode("utf-8"))
            digest.update(_hash_file(root / item.file, budget=budget).encode("ascii"))
            wal = root / (item.file + "-wal")
            if wal.exists():
                digest.update(b"-wal")
                digest.update(_hash_file(wal, budget=budget).encode("ascii"))
    return digest.hexdigest()


class DatasetResolver:
    """Resolve and validate finalized datasets, reusing unchanged generations.

    By default every call hashes content; a matching, fully validated in-process
    result skips repeated row validation. Warm work remains O(bytes + shards),
    and new CLI processes are cold. Explicitly setting
    PT_SNAP_DATASET_CACHE=immutable enables bounded process-local reuse under
    the caller's immutable-publication/change-time contract. Even then paths,
    members, sidecars and kernel change times are checked on every call.
    Explicit validators always perform full validation.
    """

    def inspect(
        self,
        path: Union[Path, str],
        *,
        budget: Union[ValidationBudget, None] = None,
    ) -> Union[ResolvedDataset, None]:
        candidate = Path(path).expanduser().absolute()
        with _CACHE_LOCK:
            cache_key = (
                candidate.parent if candidate.name == "manifest.json" and candidate not in _VALIDATED else candidate
            )
        try:
            check_budget(budget)
            root = _root(path)
            if root is None:
                with _CACHE_LOCK:
                    _ = _VALIDATED.pop(cache_key, None)
                return None
            cache_key = root
            if import_validation_active():
                raw = parse_cache_manifest((root / "manifest.json").read_bytes())
                if raw.get("format") != NATIVE_FORMAT:
                    return self._inspect_compatible_structure(root, raw, budget)
            strong_cache = os.environ.get("PT_SNAP_DATASET_CACHE") is None
            with _CACHE_LOCK:
                cached = _VALIDATED.get(root)
            if cached is not None:
                previous, resolved = cached.generation, cached.resolved
                manifest_unchanged = _stamp(root / "manifest.json") == dict(previous)["manifest.json"]
                generation = _generation(root, resolved.validation.manifest, budget) if manifest_unchanged else None
                reuse = False
                if generation is not None and generation == previous:
                    if _cacheable(generation):
                        reuse = True
                    elif strong_cache and cached.content_verified:
                        fingerprint = _content_fingerprint(root, resolved.validation.manifest, budget)
                        if _generation(root, resolved.validation.manifest, budget) != generation:
                            raise DatabaseSchemaError("Dataset changed during inspection; retry.")
                        reuse = fingerprint == resolved.fingerprint
                if reuse:
                    with _CACHE_LOCK:
                        if root in _VALIDATED:
                            _VALIDATED.move_to_end(root)
                    result = copy.deepcopy(resolved)
                    check_budget(budget)
                    return result
                with _CACHE_LOCK:
                    _ = _VALIDATED.pop(root, None)
            manifest_path = root / "manifest.json"
            manifest_stamp = _stamp(manifest_path)
            before = _hash_file(manifest_path, budget=budget)
            with manifest_path.open(encoding="utf-8") as source:
                raw: object = json.load(source, object_pairs_hook=_unique_object)
            check_budget(budget)
            planned = (
                parse_native_manifest(raw, budget=budget)
                if isinstance(raw, dict) and raw.get("format") == NATIVE_FORMAT
                else parse_manifest(raw, budget=budget)
            )
            # Preflight every member before the first SQLite open. Capturing
            # both ends also refuses publication during validation or hashing.
            generation = _generation(root, planned, budget)
            if not isinstance(planned, NativeManifest):
                # Read-only SQLite may create WAL/SHM for a closed WAL-mode DB.
                # Do this only after all paths pass preflight, then capture the
                # actual transport. Subsequent content changes still fail below.
                _prepare_compatibility_transport(root, planned, budget)
                generation = _generation(root, planned, budget)
            if manifest_stamp != _stamp(manifest_path):
                raise DatabaseSchemaError("Dataset manifest changed during inspection; retry.")
            # Compatibility manifests contain no shard digests. Bracket row
            # validation with byte hashes before allowing its result to be reused.
            # Native validation already checks both ends against declared hashes.
            compatibility_before = (
                _content_fingerprint(root, planned, budget, manifest_hash=before)
                if strong_cache and (not isinstance(planned, NativeManifest) or receipts_enabled())
                else None
            )
            receipt = load_receipt(root, "dataset", compatibility_before) if compatibility_before is not None else None
            counts = [receipt.get(key) for key in ("real", "boundary")] if receipt is not None else []
            # pylint: disable-next=unidiomatic-typecheck  # Reject bool/subclasses: the contract requires exact scalar types.
            receipt_hit = len(counts) == 2 and all(type(n) is int and n >= 0 for n in counts)
            if receipt_hit:
                assert receipt is not None  # nosec B101 # Internal invariant after validation; not an input security check.
                real, boundary = receipt["real"], receipt["boundary"]
                assert isinstance(real, int) and isinstance(boundary, int)  # nosec B101 # Internal invariant after validation; not an input security check.
                validation = DatasetValidation(planned, real, boundary)
            else:
                validation = (
                    validate_native_dataset(root, planned, budget=budget)
                    if isinstance(planned, NativeManifest)
                    else validate_dataset(root, budget=budget)
                )
            if (
                not receipt_hit
                and not isinstance(planned, NativeManifest)
                and isinstance(raw, dict)
                and ("parserCache" in raw or "ptSnap" in raw)
            ):
                try:
                    attestation = raw.get("parserCache", {})
                    if not isinstance(attestation, dict):
                        raise ValueError("parserCache: expected object")
                    producer = raw.get("ptSnap", {})
                    if not isinstance(producer, dict):
                        raise ValueError("ptSnap: expected object")
                    identity = producer.get("identity", {})
                    if not isinstance(identity, dict):
                        raise ValueError("ptSnap.identity: expected object")
                    selected = attestation.get("requestedDevice")
                    if selected is None:
                        selected = identity.get("requestedDevice")
                    # pylint: disable-next=unidiomatic-typecheck  # Reject bool/subclasses: the contract requires exact scalar types.
                    if selected is not None and (type(selected) is not int or selected < 0):
                        raise ValueError("parserCache.requestedDevice: expected nonnegative integer")
                    validate_cache(root, raw["cacheHash"], selected, budget=budget)
                except (ValueError, KeyError, TypeError, sqlite3.DatabaseError) as exc:
                    raise DatasetContractError(
                        "parserCache" if "parserCache" in raw else "ptSnap", "seal", str(exc)
                    ) from exc
            digest = hashlib.sha256()
            digest.update(before.encode("ascii"))
            for device in checked_rows(() if receipt_hit else validation.manifest.devices, budget):
                for item in checked_rows(device.slices, budget):
                    digest.update(item.file.encode("utf-8"))
                    # Native validation already verifies this digest before and
                    # after SQLite reads; do not hash every shard a third time.
                    content_hash = (
                        item.sha256 if isinstance(item, NativeSlice) else _hash_file(root / item.file, budget=budget)
                    )
                    digest.update(content_hash.encode("ascii"))
                    wal = root / (item.file + "-wal")
                    if wal.exists():
                        digest.update(b"-wal")
                        digest.update(_hash_file(wal, budget=budget).encode("ascii"))
            fingerprint = compatibility_before if receipt_hit else digest.hexdigest()
            assert fingerprint is not None  # nosec B101 # Internal invariant after validation; not an input security check.
            if compatibility_before is not None and compatibility_before != fingerprint:
                raise DatabaseSchemaError("Dataset content changed during inspection; retry.")
            if before != _hash_file(manifest_path, budget=budget):
                raise DatabaseSchemaError("Dataset manifest changed during inspection; retry.")
            if generation != _generation(root, planned, budget):
                raise DatabaseSchemaError("Dataset members changed during inspection; retry.")
            extensions = raw.get("extensions") if isinstance(raw, dict) else None
            frames = extensions.get("ptSnapOrderedFrames") if isinstance(extensions, dict) else None
            version = frames.get("version") if isinstance(frames, dict) else None
            result = ResolvedDataset(
                root,
                validation,
                fingerprint,
                # pylint: disable-next=unidiomatic-typecheck  # Reject bool/subclasses: the contract requires exact scalar types.
                version if type(version) is int else None,
                generation,
            )
            check_budget(budget)
            save_receipt(
                root,
                "dataset",
                fingerprint,
                {
                    "real": validation.real_event_count,
                    "boundary": validation.boundary_event_count,
                },
            )
            if strong_cache or _cacheable(generation):
                entry = _ValidatedEntry(
                    generation,
                    copy.deepcopy(result),
                    isinstance(planned, NativeManifest) or compatibility_before is not None,
                )
                check_budget(budget)
                with _CACHE_LOCK:
                    _VALIDATED[root] = entry
                    _VALIDATED.move_to_end(root)
                    while len(_VALIDATED) > _CACHE_LIMIT:
                        _ = _VALIDATED.popitem(last=False)
            return result
        except (
            DatasetContractError,
            OSError,
            UnicodeError,
            json.JSONDecodeError,
        ) as exc:
            with _CACHE_LOCK:
                _ = _VALIDATED.pop(cache_key, None)
            raise DatabaseSchemaError(f"Invalid dataset: {exc}") from exc
        except RecursionError as exc:
            with _CACHE_LOCK:
                _ = _VALIDATED.pop(cache_key, None)
            raise DatabaseSchemaError("Invalid dataset: manifest nesting is too deep") from exc
        except (DatabaseSchemaError, QueryTimeoutError, QueryCancelledError):
            with _CACHE_LOCK:
                _ = _VALIDATED.pop(cache_key, None)
            raise

    @staticmethod
    def _inspect_compatible_structure(
        root: Path, raw: Dict[str, object], budget: Union[ValidationBudget, None]
    ) -> ResolvedDataset:
        manifest = parse_manifest(raw, budget=budget)
        _generation(root, manifest, budget)  # Preflight all members before SQLite opens.
        _prepare_compatibility_transport(root, manifest, budget)
        generation = _generation(root, manifest, budget)
        attestation = raw.get("parserCache", {})
        producer = raw.get("ptSnap", {})
        if not isinstance(attestation, dict) or not isinstance(producer, dict):
            raise DatabaseSchemaError("Invalid cache extension")
        identity = producer.get("identity", {})
        if not isinstance(identity, dict):
            raise DatabaseSchemaError("Invalid producer identity")
        selected = attestation.get("requestedDevice")
        if selected is None:
            selected = identity.get("requestedDevice")
        cache_hash = raw.get("cacheHash")
        if not isinstance(cache_hash, str):
            raise DatabaseSchemaError("Invalid cacheHash")
        checked = validate_cache(root, cache_hash, selected, budget=budget)
        if checked != raw:
            raise DatabaseSchemaError("Dataset manifest changed during inspection; retry.")
        boundary = 0
        for device in manifest.devices:
            for item in device.slices:
                conn = sqlite3.connect(readonly_member_uri(root / item.file), uri=True, timeout=sqlite_timeout(budget))
                with closing(conn), validation_progress(conn, budget):
                    # Count only synthetic IDs through the integer primary key;
                    # never fetch/encode callstacks or scan block contents.
                    boundary += conn.execute(
                        f'SELECT COUNT(*) FROM "trace_entry_{device.device_id}" WHERE id<0'  # nosec B608
                    ).fetchone()[0]
        if raw != parse_cache_manifest((root / "manifest.json").read_bytes()) or generation != _generation(
            root, manifest, budget
        ):
            raise DatabaseSchemaError("Dataset changed during inspection; retry.")
        extensions = raw.get("extensions", {})
        frames = extensions.get("ptSnapOrderedFrames", {}) if isinstance(extensions, dict) else {}
        version = frames.get("version") if isinstance(frames, dict) else None
        fingerprint = "structure-" + hashlib.sha256(repr(generation).encode()).hexdigest()
        return ResolvedDataset(
            root,
            DatasetValidation(manifest, sum(d.event_count for d in manifest.devices), boundary),
            fingerprint,
            # pylint: disable-next=unidiomatic-typecheck  # Reject bool/subclasses: the contract requires exact scalar types.
            version if type(version) is int else None,
            generation,
            False,
        )

    def completion_device_ids(self, path: Union[Path, str]) -> Union[List[int], None]:
        """Bounded manifest-only hints, never evidence of dataset validity.

        Completion must not open or hash shard contents. Large or invalid
        manifests produce no hints; a real query still performs strong admission.
        """
        root = _root(path)
        if root is None:
            return None
        try:
            with (root / "manifest.json").open("rb") as source:
                data = source.read(1024 * 1024 + 1)
            if len(data) > 1024 * 1024:
                return []
            raw: object = json.loads(data, object_pairs_hook=_unique_object)
            manifest = (
                parse_native_manifest(raw)
                if isinstance(raw, dict) and raw.get("format") == NATIVE_FORMAT
                else parse_manifest(raw)
            )
            return sorted(device.device_id for device in manifest.devices)
        except (DatasetContractError, OSError, UnicodeError, json.JSONDecodeError):
            return []
