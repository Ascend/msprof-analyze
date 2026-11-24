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

import hashlib
import sqlite3
from contextlib import closing
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Union

from pt_snap_cli import __version__
from pt_snap_cli.context import Context, DatabaseNotFoundError, SchemaVersionError
from pt_snap_cli.core.cache.snapshot_cache import parse_cache_manifest
from pt_snap_cli.core.common.errors import (
    DatabaseMissingError,
    DatabaseSchemaError,
    ImportMetadataError,
)
from pt_snap_cli.core.common.models import (
    CacheDecision,
    ImportMetadata,
    MetadataInspection,
)
from pt_snap_cli.core.dataset.dataset_resolver import DatasetResolver
from pt_snap_cli.core.dataset.native_dataset_contract import NativeManifest
from pt_snap_cli.core.importing.import_metadata_contract import (
    metadata_from_mapping,
    validate_import_metadata,
)
from pt_snap_cli.core.importing.msinsight_export import inspect_owned_cache

METADATA_TABLE = "pt_snap_metadata"
METADATA_SCHEMA_VERSION = 1
# Standalone databases retain the v2 callstackId/text layout and add original-
# order structured frames in v3. Only standalone v2 caches require re-import.
IMPORT_FORMAT_VERSION = 3
# Native shard metadata and cache identity retain their published v2 contract.
NATIVE_IMPORT_FORMAT_VERSION = 2
IMPORTER_NAME = "pt-snap-cli"
HASH_CHUNK_SIZE = 1024 * 1024

_REQUIRED_COLUMNS = {
    "id",
    "metadata_schema_version",
    "import_format_version",
    "source_sha256",
    "source_size",
    "source_name",
    "requested_device",
    "importer_name",
    "importer_version",
    "completed_at",
}


class ImportMetadataService:
    def calculate_sha256(self, source_path: Path) -> str:
        digest = hashlib.sha256()
        try:
            with source_path.open("rb") as source:
                while True:
                    chunk = source.read(HASH_CHUNK_SIZE)
                    if not chunk:
                        break
                    digest.update(chunk)
        except OSError as exc:
            raise ImportMetadataError(f"Cannot hash snapshot file {source_path}: {exc}") from exc
        return digest.hexdigest()

    def build_metadata(
        self,
        source_path: Path,
        source_sha256: str,
        requested_device: Union[int, None],
    ) -> ImportMetadata:
        try:
            source_size = source_path.stat().st_size
        except OSError as exc:
            raise ImportMetadataError(f"Cannot inspect snapshot file {source_path}: {exc}") from exc

        return ImportMetadata(
            metadata_schema_version=METADATA_SCHEMA_VERSION,
            import_format_version=IMPORT_FORMAT_VERSION,
            source_sha256=source_sha256,
            source_size=source_size,
            source_name=source_path.name,
            requested_device=requested_device,
            importer_name=IMPORTER_NAME,
            importer_version=__version__,
            completed_at=datetime.now(timezone.utc).isoformat(),
        )

    def inspect(self, db_path: Union[Path, str]) -> MetadataInspection:
        dataset = DatasetResolver().inspect(db_path)
        path = Path(db_path).expanduser().resolve()
        if dataset is not None:
            if isinstance(dataset.validation.manifest, NativeManifest):
                return MetadataInspection(path, "available", dataset.validation.manifest.metadata)
            # External P0 metadata remains optional. Only a recognized complete
            # pt-snap manifest attestation can provide dataset-wide metadata.
            try:
                raw = parse_cache_manifest((dataset.root / "manifest.json").read_bytes())
            except (OSError, ValueError):
                return MetadataInspection(path, "invalid", reason="metadata_invalid")
            if "ptSnap" in raw:
                try:
                    owned = inspect_owned_cache(dataset.root)
                except (ValueError, KeyError, TypeError, OSError, sqlite3.DatabaseError):
                    return MetadataInspection(path, "invalid", reason="metadata_invalid")
                return MetadataInspection(path, "available", owned.metadata)
            return MetadataInspection(path, "unavailable", reason="metadata_missing")
        try:
            context = Context(path)
        except DatabaseNotFoundError as exc:
            raise DatabaseMissingError(str(exc)) from exc
        except (SchemaVersionError, sqlite3.DatabaseError) as exc:
            raise DatabaseSchemaError(str(exc)) from exc

        try:
            with context.connect() as conn:
                table = conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                    (METADATA_TABLE,),
                ).fetchone()
                if table is None:
                    return MetadataInspection(
                        db_path=path,
                        status="unavailable",
                        reason="metadata_missing",
                    )

                columns = {row["name"] for row in conn.execute(f"PRAGMA table_info({METADATA_TABLE})")}
                if not _REQUIRED_COLUMNS.issubset(columns):
                    return MetadataInspection(
                        db_path=path,
                        status="invalid",
                        reason="metadata_invalid",
                    )

                rows = conn.execute(f"SELECT * FROM {METADATA_TABLE}").fetchall()  # nosec B608 # METADATA_TABLE is a module constant; metadata values use bound parameters.
        except sqlite3.DatabaseError:
            return MetadataInspection(
                db_path=path,
                status="invalid",
                reason="metadata_invalid",
            )

        if len(rows) != 1 or rows[0]["id"] != 1:
            return MetadataInspection(
                db_path=path,
                status="invalid",
                reason="metadata_invalid",
            )

        try:
            metadata = self._metadata_from_row(dict(rows[0]))
        except (KeyError, TypeError, ValueError):
            return MetadataInspection(
                db_path=path,
                status="invalid",
                reason="metadata_invalid",
            )

        if metadata.metadata_schema_version != METADATA_SCHEMA_VERSION:
            return MetadataInspection(
                db_path=path,
                status="invalid",
                metadata=metadata,
                reason="metadata_version_unsupported",
            )

        return MetadataInspection(db_path=path, status="available", metadata=metadata)

    def write(self, db_path: Union[Path, str], metadata: ImportMetadata) -> None:
        path = Path(db_path)
        try:
            self._validate_metadata(metadata, allow_unsupported_version=False)
        except (TypeError, ValueError) as exc:
            raise ImportMetadataError(f"Cannot write invalid import metadata: {exc}") from exc
        try:
            # pylint: disable-next=confusing-with-statement  # closing() owns lifetime; the SQLite context owns the transaction.
            with closing(sqlite3.connect(path)) as conn, conn:
                conn.execute(f"DROP TABLE IF EXISTS {METADATA_TABLE}")
                conn.execute(f"""
                    CREATE TABLE {METADATA_TABLE} (
                        id INTEGER PRIMARY KEY CHECK (id = 1),
                        metadata_schema_version INTEGER NOT NULL,
                        import_format_version INTEGER NOT NULL,
                        source_sha256 TEXT NOT NULL,
                        source_size INTEGER NOT NULL,
                        source_name TEXT NOT NULL,
                        requested_device INTEGER,
                        importer_name TEXT NOT NULL,
                        importer_version TEXT NOT NULL,
                        completed_at TEXT NOT NULL
                    )
                """)
                conn.execute(
                    f"""
                    INSERT INTO {METADATA_TABLE} (
                        id, metadata_schema_version, import_format_version,
                        source_sha256, source_size, source_name, requested_device,
                        importer_name, importer_version, completed_at
                    ) VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,  # nosec B608 # METADATA_TABLE is a module constant; metadata values use bound parameters.
                    (
                        metadata.metadata_schema_version,
                        metadata.import_format_version,
                        metadata.source_sha256,
                        metadata.source_size,
                        metadata.source_name,
                        metadata.requested_device,
                        metadata.importer_name,
                        metadata.importer_version,
                        metadata.completed_at,
                    ),
                )
        except sqlite3.DatabaseError as exc:
            raise ImportMetadataError(f"Cannot write import metadata to {path}: {exc}") from exc

    def evaluate_cache(
        self,
        db_path: Union[Path, str],
        source_sha256: str,
        requested_device: Union[int, None],
        force: bool = False,
    ) -> CacheDecision:
        path = Path(db_path)
        if not path.exists():
            return CacheDecision(reused=False, metadata=None, reason="database_missing")
        if force:
            return CacheDecision(reused=False, metadata=None, reason="forced")

        try:
            inspection = self.inspect(path)
        except (DatabaseMissingError, DatabaseSchemaError):
            return CacheDecision(reused=False, metadata=None, reason="database_invalid")

        if inspection.status != "available" or inspection.metadata is None:
            return CacheDecision(
                reused=False,
                metadata=inspection.metadata,
                reason=inspection.reason or "metadata_invalid",
            )

        metadata = inspection.metadata
        if metadata.source_sha256 != source_sha256:
            return CacheDecision(reused=False, metadata=metadata, reason="source_changed")
        if metadata.import_format_version != IMPORT_FORMAT_VERSION:
            return CacheDecision(reused=False, metadata=metadata, reason="import_format_changed")
        if metadata.requested_device != requested_device:
            return CacheDecision(reused=False, metadata=metadata, reason="device_changed")
        return CacheDecision(reused=True, metadata=metadata, reason=None)

    @staticmethod
    def inspection_to_dict(inspection: MetadataInspection) -> Dict[str, Any]:
        return {
            "db_path": str(inspection.db_path),
            "status": inspection.status,
            "reason": inspection.reason,
            "metadata": asdict(inspection.metadata) if inspection.metadata is not None else None,
        }

    def _metadata_from_row(self, row: Dict[str, Any]) -> ImportMetadata:
        return metadata_from_mapping(row)

    @staticmethod
    def _validate_metadata(
        metadata: ImportMetadata,
        *,
        allow_unsupported_version: bool,
    ) -> None:
        if not allow_unsupported_version and metadata.metadata_schema_version != METADATA_SCHEMA_VERSION:
            raise ValueError("Unsupported metadata schema version")
        validate_import_metadata(metadata)

    @staticmethod
    def _required_int(value: Any) -> int:
        if isinstance(value, bool) or not isinstance(value, int):
            raise TypeError("Expected integer metadata value")
        return value

    @staticmethod
    def _optional_int(value: Any) -> Union[int, None]:
        if value is None:
            return None
        return ImportMetadataService._required_int(value)

    @staticmethod
    def _required_str(value: Any) -> str:
        if not isinstance(value, str) or not value:
            raise TypeError("Expected non-empty metadata string")
        return value
