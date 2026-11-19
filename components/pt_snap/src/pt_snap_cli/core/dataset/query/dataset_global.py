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

"""Exact built-in global reductions, with bounded fetched work.

Shard SQL reduces counters, groups, and candidate windows before Python merging.
Fetched work is cumulatively bounded by QueryBudget, including source hydration
and final output. Unlimited/high-cardinality results can still exhaust the budget;
a failure rejects the operation rather than returning an alleged global answer.
"""

from __future__ import annotations

import hashlib
from typing import Dict, List, Tuple, Union, cast

from pt_snap_cli.core.common.errors import InvalidParameterError, QueryExecutionError
from pt_snap_cli.core.common.models import QueryResult
from pt_snap_cli.core.dataset.dataset_contract import QueryScope, SliceRecord
from pt_snap_cli.core.dataset.dataset_sources import DatasetSourceResolver
from pt_snap_cli.core.dataset.lifecycle.dataset_lifecycle_sql import lifecycle_query

METRICS = ("allocated", "active", "reserved")


def _range(
    sources: DatasetSourceResolver, params: Dict[str, object], slice_index: Union[int, None]
) -> Tuple[int, int, List[SliceRecord]]:
    device = sources.device
    if slice_index is not None:
        sources.dataset.paths(QueryScope("slice", device.device_id, slice_index))
        members = [device.slices[slice_index]]
    else:
        members = list(device.slices)
    low, high = members[0].start_event_id, members[-1].end_event_id
    start = params.get("start_id", params.get("min_id"))
    end = params.get("end_id", params.get("max_id"))
    event = params.get("id")
    # `id` on block means block ID, so its caller does not pass it here.
    for endpoint in (start, end, event):
        # pylint: disable-next=unidiomatic-typecheck  # Reject bool/subclasses: the contract requires exact scalar types.
        if endpoint is not None and (type(endpoint) is not int or not low <= endpoint <= high):
            raise InvalidParameterError("Event range must lie within the selected real scope.")
    low = cast(int, start) if start is not None else low
    high = cast(int, end) if end is not None else high
    if event is not None:
        low, high = max(low, cast(int, event)), min(high, cast(int, event))
        # Contradictory filters remain an empty matching set, not a made-up event.
    elif low > high:
        raise InvalidParameterError("Event range start must not exceed end.")
    return low, high, [s for s in members if s.end_event_id >= low and s.start_event_id <= high]


def _scope(sources: DatasetSourceResolver, low: int, high: int, items: List[SliceRecord]) -> Dict[str, object]:
    return {
        "kind": "event_range",
        "device_id": sources.device.device_id,
        "slice_index": items[0].index if len(items) == 1 else None,
        "slice_indices": [s.index for s in items],
        "first_event_id": low,
        "last_event_id": high,
        "requested_range": {"first_event_id": low, "last_event_id": high},
        "dataset_path": str(sources.dataset.root),
        "fingerprint": sources.dataset.fingerprint,
        "boundary_events_included": False,
        "range_complete": True,
        "work_budget": {
            "max_rows": sources.budget.max_work_rows,
            "max_bytes": sources.budget.max_work_bytes,
            "unit": "cumulative_fetched_and_output_serialized_values; not_RSS",
        },
    }


def _range_statistics(sources, low, high, items, scope, predicate="1", values=None):
    """Range evidence is deliberately collected BEFORE non-range filters."""
    count = matching = 0
    matching_by_shard = {}
    first = last = None
    for item in items:
        row = sources.read(
            sources.dataset.root / item.file,
            f"SELECT MIN(id) AS first, MAX(id) AS last, COUNT(*) AS count, "
            f"COALESCE(SUM(CASE WHEN {predicate} THEN 1 ELSE 0 END), 0) AS matching "
            f'FROM "trace_entry_{sources.device.device_id}" '
            "WHERE id>=0 AND id>=? AND id<=?",  # nosec B608 # SQL structure uses validated integer IDs and fixed/allowlisted schema fragments; values are bound.
            [*(values or []), low, high],
        )[0]
        count += row["count"]
        matching += row["matching"]
        matching_by_shard[item.index] = row["matching"]
        if row["first"] is not None:
            first = row["first"] if first is None else min(first, row["first"])
            last = row["last"] if last is None else max(last, row["last"])
    scope["actual_range"] = {
        "first_event_id": first,
        "last_event_id": last,
        "real_event_count": count,
    }
    return matching, matching_by_shard


def _peaks(sources, low, high, items, template, scope):
    _range_statistics(sources, low, high, items, scope)
    chosen: Dict[str, Dict[str, object]] = {}
    # These index-friendly queries fetch at most three narrow rows per shard.
    # NULL counters never nominate an event, matching MAX + equality semantics.
    for item in items:
        for metric in METRICS:
            rows = sources.read(
                sources.dataset.root / item.file,
                f"SELECT id, allocated, active, reserved "
                f'FROM "trace_entry_{sources.device.device_id}" '
                f'WHERE id>=0 AND id>=? AND id<=? AND "{metric}" IS NOT NULL '
                f'ORDER BY "{metric}" DESC, id ASC LIMIT 1',  # nosec B608 # SQL structure uses validated integer IDs and fixed/allowlisted schema fragments; values are bound.
                [low, high],
            )
            if rows:
                row = rows[0]
                event = cast(int, row["id"])
                if metric not in chosen or (cast(int, row[metric]), -event) > (
                    cast(int, chosen[metric][metric]),
                    -cast(int, chosen[metric]["id"]),
                ):
                    chosen[metric] = row
    result: Dict[str, object] = {}
    for metric in METRICS:
        row = chosen.get(metric, {})
        result[f"peak_{metric}"] = row.get(metric)
        result[f"peak_{metric}_event_id"] = row.get("id")
        if template == "allocator_gap":
            for other in METRICS:
                if other != metric:
                    result[f"{other}_at_{metric}_peak"] = row.get(other)
            for other in ("active", "allocated"):
                result[f"reserved_{other}_gap_at_{metric}_peak"] = (
                    cast(int, row["reserved"]) - cast(int, row[other])
                    if row and row["reserved"] is not None and row[other] is not None
                    else None
                )
    if template == "allocator_gap":
        ids = [result[f"peak_{m}_event_id"] for m in METRICS]
        result["all_peaks_same_event"] = int(None not in ids and len(set(ids)) == 1)
        for a, b in (("allocated", "active"), ("active", "reserved"), ("allocated", "reserved")):
            result[f"{a}_{b}_same_event"] = int(
                result[f"peak_{a}_event_id"] is not None
                and result[f"peak_{a}_event_id"] == result[f"peak_{b}_event_id"]
            )
    scope["peak_owner_slices"] = {m: sources.owner(cast(int, r["id"])).index for m, r in chosen.items()}
    return [result]


def _predicates(params, fields, alias=""):
    clauses, values = [], []
    for field in fields:
        for prefix, operator in (("", "="), ("min_", ">="), ("max_", "<=")):
            value = params.get(prefix + field)
            if value is not None:
                clauses.append(f'{alias}"{field}" {operator} ?')
                values.append(value)
    return " AND ".join(clauses) or "1", values


def _window(params, max_rows):
    offset = max(0, cast(int, params.get("offset", 0)))
    limit = cast(int, params.get("limit", -1))
    if max_rows is not None and max_rows > 0:
        limit = min(limit, max_rows) if limit >= 0 else max_rows
    return offset, limit


def _matches(row: Dict[str, object], params: Dict[str, object], fields: Tuple[str, ...]) -> bool:
    for field in fields:
        value = params.get(field)
        if value is not None and row[field] != value:
            return False
        for prefix, predicate in (("min_", lambda a, b: a >= b), ("max_", lambda a, b: a <= b)):
            value = params.get(prefix + field)
            if value is not None and (row[field] is None or not predicate(row[field], value)):
                return False
    return True


def _sort(rows: List[Dict[str, object]], key: str, descending: bool) -> None:
    # SQLite NULL placement and declared primary/id direction, plus full identity
    # tie-breaks for unusual unproved historical rows with the same local ID.
    rows.sort(key=lambda r: cast(str, r.get("lifecycle_id", "")), reverse=descending)
    rows.sort(key=lambda r: cast(int, r["id"]), reverse=descending)
    rows.sort(key=lambda r: (r[key] is not None, r[key]), reverse=descending)


def _id_event_page(sources, low, high, items, params, fields, columns, counts, offset, limit):
    """Page ordered, disjoint shard ranges without fetching the skipped prefix.

    Counts describe matching rows, not ID distances: native IDs may be sparse.
    Only the landing shard uses a local OFFSET; later shards fill the remaining
    window. SQLite may still scan skipped rows, but only fetched work crosses the
    Python budget boundary. Source text/frames are hydrated after final selection.
    """
    rows = []
    direction = params["order_dir"]
    ordered = reversed(items) if direction == "DESC" else iter(items)
    predicate, values = _predicates(params, fields, "t.")
    projection = ", ".join(f't."{column}"' for column in columns)
    for item in ordered:
        sources.budget.remaining()
        if limit == 0:
            break
        count = counts[item.index]
        if offset >= count:
            offset -= count
            continue
        batch = sources.read(
            sources.dataset.root / item.file,
            f'SELECT {projection} FROM "trace_entry_{sources.device.device_id}" t '
            f"WHERE t.id>=0 AND t.id>=? AND t.id<=? AND {predicate} "
            f"ORDER BY t.id {direction} LIMIT ? OFFSET ?",  # nosec B608 # SQL structure uses validated integer IDs and fixed/allowlisted schema fragments; values are bound.
            [low, high, *values, limit, offset],
        )
        rows.extend(batch)
        offset = 0
        if limit >= 0:
            limit -= len(batch)
    return rows


def _events(sources, low, high, items, params, template, scope, offset, limit):
    fields = METRICS
    if template == "event":
        fields += ("id", "action", "address", "size", "stream")
    predicate, values = _predicates(params, fields)
    total, counts = _range_statistics(sources, low, high, items, scope, predicate, values)
    rows = []
    order = params["order_by"]
    direction = params["order_dir"]
    columns = ("id", *METRICS)
    if template == "event":
        columns = ("id", "action", "address", "size", "stream", *METRICS)
    candidate_limit = offset + limit if limit >= 0 else -1
    if order == "id":
        # Preserve the existing finite candidate-window int64 error, including
        # empty matches, even though the optimized plan binds a smaller LIMIT.
        if items and candidate_limit > 2**63 - 1:
            raise QueryExecutionError("Query execution failed: Python int too large to convert to SQLite INTEGER")
        return (
            _id_event_page(
                sources,
                low,
                high,
                items,
                params,
                fields,
                columns,
                counts,
                offset,
                limit if limit >= 0 else -1,
            ),
            total,
        )
    for item in items:
        trace = f'"trace_entry_{sources.device.device_id}"'
        projection = ", ".join(f't."{column}"' for column in columns)
        join = ""
        if order == "callstack":
            if sources.dataset.callstack_layout == "v2":
                projection += ", t.callstackId, cs.callstack"
                join = " LEFT JOIN callstack cs ON t.callstackId=cs.id"
            else:
                projection += ", t.callstack"
        row_predicate, row_values = _predicates(params, fields, "t.")
        # Dataset text identity/order is exact, independent of source collation.
        sort_column = '"callstack" COLLATE BINARY' if order == "callstack" else f'"{order}"'
        batch = sources.read(
            sources.dataset.root / item.file,
            f"SELECT {projection} FROM {trace} t{join} "
            f"WHERE t.id>=0 AND t.id>=? AND t.id<=? AND {row_predicate} "
            f"ORDER BY {sort_column} {direction}, t.id {direction} LIMIT ?",  # nosec B608 # SQL structure uses validated integer IDs and fixed/allowlisted schema fragments; values are bound.
            [low, high, *row_values, candidate_limit],
        )
        if order == "callstack":
            # Full candidate text has already crossed the budget boundary. Reuse
            # its event data; ordered frames are needed only for the final page.
            sources.events_from_rows(item, batch, with_frames=False)
        rows.extend(batch)
    _sort(rows, order, direction == "DESC")
    return rows, total


def _lifecycles(sources, items, scope):
    merged: Dict[str, Dict[str, object]] = {}
    terminal = sources.device.slices[-1].index
    resolved_alloc = resolved_free = unproved = 0
    for item in items:
        blocks = sources.read(
            sources.dataset.root / item.file,
            f'SELECT * FROM "block_{sources.device.device_id}" ORDER BY id',  # nosec B608 # SQL structure uses validated integer IDs and fixed/allowlisted schema fragments; values are bound.
        )
        refs = sources.events(
            cast(int, row[field])
            for row in blocks
            for field in ("allocEventId", "freeEventId")
            # pylint: disable-next=unidiomatic-typecheck  # Reject bool/subclasses: the contract requires exact scalar types.
            if type(row[field]) is int and cast(int, row[field]) >= 0
        )
        for block in blocks:
            sources.budget.remaining()
            alloc, free = cast(int, block["allocEventId"]), block["freeEventId"]
            allocation = refs.get(alloc)
            allocation = allocation if allocation and allocation.event["action"] == 4 else None
            completion = refs.get(cast(int, free))
            completion = completion if completion and completion.event["action"] == 6 else None
            proved = allocation is not None
            stable_negative = alloc == -1 and cast(int, block["id"]) < 0
            token = (
                f"alloc:{alloc}"
                if proved
                else (
                    f"preexisting:{block['id']}"
                    if stable_negative
                    else f"unproved:slice:{item.index}:block:{block['id']}"
                )
            )
            identity = f"{sources.namespace}:{token}"
            old = merged.get(identity)
            if old is not None:
                # A shared token with incompatible invariant observations is not
                # evidence to merge by address or guess which allocation wins.
                if any(old[f] != block[f] for f in ("address", "size", "requestedSize", "allocEventId")):
                    raise QueryExecutionError("Conflicting observations for a proved lifecycle identity.")
                if old["free_source"] and completion and old["freeEventId"] != free:
                    raise QueryExecutionError("Conflicting free-completion events for one lifecycle.")
                if old["free_source"] and not completion:
                    free = old["freeEventId"]
                    completion_dict = old["free_source"]
                else:
                    completion_dict = completion.to_dict() if completion else None
            else:
                completion_dict = completion.to_dict() if completion else None
            block.update(
                {
                    "lifecycle_id": identity,
                    "identity_status": (
                        "proved_allocation_event"
                        if proved
                        else "stable_negative_token"
                        if stable_negative
                        else "unproved_shard_local"
                    ),
                    "allocation_source": allocation.to_dict() if allocation else None,
                    "allocation_source_status": (
                        "resolved" if proved else "unknown_preexisting" if alloc == -1 else "missing"
                    ),
                    "free_source": completion_dict,
                    "free_source_status": (
                        "resolved"
                        if completion_dict
                        else "live_or_unknown"
                        if free is None or cast(int, free) < 0
                        else "missing"
                    ),
                    "freeEventId": free,
                    "observation_slice_index": item.index,
                    "state_scope": "latest_slice_observation",
                    "terminal_survivor": item.index == terminal
                    and block["state"] in (0, 1)
                    and (free is None or cast(int, free) < 0),
                    "category": ("dynamic" if alloc >= 0 else "static" if free == -1 else "preexisting"),
                }
            )
            merged[identity] = block
    rows = list(merged.values())
    for row in rows:
        resolved_alloc += row["allocation_source"] is not None
        resolved_free += row["free_source"] is not None
        unproved += row["identity_status"] == "unproved_shard_local"
    scope["source_coverage"] = {
        "coverage_scope": "all_deduplicated_lifecycles_before_filters_and_page",
        "range_complete": True,
        "lifecycles": len(rows),
        "allocation_events_resolved": resolved_alloc,
        "free_events_resolved": resolved_free,
        "unproved_identities": unproved,
        "allocation_source_complete": all(
            r["allocation_source"] is not None for r in rows if cast(int, r["allocEventId"]) >= 0
        ),
        "source_queries": sources.query_count,
    }
    return rows


def _text_stacks(sources, low, high, items, params, scope):
    """Merge shard sufficient statistics, never local HAVING/ranking windows."""
    grouped = {}
    events = 0
    for item in items:
        trace = f'"trace_entry_{sources.device.device_id}"'
        if sources.dataset.callstack_layout == "v2":
            table = f"{trace} t LEFT JOIN callstack cs ON t.callstackId=cs.id"
            text, present = "cs.callstack", "t.callstackId IS NOT NULL"
        else:
            table, text, present = f"{trace} t", "t.callstack", "t.callstack IS NOT NULL"
        batch = sources.read(
            sources.dataset.root / item.file,
            f"SELECT {text} AS callstack, COUNT(*) AS alloc_count, SUM(t.size) AS total_size, "
            f"MAX(t.size) AS max_size, MIN(t.id) AS stack_event_id FROM {table} "
            f"WHERE t.id>=0 AND t.id>=? AND t.id<=? AND {present} GROUP BY {text} COLLATE BINARY",  # nosec B608 # SQL structure uses validated integer IDs and fixed/allowlisted schema fragments; values are bound.
            [low, high],
        )
        for local in batch:
            sources.budget.remaining()
            value = local["callstack"]
            identity = (
                f"{sources.namespace}:text:sha256:{hashlib.sha256(value.encode('utf-8')).hexdigest()}"
                if isinstance(value, str)
                else f"{sources.namespace}:category:missing"
            )
            kind = "captured" if isinstance(value, str) and value != "" else "missing"
            row = grouped.get(identity)
            if row is None:
                row = dict(local)
                row.update(
                    {
                        "callstack": value if value is not None else "[missing callstack]",
                        "source_stack_id": identity,
                        "stack_kind": kind,
                        "text_kind": kind,
                        "frames_status": "text_only",
                    }
                )
                grouped[identity] = row
            else:
                row["alloc_count"] += local["alloc_count"]
                row["total_size"] += local["total_size"]
                row["max_size"] = max(row["max_size"], local["max_size"])
                row["stack_event_id"] = min(row["stack_event_id"], local["stack_event_id"])
            events += local["alloc_count"]
    return _finish_stacks(sources, grouped, params, scope, events, 0)


def _finish_stacks(sources, grouped, params, scope, events, ordered):
    rows = [
        r for r in grouped.values() if r["alloc_count"] >= params["min_count"] and r["total_size"] >= params["min_size"]
    ]
    for row in rows:
        row["avg_size"] = row["total_size"] / row["alloc_count"]
    rows.sort(
        key=lambda r: (
            -r["total_size"],
            r["callstack"] or "",
            r["stack_kind"] == "missing",
            r["source_stack_id"],
        )
    )
    scope["source_coverage"] = {
        "range_complete": True,
        "coverage_scope": "all_real_stack_bearing_actions_before_global_thresholds",
        "stack_events": events,
        "ordered_frame_events": ordered,
        "source_queries": sources.query_count,
    }
    return rows


def _stacks(sources, low, high, items, params, scope):
    if sources.dataset.ordered_frames_version not in (1, 2):
        return _text_stacks(sources, low, high, items, params, scope)
    grouped = {}
    events = ordered = 0
    for item in items:
        trace = f'"trace_entry_{sources.device.device_id}"'
        columns = ("id", "action", "address", "size", "stream", *METRICS)
        projection = ", ".join(f't."{column}"' for column in columns)
        join = ""
        if sources.dataset.callstack_layout == "v2":
            projection += ", t.callstackId, cs.callstack"
            join = " LEFT JOIN callstack cs ON t.callstackId=cs.id"
        else:
            projection += ", t.callstack"
        weights = None
        if sources.dataset.ordered_frames_version == 2:
            from pt_snap_cli.core.dataset.query.dataset_frames import attach_frames

            path = sources.dataset.root / item.file
            attach_frames(sources, path, [])  # Validate optional schema, no frame fetch.
            text = "cs.callstack" if sources.dataset.callstack_layout == "v2" else "t.callstack"
            stack_group = ""
            if sources._frame_schemas[path]:
                join += " LEFT JOIN pt_snap_event_stack es ON es.eventId=t.id"
                stack_group = "es.stackId,"
            batch = sources.read(
                path,
                "SELECT MIN(t.id) AS id, COUNT(*) AS alloc_count, "
                f"SUM(t.size) AS total_size, MAX(t.size) AS max_size FROM {trace} t{join} "
                f"WHERE t.id>=0 AND t.id>=? AND t.id<=? GROUP BY {stack_group}{text} COLLATE BINARY",  # nosec B608 # SQL structure uses validated integer IDs and fixed/allowlisted schema fragments; values are bound.
                [low, high],
            )
            weights = {row["id"]: row for row in batch}
            refs = sources.events(cast(int, row["id"]) for row in batch)
        else:
            batch = sources.read(
                sources.dataset.root / item.file,
                f"SELECT {projection} FROM {trace} t{join} WHERE t.id>=0 AND t.id>=? AND t.id<=? ORDER BY t.id",  # nosec B608 # SQL structure uses validated integer IDs and fixed/allowlisted schema fragments; values are bound.
                [low, high],
            )
            refs = sources.events_from_rows(item, batch)
        for source in refs.values():
            sources.budget.remaining()
            text = source.event.get("callstack")
            # Historical alloc_count is ALL stack-bearing real trace actions,
            # including free/segment/workspace. Never claim allocation-only.
            referenced = sources.dataset.callstack_layout == "v2" and source.local_stack_id is not None
            if text is None and source.frames is None and not referenced:
                continue
            identity = source.stack_id
            # Point attribution normalizes empty text into missing; statistics
            # historically count the non-NULL empty string as its own group.
            if text == "" and source.frames is None:
                identity = f"{sources.namespace}:text:sha256:{hashlib.sha256(b'').hexdigest()}"
            row = grouped.setdefault(
                identity,
                {
                    "callstack": text if text is not None else "[missing callstack]",
                    "stack_kind": source.stack_kind,
                    "text_kind": source.text_kind,
                    "alloc_count": 0,
                    "total_size": 0,
                    "max_size": 0,
                    "source_stack_id": identity,
                    "stack_event_id": source.event["id"],
                    "frames_status": source.frames_status,
                },
            )
            weight = (
                weights[source.event["id"]]
                if weights is not None
                else {
                    "alloc_count": 1,
                    "total_size": source.event["size"],
                    "max_size": source.event["size"],
                }
            )
            row["alloc_count"] += weight["alloc_count"]
            row["total_size"] += weight["total_size"]
            row["max_size"] = max(row["max_size"], weight["max_size"])
            if row["text_kind"] != "captured" and source.text_kind == "captured":
                row["callstack"], row["stack_event_id"] = text, source.event["id"]
                row["text_kind"] = "captured"
            events += weight["alloc_count"]
            ordered += weight["alloc_count"] if source.frames is not None else 0
    return _finish_stacks(sources, grouped, params, scope, events, ordered)


def global_query(
    sources: DatasetSourceResolver,
    template: str,
    params: Dict[str, object],
    max_rows: Union[int, None],
    exact_total: bool,
    slice_index: Union[int, None],
    semantics_version: Union[int, None],
) -> QueryResult:
    range_params = params if template in ("event", "allocation", "memory_peak", "allocator_gap") else {}
    low, high, items = _range(sources, range_params, slice_index)
    scope = _scope(sources, low, high, items)
    offset, limit = _window(params, max_rows)
    candidate_limit = offset + limit if limit >= 0 else -1
    total_override = None
    selected_offset = offset
    if template in ("memory_peak", "allocator_gap"):
        rows = _peaks(sources, low, high, items, template, scope)
    elif template in ("event", "allocation"):
        rows, total_override = _events(sources, low, high, items, params, template, scope, offset, limit)
        if params["order_by"] == "id":
            selected_offset = 0
    elif template == "callstack_analysis":
        rows = _stacks(sources, low, high, items, params, scope)
    elif template == "preexisting_live":
        event = cast(int, params["event_id"])
        item = sources.target(event, slice_index)
        blocks = sources.read(
            sources.dataset.root / item.file,
            f'SELECT COUNT(*) AS block_count, COALESCE(SUM(size),0) AS size_bytes FROM "block_{sources.device.device_id}" WHERE allocEventId=-1 AND (freeEventId IS NULL OR freeEventId> ? OR (freeEventId<0 AND freeEventId!=-1))',  # nosec B608 # SQL structure uses validated integer IDs and fixed/allowlisted schema fragments; values are bound.
            [event],
        )
        rows = blocks
        scope = _scope(sources, event, event, [item])
    else:
        if template == "leak_detection" and slice_index is not None:
            raise QueryExecutionError(
                "Dataset leak_detection requires terminal dataset scope, not --slice; select an explicit member for local observations."
            )
        pushed = lifecycle_query(sources, items, template, params, scope, candidate_limit)
        if pushed is not None:
            rows, total_override = pushed
        else:
            rows = _lifecycles(sources, items, scope)
            if template == "block":
                rows = [
                    r
                    for r in rows
                    if _matches(
                        r,
                        params,
                        ("id", "address", "size", "requestedSize", "allocEventId", "freeEventId"),
                    )
                ]
                _sort(rows, cast(str, params["order_by"]), params["order_dir"] == "DESC")
            elif template == "leak_detection":
                rows = [
                    r
                    for r in rows
                    if r["terminal_survivor"]
                    and r["allocation_source"] is not None
                    and cast(int, r["size"]) >= cast(int, params["min_size"])
                ]
                _sort(rows, "size", True)
            elif template == "freed_block_lifetime":
                buckets = {}
                for row in rows:
                    if row["allocation_source"] is None or row["free_source"] is None:
                        continue
                    distance = cast(int, row["freeEventId"]) - cast(int, row["allocEventId"])
                    if distance < 0:
                        continue
                    index = next(
                        (i for i, cap in enumerate((1000, 5000, 20000, 100000)) if distance < cap),
                        4,
                    )
                    bucket = buckets.setdefault(
                        index,
                        {
                            "lifetime_events": ("<1k", "1k-5k", "5k-20k", "20k-100k", ">=100k")[index],
                            "block_count": 0,
                            "size_bytes": 0,
                        },
                    )
                    bucket["block_count"] += 1
                    bucket["size_bytes"] += row["size"]
                rows = [buckets[i] for i in sorted(buckets)]
            else:
                raise QueryExecutionError("No dataset-global merge implementation for this template.")
    total = len(rows) if total_override is None else total_override
    selected = rows[selected_offset : selected_offset + limit] if limit >= 0 else rows[selected_offset:]
    if template == "event":
        refs = sources.events(cast(int, r["id"]) for r in selected)
        detailed = sources.dataset.ordered_frames_version in (1, 2) or cast(int, params["stack_bytes"]) >= 0
        selected = [dict(refs[cast(int, r["id"])].event) for r in selected]
        if detailed:
            for row in selected:
                source = refs[cast(int, row["id"])]
                row.update(
                    {
                        "source_stack_id": source.stack_id,
                        "stack_id": source.stack_id,
                        "stack_kind": source.stack_kind,
                        "text_kind": source.text_kind,
                        "stack_event_id": row["id"] if source.stack_kind == "captured" else None,
                        "frames": source.frames,
                        "frames_status": source.frames_status,
                    }
                )
        scope["source_coverage"] = {
            "range_complete": True,
            "event_position": "after",
            "coverage_scope": "returned_events",
            "events_resolved": len(refs),
            "ordered_frame_events": sum(s.frames is not None for s in refs.values()),
            "source_queries": sources.query_count,
        }
    elif template == "allocation":
        selected = [{k: r[k] for k in ("id", *METRICS)} for r in selected]
    sources.budget.consume(selected)
    more = total > offset + len(selected)
    return QueryResult(
        total=total if exact_total else len(selected),
        returned=len(selected),
        device_id=sources.device.device_id,
        rows=selected,
        template=template,
        semantics_version=semantics_version,
        has_more=more,
        truncated=more or offset > 0,
        total_is_exact=exact_total or not more and offset == 0,
        timeout_s=sources.budget.timeout_s,
        scope=scope,
    )
