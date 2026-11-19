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

"""Caller-path occupancy over the event owner's live set and allocation owners."""

from __future__ import annotations

import hashlib
import json
from typing import Dict, Tuple, Union, cast

from pt_snap_cli.core.common.models import QueryResult
from pt_snap_cli.core.dataset.dataset_sources import DatasetSourceResolver
from pt_snap_cli.core.dataset.query.dataset_attribution import _rounding_cursor, _scope

METRICS = (
    ("block_count", "self_block_count"),
    ("size_bytes", "self_bytes"),
    ("requested_bytes", "self_requested_bytes"),
)


def _node(
    node_id: str,
    parent: Union[str, None],
    depth: int,
    category: str,
    label: str,
    frame_id: Union[int, None] = None,
    frame: Union[Tuple[str, int, str], None] = None,
) -> Dict[str, object]:
    return {
        "node_id": node_id,
        "parent_id": parent,
        "depth": depth,
        "frame_id": frame_id,
        "category": category,
        "label": label,
        "filename": frame[0] if frame else None,
        "line": frame[1] if frame else None,
        "name": frame[2] if frame else None,
        **{field: 0 for pair in METRICS for field in pair},
    }


def frame_tree(
    sources: DatasetSourceResolver,
    template: str,
    params: Dict[str, object],
    max_rows: Union[int, None],
    exact_total: bool,
    slice_index: Union[int, None],
    semantics_version: Union[int, None],
) -> QueryResult:
    event_id = cast(int, params["event_id"])
    owner = sources.target(event_id, slice_index)
    groups = sources.read(
        sources.dataset.root / owner.file,
        "SELECT allocEventId, CASE WHEN allocEventId=-1 AND freeEventId=-1 THEN 'static' "  # nosec B608  # Validated integer device ID and fixed SQL fragments; values are bound.
        "WHEN allocEventId=-1 THEN 'preexisting_live_at_event' ELSE 'dynamic_live_at_event' END "
        "AS category, COUNT(*) AS block_count, SUM(size) AS size_bytes, "
        f'SUM(COALESCE(requestedSize,0)) AS requested_bytes FROM "block_{sources.device.device_id}" '
        "WHERE size>=? AND (allocEventId=-1 OR allocEventId<=?) "
        "AND (freeEventId IS NULL OR freeEventId<0 OR freeEventId>?) "
        + ("AND allocEventId!=-1 " if not params["include_static"] else "")
        + "GROUP BY allocEventId,category ORDER BY allocEventId,category",  # nosec B608 # SQL structure uses validated integer IDs and fixed/allowlisted schema fragments; values are bound.
        [params["min_size"], event_id, event_id],
    )
    references = sources.events(cast(int, g["allocEventId"]) for g in groups if cast(int, g["allocEventId"]) >= 0)
    root = _node("root", None, 0, "mixed", "[all active blocks]")
    nodes = {"root": root}
    frame_ids: Dict[Tuple[str, int, str], int] = {}
    ordered_blocks = dynamic_blocks = resolved_blocks = dynamic_bytes = captured_bytes = 0
    for group in groups:
        sources.budget.remaining()
        category = cast(str, group["category"])
        source = references.get(cast(int, group["allocEventId"]))
        frames = source.frames if source is not None and source.event["action"] == 4 else None
        if category == "dynamic_live_at_event":
            dynamic_blocks += cast(int, group["block_count"])
            dynamic_bytes += cast(int, group["size_bytes"])
            if source is not None and source.event["action"] == 4:
                resolved_blocks += cast(int, group["block_count"])
        # A covered raw array can have nonstandard dictionaries. Preserve its
        # occupancy, but never invent file/line/name from the rendered text.
        usable = frames is not None and all(
            # pylint: disable-next=unidiomatic-typecheck  # Reject bool/subclasses: the contract requires exact scalar types.
            isinstance(f.get("filename"), str) and type(f.get("line")) is int and isinstance(f.get("name"), str)
            for f in frames
        )
        parent = root
        if category == "dynamic_live_at_event" and usable:
            ordered_blocks += cast(int, group["block_count"])
            captured_bytes += cast(int, group["size_bytes"])
        path = [root]
        if category == "dynamic_live_at_event" and usable and frames:
            for depth, value in enumerate(reversed(frames), 1):
                sources.budget.remaining()
                frame = (
                    cast(str, value["filename"]),
                    cast(int, value["line"]),
                    cast(str, value["name"]),
                )
                frame_ids.setdefault(frame, len(frame_ids))
                identity = json.dumps([parent["node_id"], frame], ensure_ascii=True, separators=(",", ":"))
                node_id = "frame/" + hashlib.sha256(identity.encode("utf-8")).hexdigest()
                if node_id not in nodes:
                    nodes[node_id] = _node(
                        node_id,
                        cast(str, parent["node_id"]),
                        depth,
                        category,
                        f"{frame[0]}:{frame[1]} {frame[2]}",
                        frame_ids[frame],
                        frame,
                    )
                    sources.budget.consume([nodes[node_id]])
                parent = nodes[node_id]
                path.append(parent)
        else:
            kind = (
                category
                if category != "dynamic_live_at_event"
                else ("empty_callstack" if usable and frames == [] else "missing")
            )
            label = {
                "static": "[static]",
                "preexisting_live_at_event": "[preexisting live]",
                "empty_callstack": "[empty captured callstack]",
                "missing": "[missing callstack]",
            }[kind]
            if kind not in nodes:
                nodes[kind] = _node(
                    kind,
                    "root",
                    1,
                    "empty_callstack" if kind == "empty_callstack" else category,
                    label,
                )
                sources.budget.consume([nodes[kind]])
            parent = nodes[kind]
            path.append(parent)
        for total, own in METRICS:
            amount = cast(int, group[total])
            for node in path:
                node[total] = cast(int, node[total]) + amount
            parent[own] = cast(int, parent[own]) + amount
    rows = list(nodes.values())
    with _rounding_cursor(sources) as cursor:
        for row in rows:
            sources.budget.remaining()
            row["percent_of_total"] = cursor.execute(
                "SELECT ROUND(? * 100.0 / NULLIF(?,0),4)", (row["size_bytes"], root["size_bytes"])
            ).fetchone()[0]
    rows.sort(
        key=lambda r: (
            cast(int, r["depth"]),
            cast(str, r["parent_id"] or ""),
            -cast(int, r["size_bytes"]),
            cast(str, r["node_id"]),
        )
    )
    selected = rows[:max_rows] if max_rows is not None and max_rows > 0 else rows
    sources.budget.consume(selected)
    coverage = {
        "range_complete": True,
        "event_position": "after",
        "active_blocks": root["block_count"],
        "active_bytes": root["size_bytes"],
        "dynamic_blocks": dynamic_blocks,
        "dynamic_bytes": dynamic_bytes,
        "allocation_events_resolved": resolved_blocks,
        "allocation_source_complete": resolved_blocks == dynamic_blocks,
        "ordered_frame_bytes": captured_bytes,
        "ordered_frame_blocks": ordered_blocks,
        "ordered_frames_complete": ordered_blocks == dynamic_blocks,
        "frame_degradation": None if ordered_blocks == dynamic_blocks else "text_only_or_uncovered",
        "frame_identity": "filename_line_name; frame_id is query-local, node_id is caller-path hash",
        "source_queries": sources.query_count,
    }
    return QueryResult(
        total=len(rows) if exact_total else len(selected),
        returned=len(selected),
        device_id=sources.device.device_id,
        rows=selected,
        template=template,
        semantics_version=semantics_version,
        has_more=len(selected) < len(rows),
        truncated=len(selected) < len(rows),
        total_is_exact=exact_total or len(selected) == len(rows),
        timeout_s=sources.budget.timeout_s,
        scope=_scope(sources, owner.index, event_id, coverage),
    )
