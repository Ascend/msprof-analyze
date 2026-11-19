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

"""Read-only, batched device/event source lookup over a validated dataset.

No address joins, foreign-event insertion, text-to-frame reconstruction, or retained
cross-operation source cache. The caller owns the Context LRU and the entire operation's deadline.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import time
from bisect import bisect_right
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Set, Union, cast

from pt_snap_cli.context import DatabaseNotFoundError, SchemaVersionError
from pt_snap_cli.core.cache.context_cache import ContextCache
from pt_snap_cli.core.common.errors import (
    DatabaseSchemaError,
    InvalidParameterError,
    QueryCancelledError,
    QueryExecutionError,
    QueryTimeoutError,
)
from pt_snap_cli.core.common.frame_json import _bounded_depth, _finite_float, _invalid_constant
from pt_snap_cli.core.common.query_limits import (
    DEFAULT_MAX_SCRATCH_DB_BYTES,
    DEFAULT_MAX_WORK_BYTES,
    DEFAULT_MAX_WORK_ROWS,
    QueryLimits,
)
from pt_snap_cli.core.dataset.dataset_contract import SliceRecord, _unique_object
from pt_snap_cli.core.dataset.dataset_files import member_is_immutable, require_readonly_member
from pt_snap_cli.core.dataset.dataset_resolver import ResolvedDataset
from pt_snap_cli.query.executor import QueryExecutionError as ExecutorError
from pt_snap_cli.query.executor import QueryExecutor, cancellation_options
from pt_snap_cli.query.executor import QueryTimeoutError as ExecutorTimeout

SOURCE_BATCH_SIZE = 256


@dataclass
class QueryBudget:
    timeout_s: Union[float, None]
    started: float
    max_work_rows: int = DEFAULT_MAX_WORK_ROWS
    max_work_bytes: int = DEFAULT_MAX_WORK_BYTES
    work_rows: int = 0
    work_bytes: int = 0
    # Per-operation derived database pages, not total SQLite temp space or RSS.
    # Zero retains the bounded in-Python fallback.
    max_scratch_db_bytes: int = DEFAULT_MAX_SCRATCH_DB_BYTES
    cancelled: Union[Callable[[], bool], None] = None

    @classmethod
    def from_limits(cls, limits: QueryLimits, timeout_s: Union[float, None], started: float) -> QueryBudget:
        return cls(
            timeout_s,
            started,
            max_work_rows=limits.max_work_rows,
            max_work_bytes=limits.max_work_bytes,
            max_scratch_db_bytes=limits.max_scratch_db_bytes,
        )

    def describe(self) -> Dict[str, object]:
        return {
            "max_rows": self.max_work_rows,
            "max_bytes": self.max_work_bytes,
            "max_scratch_db_bytes": self.max_scratch_db_bytes,
            "unit": "cumulative_fetched_and_output_serialized_values; not_RSS",
            "scratch_unit": "derived_database_pages; not_total_temporary_space_or_RSS",
        }

    def consume(self, rows: List[Dict[str, object]]) -> None:
        """Bound cumulative fetched rows/serialized values, not merely output.

        Includes repeated source reads. Exceeding either ceiling fails the whole
        operation, never returning a silently partial global conclusion. This is
        not an RSS ceiling: SQLite and one fetched batch have their own overhead.
        """
        self.remaining()
        self.work_rows += len(rows)
        self.work_bytes += sum(len(json.dumps(row, ensure_ascii=True, default=str).encode("utf-8")) for row in rows)
        if self.work_rows > self.max_work_rows or self.work_bytes > self.max_work_bytes:
            raise QueryExecutionError(
                "Dataset query work budget exceeded "
                f"(max_work_rows={self.max_work_rows}, max_work_bytes={self.max_work_bytes}, "
                f"max_scratch_db_bytes={self.max_scratch_db_bytes}; "
                f"consumed_rows={self.work_rows}, consumed_bytes={self.work_bytes}); "
                "no partial global result. Narrow the scope or explicitly raise query limits."
            )

    def remaining(self) -> Union[float, None]:
        if self.cancelled is not None and self.cancelled():
            raise QueryCancelledError("Frame tree query cancelled by a newer request or reset.")
        if self.timeout_s is None:
            return None
        left = self.timeout_s - (time.monotonic() - self.started)
        if left <= 0:
            raise QueryTimeoutError(f"Query timed out after {self.timeout_s} seconds")
        return left


@dataclass(frozen=True)
class EventSource:
    event: Dict[str, object]
    slice_index: int
    stack_id: str
    stack_kind: str
    frames: Union[List[Dict[str, object]], None] = None
    frames_status: str = "text_only"
    local_stack_id: Union[int, None] = None

    @property
    def text_kind(self) -> str:
        text = self.event.get("callstack")
        return "captured" if isinstance(text, str) and text != "" else "missing"

    def to_dict(self) -> Dict[str, object]:
        return {
            "event": self.event,
            "slice_index": self.slice_index,
            "local_stack_id": self.local_stack_id,
            "stack_id": self.stack_id,
            "stack_kind": self.stack_kind,
            "text_kind": self.text_kind,
            "frames": self.frames,
            "frames_status": self.frames_status,
        }


class DatasetSourceResolver:
    """One operation's sources; at most one SQL batch per shard/256 distinct IDs.

    Schema/optional frame checks add a constant number of queries per visited
    shard. Connections are sequential and bounded by the borrowed LRU, not blocks.
    """

    def __init__(self, dataset: ResolvedDataset, device_id: int, cache: ContextCache, budget: QueryBudget) -> None:
        self.dataset = dataset
        self.device = dataset.device(device_id)
        self.cache = cache
        self.budget = budget
        self.query_count = 0
        self._starts = [s.start_event_id for s in self.device.slices]
        # Lifetime is one budgeted operation. Each retained source was charged
        # when fetched; reusing the same object performs no further database work.
        self._events: Dict[int, EventSource] = {}
        self._frames_resolved: Set[int] = set()
        self._frame_schemas: Dict[Path, bool] = {}

    @property
    def namespace(self) -> str:
        return f"dataset:{self.dataset.fingerprint}:device:{self.device.device_id}"

    def owner(self, event_id: int) -> Union[SliceRecord, None]:
        # pylint: disable-next=unidiomatic-typecheck  # Reject bool/subclasses: the contract requires exact scalar types.
        if type(event_id) is not int or event_id < 0:
            return None
        index = bisect_right(self._starts, event_id) - 1
        if index < 0:
            return None
        item = self.device.slices[index]
        return item if event_id <= item.end_event_id else None

    def target(self, event_id: int, slice_index: Union[int, None] = None) -> SliceRecord:
        item = self.owner(event_id)
        if item is None or (slice_index is not None and item.index != slice_index):
            raise InvalidParameterError("Event ID must be a real ID within the selected scope.")
        if event_id not in self.events([event_id]):
            raise InvalidParameterError(f"No real event at ID {event_id}; sparse gaps are not events.")
        return item

    def _consume(self, rows: List[Dict[str, object]]) -> None:
        # The executor intentionally knows only its own errors. Translate the
        # core callback's timeout before its generic exception boundary, so
        # cancellation keeps the domain kind and CLI QUERY_TIMEOUT code.
        try:
            self.budget.consume(rows)
        except QueryTimeoutError as exc:
            raise ExecutorTimeout(str(exc)) from exc
        except QueryExecutionError as exc:
            raise ExecutorError(str(exc)) from exc

    def read(self, path: Path, sql: str, values: Union[List[object], None] = None) -> List[Dict[str, object]]:
        self.budget.remaining()
        require_readonly_member(self.dataset.root, path, immutable=self.dataset.callstack_layout == "v1")
        try:
            context = self.cache.get(
                path,
                generation=self.dataset.fingerprint,
                immutable=member_is_immutable(path, self.dataset.callstack_layout == "v1"),
            )
            self.query_count += 1
            return QueryExecutor(context).execute(
                sql,
                values,
                timeout_s=self.budget.remaining(),
                consume=self._consume,
                **cancellation_options(self.budget.cancelled),
            )
        except ExecutorTimeout as exc:
            self.budget.remaining()
            raise QueryTimeoutError(f"Query timed out after {self.budget.timeout_s} seconds") from exc
        except ExecutorError as exc:
            self.budget.remaining()
            raise QueryExecutionError(str(exc)) from exc
        except (DatabaseNotFoundError, SchemaVersionError, sqlite3.DatabaseError) as exc:
            raise DatabaseSchemaError(str(exc)) from exc

    def events(self, event_ids: Iterable[int]) -> Dict[int, EventSource]:
        grouped: Dict[int, List[int]] = defaultdict(list)
        result: Dict[int, EventSource] = {}
        for event in sorted(set(event_ids)):
            self.budget.remaining()
            # pylint: disable-next=unidiomatic-typecheck  # Reject bool/subclasses: the contract requires exact scalar types.
            if type(event) is int and event in self._events:
                result[event] = self._events[event]
                continue
            item = self.owner(event)
            if item is not None:
                grouped[item.index].append(event)
        for index, ids in grouped.items():
            item = self.device.slices[index]
            path = self.dataset.root / item.file
            trace = f'"trace_entry_{self.device.device_id}"'
            for start in range(0, len(ids), SOURCE_BATCH_SIZE):
                batch = ids[start : start + SOURCE_BATCH_SIZE]
                placeholders = ",".join("?" for _ in batch)
                sql = (
                    f"SELECT t.*, cs.callstack FROM {trace} t LEFT JOIN callstack cs ON t.callstackId=cs.id"  # nosec B608 # SQL structure uses validated integer IDs and fixed/allowlisted schema fragments; values are bound.
                    if self.dataset.callstack_layout == "v2"
                    else f"SELECT t.* FROM {trace} t"  # nosec B608 # SQL structure uses validated integer IDs and fixed/allowlisted schema fragments; values are bound.
                )
                rows = self.read(path, sql + f" WHERE t.id IN ({placeholders}) AND t.id>=0", list(batch))
                result.update(self.events_from_rows(item, rows, with_frames=False))
        frame_groups: Dict[int, List[int]] = defaultdict(list)
        for event, source in result.items():
            frame_groups[source.slice_index].append(event)
        for index, ids in frame_groups.items():
            self._ensure_frames(self.device.slices[index], ids)
        self.budget.remaining()
        return {event: self._events[event] for event in result}

    def events_from_rows(
        self, item: SliceRecord, rows: List[Dict[str, object]], *, with_frames: bool = True
    ) -> Dict[int, EventSource]:
        """Resolve already charged full event rows without fetching them again.

        Native rows must include joined callstack text and the local callstackId.
        Frame reads still incur the same work budget as events() source lookup.
        Sources remain cached until this resolver operation ends. Serialized
        value accounting excludes Python object overhead and is not an RSS cap.
        """
        result: Dict[int, EventSource] = {}
        for original in rows:
            self.budget.remaining()
            event_id = cast(int, original["id"])
            if self.owner(event_id) != item:
                raise QueryExecutionError("Source event does not belong to the selected shard.")
            if event_id in self._events:
                result[event_id] = self._events[event_id]
                continue
            row = dict(original)
            event_id = cast(int, row["id"])
            text = row.get("callstack")
            captured = isinstance(text, str) and text != ""
            local_id = cast(Union[int, None], row.pop("callstackId", None))
            # V2 IDs select text WITHIN the owning DB; they are provenance,
            # not dataset grouping keys. Global interning equivalence uses
            # the full captured text, never a shortened display prefix.
            identity = (
                "text:sha256:" + hashlib.sha256((text if isinstance(text, str) else "").encode("utf-8")).hexdigest()
            )
            result[event_id] = EventSource(
                row,
                item.index,
                (f"{self.namespace}:{identity}" if captured else f"{self.namespace}:category:missing"),
                "captured" if captured else "missing",
                local_stack_id=local_id,
            )
        fresh = {event: source for event, source in result.items() if event not in self._events}
        self._events.update(fresh)
        if with_frames:
            self._ensure_frames(item, list(result))
        self.budget.remaining()
        return {event: self._events[event] for event in result}

    def _ensure_frames(self, item: SliceRecord, ids: List[int]) -> None:
        pending = [event for event in ids if event not in self._frames_resolved]
        if pending:
            self._attach_frames(self.dataset.root / item.file, pending, self._events)
            self._frames_resolved.update(pending)

    def _attach_frames(self, path: Path, ids: List[int], sources: Dict[int, EventSource]) -> None:
        if self.dataset.ordered_frames_version == 2:
            from pt_snap_cli.core.dataset.query.dataset_frames import attach_frames

            decoded = attach_frames(self, path, ids)
            for event, (frames, digest) in decoded.items():
                old = sources[event]
                sources[event] = EventSource(
                    old.event,
                    old.slice_index,
                    f"{self.namespace}:frames:sha256:{digest}",
                    "captured",
                    frames,
                    "ordered",
                    old.local_stack_id,
                )
            return
        # This is a NEW, explicit read contract, not a guessed original-producer
        # schema. Existing pt_snap_block_reference has formatted text only.
        if self.dataset.ordered_frames_version != 1:
            return
        expected = {
            "pt_snap_frame_coverage": [("eventId", "INTEGER", 1), ("frameCount", "INTEGER", 0)],
            "pt_snap_frame": [
                ("eventId", "INTEGER", 1),
                ("frameIndex", "INTEGER", 2),
                ("frameJson", "TEXT", 0),
            ],
        }
        if path not in self._frame_schemas:
            self._frame_schemas[path] = True
            for table, columns in expected.items():
                kind = self.read(path, "SELECT type FROM sqlite_master WHERE name=?", [table])
                schema = self.read(path, f'PRAGMA table_info("{table}")')
                if kind != [{"type": "table"}] or [(r["name"], r["type"], r["pk"]) for r in schema] != columns:
                    self._frame_schemas[path] = False
                    break  # Unknown/absent schemas never imply precision.
        if not self._frame_schemas[path]:
            return
        for start in range(0, len(ids), SOURCE_BATCH_SIZE):
            batch = ids[start : start + SOURCE_BATCH_SIZE]
            placeholders = ",".join("?" for _ in batch)
            coverage = self.read(
                path,
                f"SELECT * FROM pt_snap_frame_coverage WHERE eventId IN ({placeholders})",  # nosec B608 # Only placeholder count varies; data values are bound separately.
                list(batch),
            )
            frames = self.read(
                path,
                f"SELECT * FROM pt_snap_frame WHERE eventId IN ({placeholders}) ORDER BY eventId,frameIndex",  # nosec B608 # Only placeholder count varies; data values are bound separately.
                list(batch),
            )
            by_event: Dict[int, List[Dict[str, object]]] = defaultdict(list)
            for row in frames:
                by_event[cast(int, row["eventId"])].append(row)
            for row in coverage:
                event = cast(int, row["eventId"])
                count = row["frameCount"]
                entries = by_event[event]
                # pylint: disable-next=unidiomatic-typecheck  # Reject bool/subclasses: the contract requires exact scalar types.
                if event not in sources or type(count) is not int or count < 0 or len(entries) != count:
                    continue
                if any(
                    # pylint: disable-next=unidiomatic-typecheck  # Reject bool/subclasses: the contract requires exact scalar types.
                    type(entry["frameIndex"]) is not int or not isinstance(entry["frameJson"], str)
                    for entry in entries
                ) or [entry["frameIndex"] for entry in entries] != list(range(count)):
                    continue
                try:
                    decoded = [
                        json.loads(
                            cast(str, entry["frameJson"]),
                            object_pairs_hook=_unique_object,
                            parse_constant=_invalid_constant,
                            parse_float=_finite_float,
                        )
                        for entry in entries
                    ]
                    if not all(isinstance(frame, dict) for frame in decoded) or not _bounded_depth(decoded):
                        continue
                    # Canonical raw arrays retain order, duplicates and typed fields.
                    # Text formatting and shard-local IDs are only provenance here.
                    digest = hashlib.sha256(
                        json.dumps(
                            decoded,
                            sort_keys=True,
                            ensure_ascii=True,
                            separators=(",", ":"),
                            allow_nan=False,
                        ).encode("utf-8")
                    ).hexdigest()
                except (ValueError, TypeError, RecursionError, OverflowError):
                    continue
                old = sources[event]
                sources[event] = EventSource(
                    old.event,
                    old.slice_index,
                    f"{self.namespace}:frames:sha256:{digest}",
                    "captured",
                    decoded,
                    "ordered",
                    old.local_stack_id,
                )
