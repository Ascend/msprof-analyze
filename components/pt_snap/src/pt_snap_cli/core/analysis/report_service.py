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

from pathlib import Path
from typing import Dict, Union, cast

from typing_extensions import Literal

from pt_snap_cli.core.analysis.focus_service import FocusService
from pt_snap_cli.core.analysis.query_service import QueryService, _ResolvedQuery
from pt_snap_cli.core.common.models import PeakMemoryReport, QueryResult
from pt_snap_cli.core.common.query_limits import QueryLimits
from pt_snap_cli.core.dataset.dataset_sources import QueryBudget

PeakMetric = Literal["active", "allocated", "reserved"]

_EVENT_ID_BY_METRIC = {
    "active": "peak_active_event_id",
    "allocated": "peak_allocated_event_id",
    "reserved": "peak_reserved_event_id",
}

_PEAK_FIELDS = (
    "peak_allocated",
    "peak_allocated_event_id",
    "peak_active",
    "peak_active_event_id",
    "peak_reserved",
    "peak_reserved_event_id",
)

_ACTIVE_COUNTER_BY_METRIC = {
    "active": "peak_active",
    "allocated": "active_at_allocated_peak",
    "reserved": "active_at_reserved_peak",
}


class ReportService:
    def __init__(
        self,
        focus_service: Union[FocusService, None] = None,
        *,
        query_limits: Union[QueryLimits, None] = None,
    ) -> None:
        self._focus_service = focus_service or FocusService()
        self._query_service = QueryService(self._focus_service, query_limits=query_limits)

    def close(self) -> None:
        """Release connections owned by this report service; allow later reuse."""
        self._query_service.close()

    def memory_tree_report(
        self,
        event_id: int,
        db_path: Union[Union[Path, str], None] = None,
        device_id: Union[int, None] = None,
        include_static: bool = True,
        min_size: int = 0,
        *,
        start_dir: Union[Path, None] = None,
        timeout_s: Union[float, None] = None,
        query_limits: Union[QueryLimits, None] = None,
    ) -> QueryResult:
        """Return standalone or dataset frame occupancy through the shared query."""
        return self._query_service.execute_query(
            "active_memory_frame_tree_at_event",
            params={"event_id": event_id, "include_static": include_static, "min_size": min_size},
            db_path=db_path,
            device_id=device_id,
            start_dir=start_dir,
            timeout_s=timeout_s,
            query_limits=query_limits,
        )

    def event_attribution(
        self,
        event_id: int,
        db_path: Union[Union[Path, str], None] = None,
        device_id: Union[int, None] = None,
        *,
        include_static: bool = True,
        limit: int = 20,
        stack_bytes: int = -1,
        start_dir: Union[Path, None] = None,
        timeout_s: Union[float, None] = None,
        query_limits: Union[QueryLimits, None] = None,
        _budget: Union[QueryBudget, None] = None,
        _resolved: Union[_ResolvedQuery, None] = None,
    ) -> QueryResult:
        """Reuse core point-event attribution, also for externally selected peaks.

        Dataset-global peak selection is a separate contract; this method does
        not silently choose a local shard peak or invent an event for empty data.
        """
        return self._query_service.execute_query(
            "active_memory_callstack_at_event",
            params={
                "event_id": event_id,
                "include_static": include_static,
                "min_size": 0,
                "top_n": limit,
                "stack_bytes": stack_bytes,
            },
            db_path=db_path,
            device_id=device_id,
            start_dir=start_dir,
            timeout_s=timeout_s,
            query_limits=query_limits,
            _budget=_budget,
            _resolved=_resolved,
        )

    def peak_memory_report(
        self,
        db_path: Union[Union[Path, str], None] = None,
        device_id: Union[int, None] = None,
        metric: PeakMetric = "active",
        include_static: bool = True,
        limit: int = 20,
        start_dir: Union[Path, None] = None,
        stack_bytes: int = -1,
        *,
        start_id: Union[int, None] = None,
        end_id: Union[int, None] = None,
        timeout_s: Union[float, None] = None,
        query_limits: Union[QueryLimits, None] = None,
    ) -> PeakMemoryReport:
        if metric not in _EVENT_ID_BY_METRIC:
            raise ValueError(f"Invalid metric '{metric}'. Must be one of: active, allocated, reserved")

        budget = self._query_service._new_budget(timeout_s, query_limits)
        resolution = self._query_service._resolve_query(db_path, device_id, start_dir, budget)
        range_params = {"start_id": start_id, "end_id": end_id}
        gap_result = self._query_service.execute_query(
            "allocator_gap",
            params=range_params,
            _budget=budget,
            _resolved=resolution,
            db_path=db_path,
            device_id=device_id,
            start_dir=start_dir,
        )
        gap = gap_result.rows[0] if gap_result.rows else None
        # allocator_gap selects the same independent, earliest-tie peak events
        # for non-NULL counters. Preserve memory_peak's six-field contract,
        # including NULL event IDs when a standalone counter is entirely NULL.
        peak = {field: gap.get(field) for field in _PEAK_FIELDS} if gap else {}
        for peak_metric, event_field in _EVENT_ID_BY_METRIC.items():
            if peak and peak[f"peak_{peak_metric}"] is None:
                peak[event_field] = None
        # No attribution event exists for an empty trace or a NULL peak.
        event_id = cast(Union[int, None], peak.get(_EVENT_ID_BY_METRIC[metric]))
        attribution_params: Dict[str, object] = {
            "event_id": event_id,
            "include_static": include_static,
            "min_size": 0,
            "top_n": limit,
            **({"stack_bytes": stack_bytes} if stack_bytes >= 0 else {}),
        }

        if event_id is None:
            return PeakMemoryReport(
                device_id=gap_result.device_id,
                metric=metric,
                event_id=None,
                peak=peak,
                allocator_gap=None,
                callstack_groups=[],
                total_is_exact=True,
                effective_params=attribution_params,
                scope=gap_result.scope,
                timeout_s=budget.timeout_s,
            )

        callstack_result = self.event_attribution(
            event_id,
            db_path,
            device_id,
            include_static=include_static,
            limit=limit,
            stack_bytes=stack_bytes,
            start_dir=start_dir,
            _budget=budget,
            _resolved=resolution,
        )
        # allocator_gap supplies the active counter at this metric's event,
        # not the independently occurring active high-water value.
        active_bytes = cast(Union[int, None], (gap or {}).get(_ACTIVE_COUNTER_BY_METRIC[metric]))
        # No caller-side max_rows cap: these are all rows in the SQL percentage
        # denominator, including static/preexisting groups outside top_n.
        included_bytes = sum(cast(int, row["size_bytes"]) for row in callstack_result.rows)
        coverage = included_bytes * 100.0 / active_bytes if active_bytes is not None and active_bytes > 0 else None

        budget.remaining()
        return PeakMemoryReport(
            device_id=gap_result.device_id,
            metric=metric,
            event_id=event_id,
            peak=peak,
            allocator_gap=gap,
            callstack_groups=callstack_result.rows,
            has_more=callstack_result.has_more,
            truncated=callstack_result.truncated,
            total_is_exact=callstack_result.total_is_exact,
            effective_params=attribution_params,
            included_bytes=included_bytes,
            active_bytes_at_event=active_bytes,
            coverage_percent=coverage,
            scope=gap_result.scope,
            timeout_s=budget.timeout_s,
            source_coverage=cast(
                Union[Dict[str, object], None],
                (callstack_result.scope or {}).get("source_coverage"),
            ),
        )
