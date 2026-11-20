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

import json
import logging
import sqlite3
from contextlib import nullcontext
from dataclasses import replace
from pathlib import Path
from typing import Union

from pt_snap_cli.core.analysis.focus_service import FocusService
from pt_snap_cli.core.cache.snapshot_cache import (
    parse_cache_manifest,
    source_hashes,
    validate_cache,
)
from pt_snap_cli.core.common.errors import (
    DatabaseSchemaError,
    FocusFileInvalidError,
    ImportExecutionError,
    ImportMetadataError,
    InvalidDeviceError,
    InvalidParameterError,
    SnapshotFileInvalidError,
    SourceChangedError,
)
from pt_snap_cli.core.common.models import (
    CacheMissReason,
    FocusState,
    ImportMetadata,
    ImportOptions,
    ImportResult,
)
from pt_snap_cli.core.dataset.dataset_contract import parse_manifest
from pt_snap_cli.core.dataset.dataset_resolver import (
    DatasetResolver,
    ResolvedDataset,
    _require_readonly_member,
)
from pt_snap_cli.core.dataset.native_dataset_contract import (
    NATIVE_FORMAT,
    build_native_manifest,
    cache_identity,
)
from pt_snap_cli.core.importing.dataset_import_backend import DatasetImportBackend
from pt_snap_cli.core.importing.import_metadata import (
    NATIVE_IMPORT_FORMAT_VERSION,
    ImportMetadataService,
)
from pt_snap_cli.core.importing.msinsight_export import (
    COMPATIBILITY_FORMAT,
    DEFAULT_CAPACITY,
    MsinsightImportBackend,
    build_compatible_manifest,
    compatible_identity,
    convert_shards,
    inspect_owned_cache,
)
from pt_snap_cli.core.importing.ordered_frame_integrity import (
    frame_member_digest,
    require_frame_declaration,
)
from pt_snap_cli.core.importing.snapshot_import_backend import SnapshotImportBackend
from pt_snap_cli.core.importing.validation_receipts import (
    import_receipts,
    load_receipt,
    save_receipt,
)
from pt_snap_cli.core.splitting.sharded_replay_service import ShardedReplayResult

logger = logging.getLogger(__name__)

VALID_SUFFIXES = {".pkl", ".pickle"}


class ImportService:
    """Import PyTorch snapshot pickle files through the built-in backend."""

    def __init__(
        self,
        focus_service: Union[FocusService, None] = None,
        backend: Union[SnapshotImportBackend, None] = None,
        metadata_service: Union[ImportMetadataService, None] = None,
        dataset_backend: Union[DatasetImportBackend, None] = None,
    ) -> None:
        self._focus_service: Union[FocusService, None] = focus_service
        self._backend: SnapshotImportBackend = backend or SnapshotImportBackend()
        self._metadata_service: ImportMetadataService = metadata_service or ImportMetadataService()
        self._dataset_backend = dataset_backend or DatasetImportBackend()
        self._msinsight_backend = MsinsightImportBackend()

    def import_snapshot(self, options: ImportOptions) -> ImportResult:
        with import_receipts():
            return self._import_snapshot(options)

    def _import_snapshot(self, options: ImportOptions) -> ImportResult:
        self._validate_options(options)
        self._validate_snapshot_file(options.snapshot_file)
        if options.format in (COMPATIBILITY_FORMAT, "msinsight"):
            return self._import_compatible_dataset(options)
        if options.events_per_slice is not None:
            return self._import_dataset(options)
        output_dir = self._resolve_output_dir(options.snapshot_file, options.output_dir)
        db_path = self._backend.target_db_path(options.snapshot_file, output_dir)

        try:
            source_sha256 = self._metadata_service.calculate_sha256(options.snapshot_file)
        except ImportMetadataError as exc:
            raise ImportExecutionError(str(exc)) from exc

        decision = self._metadata_service.evaluate_cache(
            db_path=db_path,
            source_sha256=source_sha256,
            requested_device=options.device,
            force=options.force,
        )
        if decision.reused:
            if decision.metadata is None:
                raise AssertionError("Cache hit must include import metadata")
            focus_state = self._set_focus_if_requested(db_path, options)
            return ImportResult(
                db_path=db_path,
                device_id=options.device,
                focus_state=focus_state,
                reused=True,
                metadata=decision.metadata,
                cache_miss_reason=None,
            )

        completed_metadata: Union[ImportMetadata, None] = None

        def finalize_temp_db(tmp_db_path: Path) -> None:
            nonlocal completed_metadata
            try:
                final_sha256 = self._metadata_service.calculate_sha256(options.snapshot_file)
            except ImportMetadataError as exc:
                raise ImportExecutionError(str(exc)) from exc
            if final_sha256 != source_sha256:
                raise SourceChangedError(
                    "Snapshot source changed while import was running; existing database preserved."
                )

            try:
                metadata = self._metadata_service.build_metadata(
                    source_path=options.snapshot_file,
                    source_sha256=final_sha256,
                    requested_device=options.device,
                )
                self._metadata_service.write(tmp_db_path, metadata)
                inspection = self._metadata_service.inspect(tmp_db_path)
            except (ImportMetadataError, DatabaseSchemaError) as exc:
                raise ImportExecutionError(f"Imported database metadata is invalid: {exc}") from exc

            if inspection.status != "available" or inspection.metadata != metadata:
                raise ImportExecutionError("Imported database metadata validation failed.")
            completed_metadata = metadata

        focus_state: Union[FocusState, None] = None

        def set_focus_after_publish(published_db_path: Path) -> None:
            nonlocal focus_state
            focus_state = self._set_focus_if_requested(published_db_path, options)

        db_path = self._backend.dump_to_db(
            options.snapshot_file,
            output_dir,
            options.device,
            finalize_temp_db=finalize_temp_db,
            post_publish=set_focus_after_publish if options.set_focus else None,
        )
        if completed_metadata is None:
            raise ImportExecutionError("Imported database metadata was not produced.")

        return ImportResult(
            db_path=db_path,
            device_id=options.device,
            focus_state=focus_state,
            reused=False,
            metadata=completed_metadata,
            cache_miss_reason=decision.reason,
        )

    @staticmethod
    def _validate_options(options: ImportOptions) -> None:
        capacity = options.events_per_slice
        # pylint: disable-next=unidiomatic-typecheck  # Reject bool/subclasses: the contract requires exact scalar types.
        if capacity is not None and (type(capacity) is not int or capacity <= 0):
            raise InvalidParameterError("events_per_slice must be a positive integer.")
        # pylint: disable-next=unidiomatic-typecheck  # Reject bool/subclasses: the contract requires exact scalar types.
        if options.device is not None and (type(options.device) is not int or options.device < 0):
            raise InvalidParameterError("device must be a nonnegative integer.")
        selected_format = (
            options.format if options.format is not None else (NATIVE_FORMAT if capacity is not None else "single-db")
        )
        if selected_format in (COMPATIBILITY_FORMAT, "msinsight"):
            return
        if selected_format not in ("single-db", NATIVE_FORMAT):
            raise InvalidParameterError(f"Unsupported import format: {selected_format}")
        if (capacity is not None) != (selected_format == NATIVE_FORMAT):
            raise InvalidParameterError("pt-snap-native-v2 requires --events-per-slice; single-db forbids it.")

    def _import_dataset(self, options: ImportOptions) -> ImportResult:
        assert options.events_per_slice is not None  # nosec B101 # Internal invariant after validation; not an input security check.
        capacity = options.events_per_slice
        output = (
            (options.output_dir if options.output_dir is not None else options.snapshot_file.parent)
            .expanduser()
            .absolute()
        )
        target = self._dataset_backend.target_path(options.snapshot_file, output)
        if target.resolve() != target or target.is_symlink():
            raise ImportExecutionError("Dataset output must be canonical and non-symlink.")
        source_hash = self._hash_source(options.snapshot_file)
        existing = self._dataset_backend.inspect_target(target)
        reason: CacheMissReason = "database_missing"
        if existing is not None:
            manifest, expected = existing
            reason = "forced" if options.force else "dataset_identity_changed"
            try:
                dataset = DatasetResolver().inspect(target)
            except (DatabaseSchemaError, OSError):
                dataset = None
                if not options.force:
                    reason = "database_invalid"
            if (
                not options.force
                and dataset is not None
                and manifest.identity == cache_identity(source_hash, options.device, capacity)
            ):
                try:
                    require_frame_declaration(parse_cache_manifest((target / "manifest.json").read_bytes()))
                    if load_receipt(target, "native-frames", dataset.fingerprint) != {}:
                        for device in manifest.devices:
                            for item in device.slices:
                                frame_member_digest(target, target / item.file, device.device_id)
                        dataset.require_unchanged()
                        save_receipt(target, "native-frames", dataset.fingerprint, {})
                except (ValueError, OSError, sqlite3.DatabaseError, DatabaseSchemaError) as exc:
                    raise ImportExecutionError(
                        f"Existing native ordered-frame evidence is invalid; use --force to rebuild. Existing target and focus preserved: {exc}"
                    ) from exc
                self._recheck_source(options.snapshot_file, source_hash)
                focus_state = self._set_focus_if_requested(target, options)
                return ImportResult(
                    target,
                    options.device,
                    focus_state,
                    True,
                    manifest.metadata,
                    None,
                    target,
                    tuple(dataset.device_ids),
                    sum(len(d.slices) for d in manifest.devices),
                    NATIVE_FORMAT,
                    manifest.omitted_devices,
                )
            if not options.force:
                raise ImportExecutionError(
                    f"Existing dataset is not reusable ({reason}); use --force to replace this recognized native artifact. Existing target and focus preserved."
                )
        else:
            expected = None
        completed: Union[ImportMetadata, None] = None
        generated: Union[ShardedReplayResult, None] = None

        def finalize(result: ShardedReplayResult) -> None:
            nonlocal completed, generated
            metadata = replace(
                self._metadata_service.build_metadata(options.snapshot_file, source_hash, options.device),
                import_format_version=NATIVE_IMPORT_FORMAT_VERSION,
            )
            for item in result.slices:
                _require_readonly_member(result.directory, item.file)
                self._metadata_service.write(item.file, metadata)
                frame_member_digest(result.directory, item.file, item.device)
            manifest = build_native_manifest(result, metadata, capacity)
            require_frame_declaration(manifest)
            with (result.directory / "manifest.json").open("x", encoding="utf-8") as file:
                json.dump(manifest, file, indent=2)
            validated = DatasetResolver().inspect(result.directory)
            if validated is None:
                raise ImportExecutionError("Staged dataset validation did not produce a complete artifact.")
            self._remember_published_validation(target, validated)
            save_receipt(target, "native-frames", validated.fingerprint, {})
            completed, generated = metadata, result

        focus_state: Union[FocusState, None] = None

        def focus(path: Path) -> None:
            nonlocal focus_state
            focus_state = self._set_focus_if_requested(path, options)

        self._dataset_backend.dump_to_dataset(
            options.snapshot_file,
            target,
            capacity=capacity,
            device=options.device,
            expected=expected,
            finalize=finalize,
            post_publish=focus if options.set_focus else None,
            pre_publish=lambda: self._recheck_source(options.snapshot_file, source_hash),
        )
        assert completed is not None and generated is not None  # nosec B101 # Internal invariant after validation; not an input security check.
        return ImportResult(
            target,
            options.device,
            focus_state,
            False,
            completed,
            reason,
            target,
            tuple(sorted({s.device for s in generated.slices})),
            len(generated.slices),
            NATIVE_FORMAT,
            generated.omitted_devices,
        )

    def _import_compatible_dataset(self, options: ImportOptions) -> ImportResult:
        capacity = options.events_per_slice or DEFAULT_CAPACITY
        output = (
            (options.output_dir if options.output_dir is not None else options.snapshot_file.parent)
            .expanduser()
            .absolute()
        )
        target = self._msinsight_backend.target_path(options.snapshot_file, output)
        if target.resolve() != target or target.is_symlink():
            raise ImportExecutionError("Compatible output must be canonical and non-symlink.")
        try:
            source_hash, cache_hash = source_hashes(options.snapshot_file)
        except (OSError, ValueError) as exc:
            raise ImportExecutionError(f"Cannot calculate msinsight cacheHash: {exc}") from exc
        if target.exists():
            try:
                external_manifest = parse_cache_manifest((target / "manifest.json").read_bytes())
                if isinstance(external_manifest, dict) and "ptSnap" not in external_manifest:
                    # A compatible producer is not pt-snap-owned. Reuse read-only;
                    # never invent provenance metadata or replace it under force.
                    checked = validate_cache(target, cache_hash, options.device)
                    manifest = parse_manifest(checked)
                    if options.events_per_slice is not None and options.events_per_slice != manifest.events_per_slice:
                        raise ValueError(
                            "Explicit events_per_slice does not match the existing compatible "
                            "cache; choose a new output directory."
                        )
                    self._recheck_source(options.snapshot_file, source_hash)
                    return ImportResult(
                        target,
                        options.device,
                        self._set_focus_if_requested(target, options),
                        True,
                        None,
                        None,
                        target,
                        tuple(sorted(d.device_id for d in manifest.devices)),
                        sum(len(d.slices) for d in manifest.devices),
                        COMPATIBILITY_FORMAT,
                    )
                owned = inspect_owned_cache(target)
                if (
                    owned.identity != compatible_identity(source_hash, options.device, capacity)
                    or owned.manifest.cache_hash != cache_hash
                    or owned.manifest.source_file != str(options.snapshot_file.resolve())
                    or owned.metadata.source_size != options.snapshot_file.stat().st_size
                ):
                    raise ValueError("Source/options/format identity changed")
            except FileNotFoundError as exc:
                raise ImportExecutionError(
                    f"Existing compatible output is not reusable; preserved even under --force. "
                    f"Required artifact file is missing: {exc.filename}. Choose a new output directory."
                ) from exc
            except (
                ValueError,
                KeyError,
                TypeError,
                OSError,
                sqlite3.DatabaseError,
                DatabaseSchemaError,
            ) as exc:
                raise ImportExecutionError(
                    f"Existing compatible output is not reusable; preserved even under --force. Choose a new output directory: {exc}"
                ) from exc
            self._recheck_source(options.snapshot_file, source_hash)
            return ImportResult(
                target,
                options.device,
                self._set_focus_if_requested(target, options),
                True,
                owned.metadata,
                None,
                target,
                tuple(sorted(d.device_id for d in owned.manifest.devices)),
                sum(len(d.slices) for d in owned.manifest.devices),
                COMPATIBILITY_FORMAT,
                owned.omitted_devices,
            )
        completed: Union[ImportMetadata, None] = None
        generated: Union[ShardedReplayResult, None] = None

        def finalize(result: ShardedReplayResult) -> None:
            nonlocal completed, generated
            convert_shards(result)
            metadata = replace(
                self._metadata_service.build_metadata(options.snapshot_file, source_hash, options.device),
                import_format_version=1,
            )
            for item in result.slices:
                _require_readonly_member(result.directory, item.file)
                self._metadata_service.write(item.file, metadata)
            manifest = build_compatible_manifest(result, metadata, options.snapshot_file, capacity, cache_hash)
            with (result.directory / "manifest.json").open("x", encoding="utf-8") as file:
                json.dump(manifest, file, indent=2)
            validated = DatasetResolver().inspect(result.directory)
            if validated is None or inspect_owned_cache(result.directory).metadata != metadata:
                raise ImportExecutionError("Staged compatible artifact validation failed")
            completed, generated = metadata, result

        focus_state: Union[FocusState, None] = None

        def focus(path: Path) -> None:
            nonlocal focus_state
            focus_state = self._set_focus_if_requested(path, options)

        self._msinsight_backend.dump_to_dataset(
            options.snapshot_file,
            target,
            capacity=capacity,
            device=options.device,
            expected=None,
            finalize=finalize,
            post_publish=focus if options.set_focus else None,
            pre_publish=lambda: self._recheck_source(options.snapshot_file, source_hash),
        )
        assert completed is not None and generated is not None  # nosec B101 # Internal invariant after validation; not an input security check.
        return ImportResult(
            target,
            options.device,
            focus_state,
            False,
            completed,
            "database_missing",
            target,
            tuple(sorted({s.device for s in generated.slices})),
            len(generated.slices),
            COMPATIBILITY_FORMAT,
            generated.omitted_devices,
        )

    @staticmethod
    def _remember_published_validation(target: Path, validated: ResolvedDataset) -> None:
        if not validated.content_verified:
            return
        # Publication only renames the staged directory. The receipt is bound to
        # all manifest/member bytes, so another artifact at target cannot hit it.
        save_receipt(
            target,
            "dataset",
            validated.fingerprint,
            {
                "real": validated.validation.real_event_count,
                "boundary": validated.validation.boundary_event_count,
            },
        )

    def _hash_source(self, source: Path) -> str:
        try:
            return self._metadata_service.calculate_sha256(source)
        except ImportMetadataError as exc:
            raise ImportExecutionError(str(exc)) from exc

    def _recheck_source(self, source: Path, initial_hash: str) -> None:
        if self._hash_source(source) != initial_hash:
            raise SourceChangedError("Snapshot source changed while import was running; existing artifact preserved.")

    def _set_focus_if_requested(
        self,
        db_path: Path,
        options: ImportOptions,
    ) -> Union[FocusState, None]:
        if not options.set_focus:
            return None
        if self._focus_service is None:
            self._focus_service = FocusService()
        try:
            transaction = (
                self._focus_service.project_focus_transaction()
                if options.events_per_slice is not None or options.format in (COMPATIBILITY_FORMAT, "msinsight")
                else nullcontext()
            )
            with transaction:
                return self._focus_service.set_project_focus(
                    db_path=db_path,
                    device_id=options.device,
                )
        except (FocusFileInvalidError, DatabaseSchemaError, InvalidDeviceError, OSError) as exc:
            raise ImportExecutionError(f"Imported database cannot be registered as focus: {exc}") from exc

    @staticmethod
    def _validate_snapshot_file(path: Path) -> None:
        if not path.exists():
            raise SnapshotFileInvalidError(f"Snapshot file does not exist: {path}")
        if not path.is_file():
            raise SnapshotFileInvalidError(f"Snapshot path is not a file: {path}")
        if path.suffix.lower() not in VALID_SUFFIXES:
            raise SnapshotFileInvalidError(f"Snapshot suffix must be .pkl or .pickle, got {path.suffix!r}")

    @staticmethod
    def _resolve_output_dir(snapshot_file: Path, output_dir: Union[Path, None]) -> Path:
        return output_dir.resolve() if output_dir is not None else snapshot_file.resolve().parent
