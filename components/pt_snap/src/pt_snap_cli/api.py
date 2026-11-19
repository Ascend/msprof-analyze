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

"""High-level API for PyTorch memory snapshot analysis."""

# Keep dynamic values explicit at this public boundary; do not reintroduce Any.
# pyright: reportAny=error, reportExplicitAny=error, reportUnknownArgumentType=error, reportUnknownVariableType=error, reportUnknownMemberType=error

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from types import TracebackType
from typing import Dict, List, Type, Union

from typing_extensions import TypedDict

from pt_snap_cli.config import Config
from pt_snap_cli.core import (
    CapabilityService,
    DatabaseMissingError,
    DatabaseSchemaError,
    FocusFileInvalidError,
    FocusNotConfiguredError,
    FocusService,
    ImportMetadataService,
    OverviewService,
    QueryService,
    TemplateNotFoundError,
)
from pt_snap_cli.core.cache.context_cache import ContextCache
from pt_snap_cli.core.common.query_limits import QueryLimits


class TemplateSummaryPayload(TypedDict):
    name: str
    description: str
    category: Union[str, None]


class _QueryScopePayload(TypedDict, total=False):
    scope: Dict[str, object]


class QueryResultPayload(_QueryScopePayload):
    total: int
    returned: int
    device_id: Union[int, None]
    rows: List[Dict[str, object]]
    template: Union[str, None]
    semantics_version: Union[int, None]
    has_more: bool
    truncated: bool
    total_is_exact: bool
    timeout_s: Union[float, None]


@dataclass
class FocusState:
    """Current focus state of the analyzer."""

    db_path: Union[str, None]
    device_id: Union[int, None]
    source: str
    available_devices: List[int]
    callstack_layout: Union[str, None] = None
    callstack_layout_error: Union[str, None] = None


class SnapshotAnalyzer:
    """Programmatic API for analyzing PyTorch memory snapshots."""

    def __init__(
        self,
        db_path: Union[Path, None] = None,
        device_id: Union[int, None] = None,
        *,
        context_cache: Union[ContextCache, None] = None,
        query_limits: Union[QueryLimits, None] = None,
    ) -> None:
        self._config: Config = Config()
        self._db_path: Union[Path, None] = db_path
        self._device_id: Union[int, None] = device_id
        self._focus_service: FocusService = FocusService(self._config)
        # Share one context cache across the analyzer so that long-lived
        # SnapshotAnalyzer instances reuse a single
        # SQLite connection and skip schema validation on every query.
        # Explicit ``is not None`` because an empty cache is falsy via
        # ``__len__`` and would be silently replaced otherwise.
        self._context_cache: ContextCache = context_cache if context_cache is not None else ContextCache()
        self._owns_context_cache: bool = context_cache is None
        self._closed: bool = False
        self._query_service: QueryService = QueryService(
            self._focus_service, context_cache=self._context_cache, query_limits=query_limits
        )
        self._metadata_service: ImportMetadataService = ImportMetadataService()
        self._capability_service: CapabilityService = CapabilityService(
            query_service=self._query_service,
        )
        self._overview_service: OverviewService = OverviewService(
            self._focus_service,
            metadata_service=self._metadata_service,
            context_cache=self._context_cache,
        )

    def close(self) -> None:
        """End this analyzer's lifetime, closing only its internally owned cache.

        Safe to call repeatedly. An injected cache remains the caller's
        responsibility and can still be used by other analyzers.
        """
        if self._closed:
            return
        self._closed = True
        self._query_service.close()
        if self._owns_context_cache:
            self._context_cache.close()

    def __enter__(self) -> SnapshotAnalyzer:
        self._ensure_open()
        return self

    def __exit__(
        self,
        exc_type: Union[Type[BaseException], None],
        exc_value: Union[BaseException, None],
        traceback: Union[TracebackType, None],
    ) -> None:
        self.close()

    def _ensure_open(self) -> None:
        if self._closed:
            raise RuntimeError("SnapshotAnalyzer is closed.")

    @property
    def context_cache(self) -> ContextCache:
        """Return the :class:`ContextCache` this analyzer uses."""
        return self._context_cache

    def invalidate_context_cache(self, db_path: Union[Union[Path, str], None] = None) -> None:
        """Drop cached contexts, including from an explicitly shared cache.

        This cleanup operation remains available after close(). While open,
        the analyzer can create fresh contexts on its next query or overview.
        """
        self._query_service.invalidate_context_cache(db_path)

    def get_focus(self) -> FocusState:
        self._ensure_open()
        state = self._focus_service.get_focus(
            explicit_db_path=self._db_path,
            explicit_device_id=self._device_id,
        )
        return FocusState(
            db_path=str(state.db_path) if state.db_path is not None else None,
            device_id=self._device_id if self._device_id is not None else state.device_id,
            source=state.source,
            available_devices=state.available_devices,
            callstack_layout=state.callstack_layout,
            callstack_layout_error=state.callstack_layout_error,
        )

    def set_focus(self, db_path: Union[str, None] = None, device_id: Union[int, None] = None) -> FocusState:
        self._ensure_open()
        if db_path is None and device_id is None:
            return self.get_focus()
        candidate_db = Path(db_path) if db_path is not None else self._db_path
        candidate_device = device_id if db_path is not None or device_id is not None else self._device_id
        if candidate_db is None and candidate_device is not None:
            resolved = self._focus_service.resolve_focus()
            if resolved.db_path is None:
                raise RuntimeError("No database configured. Set db_path before selecting a device.")
            candidate_db = resolved.db_path

        if candidate_db is not None:
            try:
                _ = self._focus_service.validate_session_db(candidate_db, candidate_device)
            except DatabaseMissingError as exc:
                raise FileNotFoundError(str(exc)) from exc
            except DatabaseSchemaError as exc:
                raise ValueError(str(exc)) from exc

        if db_path is not None:
            self._db_path = Path(db_path)
            self._device_id = device_id
        elif device_id is not None:
            self._device_id = device_id
        return self.get_focus()

    def list_templates(self, category: Union[str, None] = None) -> List[TemplateSummaryPayload]:
        self._ensure_open()
        return [
            {
                "name": template.name,
                "description": template.description,
                "category": template.category,
            }
            for template in self._query_service.list_templates(category)
        ]

    def get_template_info(
        self, name: str, *, query_limits: Union[QueryLimits, None] = None
    ) -> Union[Dict[str, object], None]:
        self._ensure_open()
        try:
            info = self._query_service.get_template_info(name, query_limits=query_limits)
        except TemplateNotFoundError:
            return None

        return self._query_service.template_info_to_dict(info)

    def execute_query(
        self,
        template: str,
        params: Union[Dict[str, object], None] = None,
        device_id: Union[int, None] = None,
        max_rows: Union[int, None] = None,
        *,
        exact_total: bool = False,
        timeout_s: Union[float, None] = None,
        slice_index: Union[int, None] = None,
        query_limits: Union[QueryLimits, None] = None,
    ) -> QueryResultPayload:
        self._ensure_open()
        try:
            result = self._query_service.execute_query(
                template=template,
                params=params,
                db_path=self._db_path,
                device_id=device_id if device_id is not None else self._device_id,
                max_rows=max_rows,
                exact_total=exact_total,
                timeout_s=timeout_s,
                slice_index=slice_index,
                query_limits=query_limits,
            )
        except FocusNotConfiguredError as exc:
            raise RuntimeError("No database configured. Call set_focus() first.") from exc
        payload: QueryResultPayload = {
            "total": result.total,
            "returned": result.returned,
            "device_id": result.device_id,
            "rows": result.rows,
            "template": result.template,
            "semantics_version": result.semantics_version,
            "has_more": result.has_more,
            "truncated": result.truncated,
            "total_is_exact": result.total_is_exact,
            "timeout_s": result.timeout_s,
        }
        if result.scope is not None:
            payload["scope"] = result.scope
        return payload

    def list_capabilities(self) -> Dict[str, object]:
        self._ensure_open()
        return self._capability_service.catalog_to_dict(self._capability_service.catalog())

    def get_database_overview(self, db_path: Union[str, None] = None) -> Dict[str, object]:
        self._ensure_open()
        resolved_path = db_path if db_path is not None else self._db_path
        try:
            overview = self._overview_service.inspect(resolved_path)
        except FocusNotConfiguredError as exc:
            raise RuntimeError("No database configured. Call set_focus() first.") from exc
        except FocusFileInvalidError as exc:
            raise ValueError(str(exc)) from exc
        except DatabaseMissingError as exc:
            raise FileNotFoundError(str(exc)) from exc
        except DatabaseSchemaError as exc:
            raise ValueError(str(exc)) from exc
        return self._overview_service.overview_to_dict(overview)

    def get_database_metadata(self, db_path: Union[str, None] = None) -> Dict[str, object]:
        self._ensure_open()
        resolved = self._focus_service.resolve_focus(
            explicit_db_path=db_path if db_path is not None else self._db_path,
            explicit_device_id=self._device_id,
        )
        if resolved.db_path is None:
            raise RuntimeError("No database configured. Call set_focus() first.")
        try:
            inspection = self._metadata_service.inspect(resolved.db_path)
        except DatabaseMissingError as exc:
            raise FileNotFoundError(str(exc)) from exc
        except DatabaseSchemaError as exc:
            raise ValueError(str(exc)) from exc
        return self._metadata_service.inspection_to_dict(inspection)
