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

import sqlite3
from pathlib import Path
from typing import Any, Dict, Union

from pt_snap_cli.context import Context, DatabaseNotFoundError, SchemaVersionError
from pt_snap_cli.core.analysis.focus_service import FocusService
from pt_snap_cli.core.cache.context_cache import ContextCache
from pt_snap_cli.core.common.errors import (
    DatabaseMissingError,
    DatabaseSchemaError,
    FocusNotConfiguredError,
)
from pt_snap_cli.core.common.models import DatabaseOverview, DeviceTraceBounds
from pt_snap_cli.core.dataset.dataset_resolver import DatasetResolver
from pt_snap_cli.core.importing.import_metadata import ImportMetadataService


class OverviewService:
    """Read-only SnapshotDB orientation: devices, trace bounds, import metadata."""

    def __init__(
        self,
        focus_service: Union[FocusService, None] = None,
        metadata_service: Union[ImportMetadataService, None] = None,
        *,
        context_cache: Union[ContextCache, None] = None,
    ) -> None:
        self._focus_service = focus_service or FocusService()
        self._metadata_service = metadata_service or ImportMetadataService()
        self._context_cache = context_cache if context_cache is not None else ContextCache()
        self._owns_context_cache: bool = context_cache is None

    def close(self) -> None:
        """Release owned connections; borrowed caches and later reuse are unaffected."""
        if self._owns_context_cache:
            self._context_cache.close()

    def inspect(
        self,
        db_path: Union[Union[Path, str], None] = None,
        start_dir: Union[Path, None] = None,
    ) -> DatabaseOverview:
        resolved = self._focus_service.resolve_focus(
            explicit_db_path=db_path,
            start_dir=start_dir,
        )
        if resolved.db_path is None:
            raise FocusNotConfiguredError("No database path specified and no database configured.")

        dataset = DatasetResolver().inspect(resolved.db_path)
        db_path = resolved.db_path.expanduser().resolve()
        if dataset is not None:
            return DatabaseOverview(
                db_path=db_path,
                focus_source=resolved.source,
                devices=[
                    DeviceTraceBounds(
                        device.device_id,
                        device.slices[0].start_event_id,
                        device.slices[-1].end_event_id,
                    )
                    for device in sorted(dataset.validation.manifest.devices, key=lambda d: d.device_id)
                ],
                metadata=self._metadata_service.inspect(db_path),
                dataset=dataset.to_dict(),
            )
        ctx = self._validated_context(db_path)
        try:
            raw_bounds = ctx.device_trace_bounds()
        except (ValueError, sqlite3.DatabaseError) as exc:
            raise DatabaseSchemaError(str(exc)) from exc
        devices = [
            DeviceTraceBounds(
                device_id=device_id,
                first_event_id=first_event_id,
                last_event_id=last_event_id,
            )
            for device_id, first_event_id, last_event_id in raw_bounds
        ]
        return DatabaseOverview(
            db_path=db_path,
            focus_source=resolved.source,
            devices=devices,
            metadata=self._metadata_service.inspect(db_path),
        )

    def overview_to_dict(self, overview: DatabaseOverview) -> Dict[str, Any]:
        inspection = self._metadata_service.inspection_to_dict(overview.metadata)
        return {
            "db_path": str(overview.db_path),
            "focus_source": overview.focus_source,
            **({"dataset": overview.dataset} if overview.dataset is not None else {}),
            "devices": [
                {
                    "device_id": device.device_id,
                    "first_event_id": device.first_event_id,
                    "last_event_id": device.last_event_id,
                }
                for device in overview.devices
            ],
            "import_metadata": {
                "status": inspection["status"],
                "reason": inspection["reason"],
                "metadata": inspection["metadata"],
            },
        }

    def _validated_context(self, db_path: Path) -> Context:
        try:
            return self._context_cache.get(db_path)
        except DatabaseNotFoundError as exc:
            raise DatabaseMissingError(str(exc)) from exc
        except (SchemaVersionError, sqlite3.DatabaseError) as exc:
            raise DatabaseSchemaError(str(exc)) from exc
