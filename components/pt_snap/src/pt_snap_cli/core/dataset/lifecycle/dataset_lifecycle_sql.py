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

"""Bounded lifecycle reduction with one reusable state row per large-scope identity.

Small observation sets use read-only ATTACH/CTEs; larger sets reuse a private,
size-limited derived table for summary and page/buckets. Only aggregates/pages
cross the Python boundary. The fetched-row/byte budget does not bound SQLite's
internal scans or temporary space. All statements, including the bounded routing
probe, share the operation deadline. Source members always remain read-only.
"""

from __future__ import annotations

import sqlite3
from contextlib import closing
from typing import cast

from pt_snap_cli.core.common.errors import QueryExecutionError
from pt_snap_cli.core.dataset.dataset_contract import BLOCK_COLUMNS
from pt_snap_cli.core.dataset.lifecycle.dataset_lifecycle_connection import _AttachedSources

# A row threshold, not an ATTACH/shard-count heuristic. Same-artifact synthetic
# measurements show scratch's fixed storage cost dominates tiny inputs, while
# reduction reuse wins well before this conservative observation bound. Probe
# only this many + 1 observations across all members, never COUNT the whole scope.
_ATTACHED_OBSERVATION_LIMIT = 4096


def _attachment_limit() -> int:
    # getlimit is unavailable before Python 3.11. Ten is SQLite's default.
    with closing(sqlite3.connect(":memory:")) as connection:
        getter = getattr(connection, "getlimit", None)
        category = getattr(sqlite3, "SQLITE_LIMIT_ATTACHED", None)
        return getter(category) if getter is not None and category is not None else 10


def _required_slices(sources, items, limit):
    """Discover proof owners without fetching individual block/event references."""
    required = {item.index: item for item in items}
    if len(required) > limit:
        return None
    if len(required) == len(sources.device.slices):
        return list(required.values())
    for item in items:
        # Both references may point outside the observation scope. Discover all
        # owners before filtering/pagination so lifecycle conflicts remain visible.
        queries = []
        for field in ("allocEventId", "freeEventId"):
            cases = " ".join(
                f'WHEN "{field}" BETWEEN {owner.start_event_id} AND {owner.end_event_id} THEN {owner.index}'
                for owner in sources.device.slices
                if owner.index not in required
            )
            queries.append(f"SELECT CASE {cases} END AS owner_index FROM \"block_{sources.device.device_id}\"")  # nosec B608 # SQL structure uses validated integer IDs and fixed/allowlisted schema fragments; values are bound.
        rows = sources.read(
            sources.dataset.root / item.file,
            "SELECT owner_index FROM (" + " UNION ".join(queries) + ") WHERE owner_index IS NOT NULL LIMIT ?",  # nosec B608 # SQL structure uses validated integer IDs and fixed/allowlisted schema fragments; values are bound.
            [limit - len(required) + 1],
        )
        for row in rows:
            owner = sources.device.slices[row["owner_index"]]
            required[owner.index] = owner
        if len(required) > limit:
            return None
        if len(required) == len(sources.device.slices):
            break
    return sorted(required.values(), key=lambda item: item.index)


def _proof(sources, items, field, action):
    device = sources.device.device_id
    cases = " ".join(
        f'WHEN b."{field}" BETWEEN {item.start_event_id} AND {item.end_event_id} '
        f'THEN EXISTS(SELECT 1 FROM "s{item.index}"."trace_entry_{device}" e '
        f'WHERE e.id=b."{field}" AND e.id>=0 AND e.action={action})'  # nosec B608 # SQL structure uses validated integer IDs and fixed/allowlisted schema fragments; values are bound.
        for item in items
    )
    return f"CASE {cases} ELSE 0 END"


def _large_observation_set(sources, items):
    remaining = _ATTACHED_OBSERVATION_LIMIT + 1
    for item in items:
        count = sources.read(
            sources.dataset.root / item.file,
            f'SELECT COUNT(*) AS count FROM (SELECT 1 FROM "block_{sources.device.device_id}" LIMIT ?)',  # nosec B608 # SQL structure uses validated integer IDs and fixed/allowlisted schema fragments; values are bound.
            [remaining],
        )[0]["count"]
        remaining -= count
        if remaining == 0:
            return True
    return False


def _lifecycle_cte(sources, items, proof_items):
    allocated = _proof(sources, proof_items, "allocEventId", 4)
    completed = _proof(sources, proof_items, "freeEventId", 6)
    selected = ",".join(f'b."{name}"' for name, _ in BLOCK_COLUMNS)
    observations = " UNION ALL ".join(
        f"SELECT {selected}, {item.index} AS observation_slice_index, "
        f"{allocated} AS allocation_proved, "
        f"CASE WHEN {completed} THEN b.freeEventId END AS completed_free "
        f'FROM "s{item.index}"."block_{sources.device.device_id}" b'  # nosec B608 # SQL structure uses validated integer IDs and fixed/allowlisted schema fragments; values are bound.
        for item in items
    )
    invariants = ("address", "size", "requestedSize", "allocEventId")
    conflicts = " OR ".join(
        f'(MIN("{column}") IS NOT MAX("{column}") OR (COUNT("{column}")>0 AND COUNT("{column}")<COUNT(*)))'
        for column in invariants
    )
    terminal = sources.device.slices[-1].index
    return f"""WITH observations AS ({observations}), identified AS (
        SELECT *, CASE WHEN allocation_proved THEN 'alloc:' || allocEventId
            WHEN allocEventId=-1 AND id<0 THEN 'preexisting:' || id
            ELSE 'unproved:slice:' || observation_slice_index || ':block:' || id
        END AS token FROM observations
    ), history AS (
        SELECT token, MAX(completed_free) AS known_free,
            ({conflicts}) AS invariant_conflict,
            MIN(completed_free) IS NOT MAX(completed_free) AS free_conflict
        FROM identified GROUP BY token
    ), ranked AS (
        SELECT *, ROW_NUMBER() OVER (
            PARTITION BY token ORDER BY observation_slice_index DESC, id DESC
        ) AS observation_rank FROM identified
    ), latest AS (
        SELECT r.id, r.address, r.size, r.requestedSize, r.state, r.allocEventId,
            COALESCE(h.known_free,r.freeEventId) AS freeEventId,
            r.observation_slice_index, r.allocation_proved, r.token,
            h.known_free IS NOT NULL AS completion_proved,
            h.invariant_conflict, h.free_conflict
        FROM ranked r JOIN history h ON h.token=r.token WHERE observation_rank=1
    ), lifecycles AS (
        SELECT *, (observation_slice_index={terminal} AND state IN (0,1)
            AND (freeEventId IS NULL OR freeEventId<0)) AS terminal_survivor
        FROM latest
    ) """  # nosec B608 # SQL structure uses validated integer IDs and fixed/allowlisted schema fragments; values are bound.


def _filter(template, params):
    if template == "leak_detection":
        return "terminal_survivor AND allocation_proved AND size>=?", [params["min_size"]]
    if template == "freed_block_lifetime":
        return "allocation_proved AND completion_proved AND freeEventId>=allocEventId", []
    clauses, values = [], []
    for field in ("id", "address", "size", "requestedSize", "allocEventId", "freeEventId"):
        for prefix, operator in (("", "="), ("min_", ">="), ("max_", "<=")):
            value = params.get(prefix + field)
            if value is not None:
                clauses.append(f'"{field}" {operator} ?')
                values.append(value)
    return " AND ".join(clauses) or "1", values


def lifecycle_query(sources, items, template, params, scope, candidate_limit):
    attachment_limit = _attachment_limit()
    if attachment_limit < 1:
        return None
    required = _required_slices(sources, items, attachment_limit)
    predicate, values = _filter(template, params)
    scratch_enabled = sources.budget.max_scratch_db_bytes != 0
    if scratch_enabled and (required is None or _large_observation_set(sources, items)):
        from pt_snap_cli.core.dataset.lifecycle.dataset_lifecycle_scratch import scratch_lifecycles

        # Once selected, storage/deadline failures must fail the whole operation;
        # falling back could hide exhaustion and redo unbounded expensive work.
        execution = scratch_lifecycles(sources, items)
    else:
        if required is None:
            return None
        from contextlib import contextmanager

        @contextmanager
        def attached_lifecycles():
            with _AttachedSources(sources, required) as database:
                yield database, _lifecycle_cte(sources, items, required)

        execution = attached_lifecycles()
    with execution as (database, cte):
        summary = database.read(
            cte
            + f"""SELECT COUNT(*) AS lifecycles,
                COALESCE(SUM(allocation_proved),0) AS allocation_events_resolved,
                COALESCE(SUM(completion_proved),0) AS free_events_resolved,
                COALESCE(SUM(token LIKE 'unproved:%'),0) AS unproved_identities,
                COALESCE(SUM(allocEventId>=0 AND NOT allocation_proved),0) AS missing_allocations,
                COALESCE(MAX(invariant_conflict),0) AS invariant_conflict,
                COALESCE(MAX(free_conflict),0) AS free_conflict,
                COALESCE(SUM(CASE WHEN {predicate} THEN 1 ELSE 0 END),0) AS matching
                FROM lifecycles""",  # nosec B608 # SQL structure uses validated integer IDs and fixed/allowlisted schema fragments; values are bound.
            values,
        )[0]
        if summary["invariant_conflict"]:
            raise QueryExecutionError("Conflicting observations for a proved lifecycle identity.")
        if summary["free_conflict"]:
            raise QueryExecutionError("Conflicting free-completion events for one lifecycle.")
        scope["source_coverage"] = {
            "coverage_scope": "all_deduplicated_lifecycles_before_filters_and_page",
            "range_complete": True,
            **{
                key: summary[key]
                for key in (
                    "lifecycles",
                    "allocation_events_resolved",
                    "free_events_resolved",
                    "unproved_identities",
                )
            },
            "allocation_source_complete": not summary["missing_allocations"],
            "source_queries": sources.query_count,
        }
        if template == "freed_block_lifetime":
            buckets = database.read(
                cte
                + f"""SELECT CASE
                    WHEN freeEventId-allocEventId<1000 THEN 0
                    WHEN freeEventId-allocEventId<5000 THEN 1
                    WHEN freeEventId-allocEventId<20000 THEN 2
                    WHEN freeEventId-allocEventId<100000 THEN 3 ELSE 4 END AS bucket,
                    COUNT(*) AS block_count, SUM(size) AS size_bytes
                    FROM lifecycles WHERE {predicate} GROUP BY bucket ORDER BY bucket""",  # nosec B608 # SQL structure uses validated integer IDs and fixed/allowlisted schema fragments; values are bound.
                values,
            )
            for row in buckets:
                row["lifetime_events"] = ("<1k", "1k-5k", "5k-20k", "20k-100k", ">=100k")[row.pop("bucket")]
            scope["source_coverage"]["source_queries"] = sources.query_count
            return buckets, len(buckets)
        order = params["order_by"] if template == "block" else "size"
        direction = params["order_dir"] if template == "block" else "DESC"
        rows = database.read(
            cte + f"SELECT * FROM lifecycles WHERE {predicate} "
            f'ORDER BY "{order}" {direction}, id {direction}, token {direction} LIMIT ?',  # nosec B608 # SQL structure uses validated integer IDs and fixed/allowlisted schema fragments; values are bound.
            [*values, candidate_limit],
        )
    refs = sources.events(
        cast(int, row[field])
        for row in rows
        for field in ("allocEventId", "freeEventId")
        # pylint: disable-next=unidiomatic-typecheck  # Reject bool/subclasses: the contract requires exact scalar types.
        if type(row[field]) is int and cast(int, row[field]) >= 0
    )
    for row in rows:
        alloc, free = row["allocEventId"], row["freeEventId"]
        allocation = refs.get(alloc) if row.pop("allocation_proved") else None
        completion = refs.get(free) if row.pop("completion_proved") else None
        token = row.pop("token")
        row.pop("invariant_conflict")
        row.pop("free_conflict")
        row.update(
            {
                "lifecycle_id": f"{sources.namespace}:{token}",
                "identity_status": (
                    "proved_allocation_event"
                    if allocation
                    else ("stable_negative_token" if token.startswith("preexisting:") else "unproved_shard_local")
                ),
                "allocation_source": allocation.to_dict() if allocation else None,
                "allocation_source_status": (
                    "resolved" if allocation else ("unknown_preexisting" if alloc == -1 else "missing")
                ),
                "free_source": completion.to_dict() if completion else None,
                "free_source_status": (
                    "resolved" if completion else ("live_or_unknown" if free is None or free < 0 else "missing")
                ),
                "state_scope": "latest_slice_observation",
                "terminal_survivor": bool(row["terminal_survivor"]),
                "category": "dynamic" if alloc >= 0 else "static" if free == -1 else "preexisting",
            }
        )
    scope["source_coverage"]["source_queries"] = sources.query_count
    return rows, summary["matching"]
