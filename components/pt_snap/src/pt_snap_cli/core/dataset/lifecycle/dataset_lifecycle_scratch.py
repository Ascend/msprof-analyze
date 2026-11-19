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

"""Private disk-backed reduction for large lifecycle observation or ATTACH sets.

Only references and one narrow row per identity are retained. The derived main
DB has a page ceiling; this does NOT limit all SQLite journals/sort files or RSS.
The fetched/output budget and operation deadline remain independent safeguards.
Source databases are never writable, even while the derived database is built.
"""

from __future__ import annotations

import os
import sqlite3
import tempfile
from contextlib import contextmanager
from pathlib import Path

from pt_snap_cli.core.common.errors import QueryExecutionError
from pt_snap_cli.core.common.query_limits import MAX_SCRATCH_DB_BYTES, MIN_SCRATCH_DB_BYTES
from pt_snap_cli.core.dataset.dataset_files import readonly_member_uri, require_readonly_member
from pt_snap_cli.core.dataset.lifecycle.dataset_lifecycle_connection import _AttachedSources

_PAGE_SIZE = MIN_SCRATCH_DB_BYTES
_MAX_SCRATCH_BYTES = MAX_SCRATCH_DB_BYTES
_CACHE_KIB = 2048
_COLUMNS = ("id", "address", "size", "requestedSize", "state", "allocEventId", "freeEventId")


class _ScratchSources(_AttachedSources):
    def execute(self, sql, values=()):
        self._configure_deadline()
        self.sources.query_count += 1
        try:
            self.connection.execute(sql, values).close()
            self.sources.budget.remaining()
        except (sqlite3.Error, OverflowError) as exc:
            self.sources.budget.remaining()
            if getattr(exc, "sqlite_errorcode", None) == getattr(
                sqlite3, "SQLITE_FULL", 13
            ) or "database or disk is full" in str(exc):
                raise QueryExecutionError(
                    "Dataset lifecycle scratch space exhausted (derived database page limit "
                    "or disk full; "
                    f"max_scratch_db_bytes={self.sources.budget.max_scratch_db_bytes}); "
                    "no partial global result."
                ) from exc
            raise QueryExecutionError(str(exc)) from exc

    @contextmanager
    def source(self, item):
        path = self.sources.dataset.root / item.file
        immutable = self.sources.dataset.callstack_layout == "v1"
        require_readonly_member(self.sources.dataset.root, path, immutable=immutable)
        uri = readonly_member_uri(path, immutable)
        self.execute("ATTACH DATABASE ? AS src", [uri])
        try:
            # Bound each source's independent page cache too. URI mode=ro is the
            # write barrier; query_only is connection-wide and would block main.
            self.execute(f"PRAGMA src.cache_size=-{_CACHE_KIB}")
            self.execute("PRAGMA src.mmap_size=0")
            yield
        finally:
            # Detach must also work after deadline expiry or interruption. The
            # outer owner closes the connection if detach itself fails.
            self.connection.set_progress_handler(None, 0)
            self.connection.execute("DETACH DATABASE src").close()

    def build(self, items, maximum):
        self.connection.isolation_level = None
        self.connection.set_authorizer(
            lambda action, first, second, database, trigger: (
                sqlite3.SQLITE_DENY
                if action in (sqlite3.SQLITE_INSERT, sqlite3.SQLITE_UPDATE, sqlite3.SQLITE_DELETE)
                and database != "main"
                else sqlite3.SQLITE_OK
            )
        )
        self.execute("PRAGMA trusted_schema=OFF")
        self.execute(f"PRAGMA main.page_size={_PAGE_SIZE}")
        self.execute(f"PRAGMA main.max_page_count={maximum // _PAGE_SIZE}")
        self.execute(f"PRAGMA main.cache_size=-{_CACHE_KIB}")
        self.execute("PRAGMA main.mmap_size=0")
        self.execute("PRAGMA temp_store=FILE")
        self.execute("PRAGMA journal_mode=DELETE")
        self.execute(
            "CREATE TABLE refs(id INTEGER PRIMARY KEY, allocation_proved INTEGER NOT NULL "
            "DEFAULT 0, completion_proved INTEGER NOT NULL DEFAULT 0)"
        )
        device = self.sources.device.device_id
        for item in items:
            with self.source(item):
                for column in ("allocEventId", "freeEventId"):
                    self.execute(
                        f'INSERT OR IGNORE INTO refs(id) SELECT "{column}" '
                        f'FROM src."block_{device}" WHERE "{column}">=0'  # nosec B608 # SQL structure uses validated integer IDs and fixed/allowlisted schema fragments; values are bound.
                    )
        # Range ownership is authoritative. Never accept a same-ID event from a
        # non-owner, a boundary/sentinel event, or an event with the wrong action.
        for item in self.sources.device.slices:
            needed = self.read(
                "SELECT EXISTS(SELECT 1 FROM refs WHERE id BETWEEN ? AND ?) AS needed",
                [item.start_event_id, item.end_event_id],
            )[0]["needed"]
            if needed:
                with self.source(item):
                    self.execute(
                        "UPDATE refs SET allocation_proved=EXISTS(SELECT 1 FROM "
                        f'src."trace_entry_{device}" e WHERE e.id=refs.id AND e.id>=0 '
                        "AND e.action=4), completion_proved=EXISTS(SELECT 1 FROM "
                        f'src."trace_entry_{device}" e WHERE e.id=refs.id AND e.id>=0 '
                        "AND e.action=6) WHERE id BETWEEN ? AND ?",  # nosec B608 # SQL structure uses validated integer IDs and fixed/allowlisted schema fragments; values are bound.
                        [item.start_event_id, item.end_event_id],
                    )
        self.execute(
            "CREATE TABLE lifecycle_state(token TEXT PRIMARY KEY COLLATE BINARY, "
            + ", ".join(f'"{column}" INTEGER' for column in _COLUMNS)
            + ", observation_slice_index INTEGER NOT NULL, allocation_proved INTEGER NOT NULL, "
            "known_free INTEGER, invariant_conflict INTEGER NOT NULL DEFAULT 0, "
            "free_conflict INTEGER NOT NULL DEFAULT 0) WITHOUT ROWID"
        )
        latest = (
            "(excluded.observation_slice_index>lifecycle_state.observation_slice_index OR "
            "(excluded.observation_slice_index=lifecycle_state.observation_slice_index "
            "AND excluded.id>lifecycle_state.id))"
        )
        updates = ", ".join(
            f'"{column}"=CASE WHEN {latest} THEN excluded."{column}" ELSE lifecycle_state."{column}" END'
            for column in (*_COLUMNS, "observation_slice_index")
        )
        conflict = " OR ".join(
            f'lifecycle_state."{column}" IS NOT excluded."{column}"'
            for column in ("address", "size", "requestedSize", "allocEventId")
        )
        for item in items:
            with self.source(item):
                self.execute(
                    "INSERT INTO lifecycle_state(token, "
                    + ", ".join(f'"{column}"' for column in _COLUMNS)
                    + ", observation_slice_index, allocation_proved, known_free) "
                    "SELECT CASE WHEN a.allocation_proved THEN 'alloc:' || b.allocEventId "
                    "WHEN b.allocEventId=-1 AND b.id<0 THEN 'preexisting:' || b.id "
                    f"ELSE 'unproved:slice:{item.index}:block:' || b.id END, "
                    + ", ".join(f'b."{column}"' for column in _COLUMNS)
                    + f", {item.index}, COALESCE(a.allocation_proved,0), "
                    "CASE WHEN f.completion_proved THEN b.freeEventId END "
                    f'FROM src."block_{device}" b LEFT JOIN refs a ON a.id=b.allocEventId '
                    "LEFT JOIN refs f ON f.id=b.freeEventId WHERE 1 "
                    "ON CONFLICT(token) DO UPDATE SET "
                    f"invariant_conflict=lifecycle_state.invariant_conflict OR ({conflict}), "
                    "free_conflict=lifecycle_state.free_conflict OR "
                    "(lifecycle_state.known_free IS NOT NULL AND excluded.known_free IS NOT NULL "
                    "AND lifecycle_state.known_free IS NOT excluded.known_free), "
                    "known_free=COALESCE(lifecycle_state.known_free,excluded.known_free), " + updates  # nosec B608 # SQL structure uses validated integer IDs and fixed/allowlisted schema fragments; values are bound.
                )
        self.execute("PRAGMA query_only=ON")


def _lifecycle_cte(terminal):
    return f"""WITH latest AS (
        SELECT id,address,size,requestedSize,state,allocEventId,
            COALESCE(known_free,freeEventId) AS freeEventId,
            observation_slice_index,allocation_proved,token,
            known_free IS NOT NULL AS completion_proved,invariant_conflict,free_conflict
        FROM lifecycle_state
    ), lifecycles AS (
        SELECT *, (observation_slice_index={terminal} AND state IN (0,1)
            AND (freeEventId IS NULL OR freeEventId<0)) AS terminal_survivor
        FROM latest
    ) """  # nosec B608 # SQL structure uses validated integer IDs and fixed/allowlisted schema fragments; values are bound.


@contextmanager
def scratch_lifecycles(sources, items):
    maximum = sources.budget.max_scratch_db_bytes
    # pylint: disable-next=unidiomatic-typecheck  # Reject bool/subclasses: the contract requires exact scalar types.
    if type(maximum) is not int or not _PAGE_SIZE <= maximum <= _MAX_SCRATCH_BYTES:
        raise QueryExecutionError(
            f"Dataset lifecycle scratch limit {maximum!r} must be 0 (disabled) or between 4096 bytes "
            "and 4 GiB; this bounds derived database pages, not total temporary space or RSS."
        )
    try:
        with tempfile.TemporaryDirectory(prefix="pt-snap-lifecycle-") as directory:
            path = Path(directory) / "derived.db"
            descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            os.close(descriptor)
            database = _ScratchSources(sources, [], database=str(path))
            try:
                database.build(items, maximum)
                yield database, _lifecycle_cte(sources.device.slices[-1].index)
            finally:
                database.__exit__(None, None, None)
    except (OSError, sqlite3.Error) as exc:
        sources.budget.remaining()
        raise QueryExecutionError(
            "Dataset lifecycle scratch storage failed "
            f"(max_scratch_db_bytes={maximum}); no partial global result: {exc}"
        ) from exc
