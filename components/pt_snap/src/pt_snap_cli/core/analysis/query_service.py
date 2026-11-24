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

import copy
import os
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Union

from pt_snap_cli.context import Context, DatabaseNotFoundError, SchemaVersionError
from pt_snap_cli.core.analysis.focus_service import FocusService
from pt_snap_cli.core.cache.context_cache import ContextCache
from pt_snap_cli.core.common.errors import (
    DatabaseMissingError,
    DatabaseSchemaError,
    FocusNotConfiguredError,
    InvalidCategoryError,
    InvalidDeviceError,
    InvalidParameterError,
    QueryExecutionError,
    QueryTimeoutError,
    TemplateNotFoundError,
    TemplateRenderError,
)
from pt_snap_cli.core.common.latest_query import LatestQuery
from pt_snap_cli.core.common.models import (
    QueryResult,
    ResolvedFocus,
    TemplateInfo,
    TemplateParameter,
    TemplateSummary,
)
from pt_snap_cli.core.common.query_limits import QueryLimits, resolve_query_limits
from pt_snap_cli.core.common.stack_summary import summarize_stacks
from pt_snap_cli.core.dataset.dataset_contract import QueryScope
from pt_snap_cli.core.dataset.dataset_resolver import DatasetResolver, ResolvedDataset
from pt_snap_cli.core.dataset.dataset_sources import DatasetSourceResolver, QueryBudget
from pt_snap_cli.core.dataset.dataset_support import dataset_support
from pt_snap_cli.core.dataset.query.dataset_attribution import (
    event_attribution,
    summarize_dataset_stacks,
)
from pt_snap_cli.core.dataset.query.dataset_frame_tree import frame_tree
from pt_snap_cli.core.dataset.query.dataset_global import global_query
from pt_snap_cli.query.executor import QueryExecutionError as ExecutorQueryExecutionError
from pt_snap_cli.query.executor import QueryExecutor, cancellation_options
from pt_snap_cli.query.executor import QueryTimeoutError as ExecutorQueryTimeoutError
from pt_snap_cli.query.executor import TemplateRenderError as ExecutorTemplateRenderError
from pt_snap_cli.query.registry import (
    discover_categories,
    get_query,
    get_template_info,
    is_packaged_query,
    list_by_category_with_details,
    list_queries_with_details,
)

QUERY_TIMEOUT_ENV = "PT_SNAP_QUERY_TIMEOUT"


def resolve_query_timeout(explicit: Union[float, None]) -> Union[float, None]:
    """Return a positive timeout in seconds, or ``None`` when unbounded.

    An explicit argument wins. ``<= 0`` disables the timeout. Otherwise
    ``PT_SNAP_QUERY_TIMEOUT`` is read. Row limits (``max_rows`` / ``LIMIT``)
    are not a substitute for this value.
    """
    if explicit is not None:
        if isinstance(explicit, bool):
            raise InvalidParameterError("Query timeout must be a number of seconds")
        return float(explicit) if explicit > 0 else None
    raw = os.environ.get(QUERY_TIMEOUT_ENV)
    if raw is None or raw.strip() == "":
        return None
    try:
        value = float(raw)
    except ValueError as exc:
        raise InvalidParameterError(f"{QUERY_TIMEOUT_ENV} must be a number of seconds, got {raw!r}") from exc
    return value if value > 0 else None


@dataclass(frozen=True)
class _ResolvedQuery:
    """One composition's focus and inspected generation, shared by every step."""

    focus: ResolvedFocus
    dataset: Union[ResolvedDataset, None]
    explicit_device_id: Union[int, None]


class QueryService:
    def __init__(
        self,
        focus_service: Union[FocusService, None] = None,
        *,
        context_cache: Union[ContextCache, None] = None,
        query_limits: Union[QueryLimits, None] = None,
    ) -> None:
        if query_limits is not None:
            _ = resolve_query_limits(query_limits)
        self._query_limits: Union[QueryLimits, None] = query_limits
        self._focus_service = focus_service or FocusService()
        # Cache Context instances across calls so long-lived SnapshotAnalyzer
        # owners skip the per-call schema validation and
        # SQLite connect/close handshake. See ContextCache for the LRU and
        # mtime invalidation semantics.
        self._context_cache = context_cache if context_cache is not None else ContextCache()
        self._owns_context_cache: bool = context_cache is None
        self._executor: Union[QueryExecutor, None] = None
        self._executor_context: Union[Context, None] = None
        self._executor_source: Union[QueryExecutor, None] = None
        self._frame_tree_queries = LatestQuery()

    @property
    def context_cache(self) -> ContextCache:
        """Return the :class:`ContextCache` backing this service."""
        return self._context_cache

    def close(self) -> None:
        """Release owned connections and executor references; allow later reuse.

        An injected cache is borrowed and must be closed by its owner.
        """
        self._frame_tree_queries.cancel()
        self._executor = None
        self._executor_context = None
        self._executor_source = None
        if self._owns_context_cache:
            self._context_cache.close()

    def invalidate_context_cache(self, db_path: Union[Union[Path, str], None] = None) -> None:
        """Drop a cached context (or all of them when ``db_path`` is None)."""
        self._frame_tree_queries.cancel()
        self._context_cache.invalidate(db_path)

    def list_templates(
        self,
        category: Union[str, None] = None,
        validate_category: bool = True,
    ) -> List[TemplateSummary]:
        if category is not None and validate_category:
            categories = discover_categories()
            if category not in categories:
                raise InvalidCategoryError(f"Invalid category '{category}'. Must be one of: {', '.join(categories)}")

        template_rows = list_by_category_with_details(category) if category is not None else list_queries_with_details()
        summaries: List[TemplateSummary] = []
        for row in template_rows:
            template = get_query(row["name"])
            summaries.append(
                TemplateSummary(
                    name=row["name"],
                    description=row["description"],
                    category=template.category if template is not None else category,
                )
            )
        return summaries

    def get_template_info(self, name: str, *, query_limits: Union[QueryLimits, None] = None) -> TemplateInfo:
        template = get_query(name)
        if template is None:
            raise TemplateNotFoundError(f"Template '{name}' not found")

        info = get_template_info(name)
        if info is None:
            raise TemplateNotFoundError(f"Template '{name}' not found")

        devices = info["devices"]
        if isinstance(devices, list):
            devices = ", ".join(str(item) for item in devices)

        return TemplateInfo(
            name=info["name"],
            description=info["description"],
            category=template.category,
            devices=devices,
            parameters={
                param_name: TemplateParameter(
                    type=param_details["type"],
                    default=param_details["default"],
                    required=param_details["required"],
                    description=param_details["description"],
                    choices=param_details.get("choices"),
                )
                for param_name, param_details in info["parameters"].items()
            },
            output_schema=copy.deepcopy(info["output_schema"]),
            dataset_support=dataset_support(
                name,
                is_packaged_query(name)
                and not (self._executor is not None and self._executor.has_runtime_template(name)),
                self.resolve_limits(query_limits),
            ),
            semantics_version=info.get("semantics_version"),
            interpretation_limits=(
                [str(item) for item in info["interpretation_limits"]]
                if isinstance(info.get("interpretation_limits"), list)
                else []
            ),
        )

    def list_template_contracts(self, category: Union[str, None] = None) -> List[TemplateInfo]:
        """Return full template contracts, matching ``get_template_info`` per name."""
        return [self.get_template_info(item.name) for item in self.list_templates(category)]

    @staticmethod
    def template_info_to_dict(info: TemplateInfo) -> Dict[str, Any]:
        """Serialize a template contract for CLI/API JSON adapters."""
        return {
            "name": info.name,
            "description": info.description,
            "category": info.category,
            "devices": info.devices,
            "parameters": {
                param_name: {
                    "type": param.type,
                    "default": param.default,
                    "required": param.required,
                    "description": param.description,
                    "choices": param.choices,
                }
                for param_name, param in info.parameters.items()
            },
            "output_schema": info.output_schema,
            "semantics_version": info.semantics_version,
            "interpretation_limits": list(info.interpretation_limits),
            "dataset_support": dict(info.dataset_support),
        }

    def execute_query(
        self,
        template: str,
        params: Union[Dict[str, Any], None] = None,
        db_path: Union[Union[Path, str], None] = None,
        device_id: Union[int, None] = None,
        start_dir: Union[Path, None] = None,
        max_rows: Union[int, None] = None,
        *,
        exact_total: bool = False,
        timeout_s: Union[float, None] = None,
        slice_index: Union[int, None] = None,
        query_limits: Union[QueryLimits, None] = None,
        _budget: Union[QueryBudget, None] = None,
        _resolved: Union[_ResolvedQuery, None] = None,
    ) -> QueryResult:
        """Frame-tree calls on this service supersede unfinished frame-tree calls.

        Separate service instances do not cancel one another. Other templates
        retain their existing ownership/concurrency contract.
        """
        if template != "active_memory_frame_tree_at_event":
            return self._execute_query(
                template,
                params,
                db_path,
                device_id,
                start_dir,
                max_rows,
                exact_total=exact_total,
                timeout_s=timeout_s,
                slice_index=slice_index,
                query_limits=query_limits,
                _budget=_budget,
                _resolved=_resolved,
            )
        budget = _budget if _budget is not None else self._new_budget(timeout_s, query_limits)
        with self._frame_tree_queries.run(budget.remaining) as cancelled:
            previous = budget.cancelled
            budget.cancelled = lambda: cancelled() or (previous is not None and previous())
            # Each task opens and closes its handles in its executing thread.
            # The borrowed/standalone cache must never move between click workers.
            worker = QueryService(self._focus_service, query_limits=self._query_limits)
            # Retain override detection and custom templates, never the source connection.
            worker._executor = self._executor
            worker._executor_source = self._executor
            try:
                result = worker._execute_query(
                    template,
                    params,
                    db_path,
                    device_id,
                    start_dir,
                    max_rows,
                    exact_total=exact_total,
                    timeout_s=timeout_s,
                    slice_index=slice_index,
                    query_limits=query_limits,
                    _budget=budget,
                    _resolved=_resolved,
                )
                budget.remaining()
                return result
            finally:
                try:
                    worker.close()
                finally:
                    budget.cancelled = previous

    def _execute_query(
        self,
        template: str,
        params: Union[Dict[str, Any], None] = None,
        db_path: Union[Union[Path, str], None] = None,
        device_id: Union[int, None] = None,
        start_dir: Union[Path, None] = None,
        max_rows: Union[int, None] = None,
        *,
        exact_total: bool = False,
        timeout_s: Union[float, None] = None,
        slice_index: Union[int, None] = None,
        query_limits: Union[QueryLimits, None] = None,
        _budget: Union[QueryBudget, None] = None,
        _resolved: Union[_ResolvedQuery, None] = None,
    ) -> QueryResult:
        budget = _budget if _budget is not None else self._new_budget(timeout_s, query_limits)
        timeout_s, started = budget.timeout_s, budget.started
        budget.remaining()
        resolution = _resolved or self._resolve_query(db_path, device_id, start_dir, budget)
        resolved, dataset = resolution.focus, resolution.dataset
        assert resolved.db_path is not None  # nosec B101 # Internal invariant after validation; not an input security check.
        budget.remaining()
        scope: Union[Dict[str, object], None] = None
        query_params = params or {}
        sources: Union[DatasetSourceResolver, None] = None
        if dataset is not None:
            selected = dataset.device(
                resolution.explicit_device_id if resolution.explicit_device_id is not None else resolved.device_id
            )
            sources = DatasetSourceResolver(dataset, selected.device_id, self._context_cache, budget)
            template_obj = get_query(template)
            if template_obj is None:
                raise TemplateNotFoundError(f"Template '{template}' not found")
            support = dataset_support(template, is_packaged_query(template))
            overridden = self._executor is not None and self._executor.has_runtime_template(template)
            if not support["supported"] or overridden:
                raise QueryExecutionError(
                    "Unsupported dataset-global template/custom SQL or runtime override; "
                    "select an explicit standalone member. A built-in name is not a merge contract."
                )
            for name in ("id", "min_id", "max_id", "start_id", "end_id", "event_id"):
                if isinstance(query_params.get(name), bool):
                    raise InvalidParameterError("Event/block endpoints must not be booleans.")
            try:
                validated = template_obj.validate_params(query_params)
            except (TypeError, ValueError) as exc:
                raise TemplateRenderError(str(exc)) from exc
            if slice_index is not None:
                dataset.paths(QueryScope("slice", selected.device_id, slice_index))
            implementation = (
                frame_tree
                if template == "active_memory_frame_tree_at_event"
                else (
                    event_attribution
                    if template in ("active_blocks_at_event", "active_memory_callstack_at_event")
                    else global_query
                )
            )
            result = implementation(
                sources,
                template,
                validated,
                max_rows,
                exact_total,
                slice_index,
                template_obj.semantics_version,
            )
            stack_bytes = validated.get("stack_bytes")
            if isinstance(stack_bytes, int) and stack_bytes >= 0:
                summarize_dataset_stacks(result.rows, stack_bytes)
            budget.remaining()
            # Inspection establishes the baseline for standalone queries and
            # composed reports alike. Reject mixed-generation rows or counts
            # before either adapter can publish any part of the result.
            dataset.require_unchanged(budget)
            if result.scope is not None:
                result.scope["work_budget"] = budget.describe()
            return result
        else:
            if slice_index is not None:
                raise InvalidParameterError("slice_index requires a manifest dataset.")
            ctx = self._validated_context(resolved.db_path)
            target_device = self._resolve_device_id(ctx, resolved.device_id, resolution.explicit_device_id)
        executor = self._get_executor(ctx)

        try:
            rows, has_more, _applied_limit = executor.execute_template_page(
                template,
                query_params,
                device_id=target_device,
                max_rows=max_rows,
                timeout_s=budget.remaining(),
                **cancellation_options(budget.cancelled),
            )
            offset = _validated_offset(template, query_params)
            rank_cap = _finite_top_n(template, query_params)
            if rank_cap is not None and _inner_rank_window_full(rows, rank_cap):
                has_more = True
            returned = len(rows)
            if exact_total:
                total = executor.count_template(
                    template,
                    query_params,
                    device_id=target_device,
                    timeout_s=_remaining_timeout(timeout_s, started),
                    ignore_row_window=True,
                    **cancellation_options(budget.cancelled),
                )
                total_is_exact = True
                if offset == 0:
                    has_more = total > returned
            else:
                total = returned
                total_is_exact = (not has_more) and offset == 0
            truncated = has_more or offset > 0 or (exact_total and total > returned)
        except ExecutorTemplateRenderError as exc:
            raise TemplateRenderError(str(exc)) from exc
        except ExecutorQueryTimeoutError as exc:
            budget.remaining()
            raise QueryTimeoutError(f"Query timed out after {timeout_s} seconds") from exc
        except ExecutorQueryExecutionError as exc:
            budget.remaining()
            if get_query(template) is None:
                raise TemplateNotFoundError(f"Template '{template}' not found") from exc
            raise QueryExecutionError(str(exc)) from exc

        template_obj = get_query(template)
        if template_obj is not None and "stack_bytes" in template_obj.parameters:
            stack_bytes = template_obj.validate_params(query_params)["stack_bytes"]
            if isinstance(stack_bytes, int) and stack_bytes >= 0:
                if sources is not None:
                    summarize_dataset_stacks(rows, stack_bytes)
                else:
                    summarize_stacks(rows, stack_bytes, ctx.callstack_layout)
        budget.remaining()
        return QueryResult(
            total=total,
            returned=returned,
            device_id=target_device,
            rows=rows,
            template=template,
            semantics_version=template_obj.semantics_version if template_obj is not None else None,
            has_more=has_more,
            truncated=truncated,
            total_is_exact=total_is_exact,
            timeout_s=timeout_s,
            scope=scope,
        )

    def resolve_limits(self, explicit: Union[QueryLimits, None] = None) -> QueryLimits:
        """Per-call limits override instance limits, then environment/defaults."""
        return resolve_query_limits(explicit if explicit is not None else self._query_limits)

    def _new_budget(
        self, timeout_s: Union[float, None] = None, query_limits: Union[QueryLimits, None] = None
    ) -> QueryBudget:
        """Create fresh counters and a deadline for one operation/composition."""
        return QueryBudget.from_limits(
            self.resolve_limits(query_limits), resolve_query_timeout(timeout_s), time.monotonic()
        )

    def _resolve_query(
        self,
        db_path: Union[Union[Path, str], None],
        device_id: Union[int, None],
        start_dir: Union[Path, None],
        budget: QueryBudget,
    ) -> _ResolvedQuery:
        budget.remaining()
        resolved = self._focus_service.resolve_focus(
            explicit_db_path=db_path,
            explicit_device_id=device_id,
            start_dir=start_dir,
        )
        if resolved.db_path is None:
            raise FocusNotConfiguredError("No database path specified and no database configured.")
        dataset = DatasetResolver().inspect(resolved.db_path, budget=budget)
        budget.remaining()
        return _ResolvedQuery(resolved, dataset, device_id)

    def _get_executor(self, ctx: Context) -> QueryExecutor:
        """Reuse the executor while its cached database context remains valid.

        Packaged templates are served by the registry, so the executor needs no
        template directory of its own.
        """
        if self._executor is None or self._executor_context is not ctx:
            self._executor = (
                self._executor_source.clone_for_context(ctx)
                if self._executor_source is not None
                else QueryExecutor(ctx)
            )
            self._executor_source = None
            self._executor_context = ctx
        return self._executor

    def _resolve_device_id(
        self,
        ctx: Context,
        focused_device_id: Union[int, None],
        explicit_device_id: Union[int, None],
    ) -> Union[int, None]:
        if explicit_device_id is not None:
            if explicit_device_id not in ctx.device_ids:
                raise InvalidDeviceError(f"Device {explicit_device_id} not found. Available: {ctx.device_ids}")
            return explicit_device_id

        if focused_device_id is not None:
            if focused_device_id not in ctx.device_ids:
                raise InvalidDeviceError(f"Device {focused_device_id} not found. Available: {ctx.device_ids}")
            return focused_device_id

        if not ctx.device_ids:
            raise InvalidDeviceError("No devices found in database.")
        return ctx.device_ids[0]

    def _validated_context(
        self, db_path: Path, *, generation: Union[str, None] = None, immutable: bool = False
    ) -> Context:
        try:
            if generation is not None:
                return self._context_cache.get(db_path, generation=generation, immutable=immutable)
            return self._context_cache.get(db_path)
        except DatabaseNotFoundError as exc:
            raise DatabaseMissingError(str(exc)) from exc
        except (SchemaVersionError, sqlite3.DatabaseError) as exc:
            raise DatabaseSchemaError(str(exc)) from exc


def _validated_offset(template: str, params: Dict[str, Any]) -> int:
    template_obj = get_query(template)
    if template_obj is None or "offset" not in template_obj.parameters:
        return 0
    try:
        validated = template_obj.validate_params(params)
    except (TypeError, ValueError):
        return 0
    raw = validated.get("offset")
    return raw if isinstance(raw, int) and raw > 0 else 0


def _finite_top_n(template: str, params: Dict[str, Any]) -> Union[int, None]:
    """Return a declared non-negative ``top_n``, or ``None`` when unbounded."""
    template_obj = get_query(template)
    if template_obj is None or "top_n" not in template_obj.parameters:
        return None
    try:
        validated = template_obj.validate_params(params)
    except (TypeError, ValueError):
        return None
    raw = validated.get("top_n")
    return raw if isinstance(raw, int) and raw >= 0 else None


def _inner_rank_window_full(rows: List[Dict[str, Any]], rank_cap: int) -> bool:
    """True when a finite ``top_n`` window is full and may have dropped rows.

    ``active_memory_callstack_at_event`` applies ``top_n`` only to dynamic
    groups. Other ``top_n`` templates treat every returned row as ranked.
    This is a cap-hit check, not an extra-row probe: an exact match of
    ``rank_cap`` is treated as possibly incomplete unless ``exact_total``
    later proves ``total == returned``.
    """
    # A zero-cap window can hide every ranked group. Empty output cannot
    # establish completeness until exact_total explicitly counts without it.
    if rank_cap == 0:
        return True
    if not rows:
        return False
    if any("category" in row for row in rows):
        ranked = sum(1 for row in rows if row.get("category") == "dynamic_live_at_event")
    else:
        ranked = len(rows)
    return ranked >= rank_cap


def _remaining_timeout(timeout_s: Union[float, None], started: float) -> Union[float, None]:
    """Return leftover seconds from a single QueryService call budget."""
    if timeout_s is None:
        return None
    left = timeout_s - (time.monotonic() - started)
    if left <= 0:
        raise QueryTimeoutError(f"Query timed out after {timeout_s} seconds")
    return left
