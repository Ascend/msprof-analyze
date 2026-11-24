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

"""Read-only SQL reduction for text-only point-event attribution.

Coverage is computed over the full active set before ranking or pagination. Only
aggregate rows and the requested page cross into Python and incur its fetched
row/value budget. SQLite scans and temporary sorting remain deadline bounded,
not an RSS/temporary-disk promise. Ordered-frame inputs retain the source path.
"""

from __future__ import annotations

import hashlib
from typing import Dict, List, Tuple, Union, cast

from pt_snap_cli.core.dataset.dataset_contract import SliceRecord
from pt_snap_cli.core.dataset.dataset_sources import DatasetSourceResolver
from pt_snap_cli.core.dataset.lifecycle.dataset_lifecycle_connection import _AttachedSources
from pt_snap_cli.core.dataset.lifecycle.dataset_lifecycle_sql import (
    _attachment_limit,
    _proof,
    _required_slices,
)


def _active_cte(
    sources: DatasetSourceResolver,
    item: SliceRecord,
    required: List[SliceRecord],
    include_static: bool,
) -> str:
    device = sources.device.device_id
    text_cases = []
    for owner in required:
        table = f'"s{owner.index}"."trace_entry_{device}"'
        join = (
            f' LEFT JOIN "s{owner.index}".callstack cs ON cs.id=e.callstackId'
            if sources.dataset.callstack_layout == "v2"
            else ""
        )
        text = "cs.callstack" if join else "e.callstack"
        text_cases.append(
            f"WHEN b.allocEventId BETWEEN {owner.start_event_id} AND {owner.end_event_id} "
            f"THEN (SELECT {text} FROM {table} e{join} "
            "WHERE e.id=b.allocEventId AND e.id>=0 AND e.action=4)"  # nosec B608 # SQL structure uses validated integer IDs and fixed/allowlisted schema fragments; values are bound.
        )
    return f"""WITH active AS (
        SELECT * FROM "s{item.index}"."block_{device}"
        WHERE size>=? AND (allocEventId=-1 OR allocEventId<=?)
            AND (freeEventId=-1 OR freeEventId>?)
            {'' if include_static else 'AND allocEventId!=-1'}
    ), attributed AS (
        SELECT b.*, {_proof(sources, required, 'allocEventId', 4)} AS allocation_proved,
            {_proof(sources, required, 'freeEventId', 6)} AS completion_proved,
            CASE {' '.join(text_cases)} END AS source_text
        FROM active b
    ), classified AS (
        SELECT *, CASE WHEN allocEventId>=0 THEN 'dynamic_live_at_event'
            WHEN freeEventId=-1 THEN 'static' ELSE 'preexisting_live_at_event' END AS category,
            CASE WHEN allocEventId>=0 THEN
                CASE WHEN typeof(source_text)='text' AND source_text!='' THEN 'captured'
                ELSE 'missing' END
            WHEN freeEventId=-1 THEN 'static' ELSE 'preexisting_live_at_event' END AS stack_kind
        FROM attributed
    ) """  # nosec B608 # SQL structure uses validated integer IDs and fixed/allowlisted schema fragments; values are bound.


def _group_cte(cte: str, top_n: int) -> str:
    return (
        cte
        + f""", labelled AS (
        SELECT *, CASE stack_kind
            WHEN 'captured' THEN source_text
            WHEN 'static' THEN '[static] allocEventId=-1, freeEventId=-1'
            WHEN 'preexisting_live_at_event' THEN '[preexisting live] allocEventId=-1'
            ELSE '[missing callstack]' END AS callstack
        FROM classified
    ), grouped AS (
        SELECT category, stack_kind, callstack, COUNT(*) AS block_count,
            SUM(size) AS size_bytes, SUM(requestedSize) AS requested_bytes,
            MIN(CASE WHEN stack_kind='captured' THEN allocEventId END) AS stack_event_id
        FROM labelled GROUP BY stack_kind, callstack
    ), ranked AS (
        SELECT *, ROW_NUMBER() OVER (PARTITION BY category ORDER BY
            size_bytes DESC, block_count DESC, callstack,
            stack_kind='captured') AS group_rank FROM grouped
    ), included AS (
        SELECT * FROM ranked WHERE category!='dynamic_live_at_event'
            OR {top_n}<0 OR group_rank<={top_n}
    ) """  # nosec B608 # SQL structure uses validated integer IDs and fixed/allowlisted schema fragments; values are bound.
    )


def reduce_active(
    sources: DatasetSourceResolver,
    item: SliceRecord,
    template: str,
    params: Dict[str, object],
    max_rows: Union[int, None],
) -> Union[Tuple[List[Dict[str, object]], Dict[str, object], int, bool, int], None]:
    """Return reduced output/full coverage, or preserve the budgeted fallback.

    Required proof owners include future completed frees. Local v2 stack IDs are
    used only to obtain their owning shard's full text, never as global identity.
    A frame extension, even partially covered, must use ordered-frame attribution.
    """
    if sources.dataset.ordered_frames_version in (1, 2):
        return None
    required = _required_slices(sources, [item], _attachment_limit())
    if required is None:
        return None
    cte = _active_cte(sources, item, required, bool(params["include_static"]))
    values = [params["min_size"], params["event_id"], params["event_id"]]
    cap = max_rows if max_rows is not None and max_rows > 0 else -1
    with _AttachedSources(sources, required) as database:
        # A valid block size is int64, but whole-set byte totals need not be.
        # Sum four 16-bit components in SQLite (bounded even at SQLite's maximum
        # physical table size), then reconstruct exact Python integers from the
        # single charged summary row. This keeps finite pages/top_n independent
        # of int64 SUM overflow in whole-set coverage totals. Group/denominator
        # sums retain their existing SQLite int64 overflow behavior.
        byte_fields = {
            "active_bytes": "size",
            "dynamic_bytes": "CASE WHEN allocEventId>=0 THEN size ELSE 0 END",
            "captured_dynamic_bytes": "CASE WHEN stack_kind='captured' THEN size ELSE 0 END",
        }
        byte_sums = ", ".join(
            f'COALESCE(SUM((({expression}) >> {16 * part}) & 65535),0) AS "{field}_{part}"'
            for field, expression in byte_fields.items()
            for part in range(4)
        )
        coverage = database.read(
            cte
            + f"""SELECT COUNT(*) AS active_blocks, {byte_sums},
                COALESCE(SUM(allocEventId>=0),0) AS dynamic_blocks,
                COALESCE(SUM(allocEventId>=0 AND allocation_proved),0) AS allocation_events_resolved,
                COALESCE(SUM(stack_kind='captured'),0) AS allocation_stacks_captured,
                COALESCE(SUM(allocEventId<0),0) AS unknown_preexisting_blocks,
                COALESCE(SUM(freeEventId>=0),0) AS free_references,
                COALESCE(SUM(completion_proved),0) AS free_events_resolved
                FROM classified""",  # nosec B608 # SQL structure uses validated integer IDs and fixed/allowlisted schema fragments; values are bound.
            values,
        )[0]
        for field in byte_fields:
            coverage[field] = sum(cast(int, coverage.pop(f"{field}_{part}")) << (16 * part) for part in range(4))
        coverage.update(
            range_complete=True,
            event_position="after",
            allocation_source_complete=(coverage["dynamic_blocks"] == coverage["allocation_events_resolved"]),
            ordered_frame_blocks=0,
            ordered_frames_complete=False,
            frame_degradation="text_only_or_uncovered",
        )
        if template == "active_blocks_at_event":
            limit = cast(int, params["limit"])
            if cap >= 0:
                limit = min(limit, cap) if limit >= 0 else cap
            offset = max(0, cast(int, params["offset"]))
            rows = database.read(
                cte + f'SELECT * FROM active ORDER BY "{params["order_by"]}" '
                f'{params["order_dir"]}, id ASC LIMIT ? OFFSET ?',  # nosec B608 # SQL structure uses validated integer IDs and fixed/allowlisted schema fragments; values are bound.
                [*values, limit, offset],
            )
            total, rank_full = cast(int, coverage["active_blocks"]), False
        else:
            top_n = cast(int, params["top_n"])
            grouped = _group_cte(cte, top_n)
            summary = database.read(
                grouped
                + """SELECT COUNT(*) AS total,
                    COALESCE(SUM(category='dynamic_live_at_event'),0) AS dynamic_groups
                    FROM grouped""",  # nosec B608 # SQL structure uses validated integer IDs and fixed/allowlisted schema fragments; values are bound.
                values,
            )[0]
            rows = database.read(
                grouped
                + """SELECT category, stack_kind, callstack, block_count,
                    size_bytes, requested_bytes, stack_event_id,
                    ROUND(size_bytes / 1073741824.0,6) AS size_gib,
                    ROUND(requested_bytes / 1073741824.0,6) AS requested_gib,
                    ROUND(size_bytes * 100.0 / NULLIF((SELECT SUM(size_bytes) FROM included),0),4)
                        AS percent_of_active_blocks
                    FROM included ORDER BY size_bytes DESC, block_count DESC, callstack,
                        stack_kind='captured' LIMIT ?""",  # nosec B608 # SQL structure uses validated integer IDs and fixed/allowlisted schema fragments; values are bound.
                [*values, cap],
            )
            for row in rows:
                sources.budget.remaining()
                kind = row["stack_kind"]
                identity = (
                    "text:sha256:" + hashlib.sha256(cast(str, row["callstack"]).encode("utf-8")).hexdigest()
                    if kind == "captured"
                    else f"category:{kind}"
                )
                row.update(
                    source_stack_id=f"{sources.namespace}:{identity}",
                    stack_id=f"{sources.namespace}:{identity}",
                    text_kind=kind,
                    frames=None,
                    frames_status="text_only",
                )
            total = cast(int, summary["total"])
            dynamic = cast(int, summary["dynamic_groups"])
            rank_full = 0 <= top_n <= dynamic
            offset = 0
    coverage["source_queries"] = sources.query_count
    return rows, coverage, total, rank_full, offset
