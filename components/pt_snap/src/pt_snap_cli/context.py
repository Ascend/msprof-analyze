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

"""Database context management for PyTorch memory snapshots."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Dict, Generator, List, Set, Tuple, Union
from urllib.parse import quote

from typing_extensions import Literal

CallstackLayout = Literal["v1", "v2"]
_METADATA_TABLE = "pt_snap_metadata"


class DatabaseNotFoundError(FileNotFoundError):
    """Raised when database file does not exist."""

    pass


class SchemaVersionError(ValueError):
    """Raised when database schema is invalid or incompatible."""

    pass


class Context:
    """Database context manager for PyTorch memory snapshot analysis.

    Manages SQLite database connections in read-only mode with schema validation.

    By default the underlying SQLite connection is opened and closed for every
    ``connect()`` context. Pass ``persistent=True`` to keep the connection
    alive across calls so that long-lived owners (e.g. a ``ContextCache``
    shared by a long-lived SnapshotAnalyzer) can avoid the per-query open/close cost.
    Persistent contexts still close their connection when ``close()`` is
    invoked explicitly.
    """

    def __init__(
        self,
        db_path: Union[str, Path],
        devices: Union[List[int], None] = None,
        *,
        persistent: bool = False,
        immutable: bool = False,
    ):
        """Initialize context with database path.

        Args:
            db_path: Path to the SQLite database file.
            devices: Optional list of device IDs to filter.
            immutable: Internal opt-in for a closed, finalized compatibility
                dataset after ALL member/parent/sidecar checks. Never use this
                to read a live WAL or as a concurrency/sandbox guarantee. The
                standalone default remains mode=ro without immutable.
            persistent: When True, the connection stays open after each
                ``connect()`` call so it can be reused. The caller is
                responsible for invoking ``close()`` to release it.

        Raises:
            DatabaseNotFoundError: If database file does not exist.
            SchemaVersionError: If database schema is invalid.
        """
        self.db_path = Path(db_path)
        self._devices = devices
        self._persistent = persistent
        # Opt-in only after dataset-wide finalized-member checks. Standalone
        # analysis keeps mode=ro without immutable and its existing WAL behavior.
        self._immutable = immutable
        self._conn: Union[sqlite3.Connection, None] = None
        self._connect_depth = 0
        self._device_ids: Union[List[int], None] = None
        self._callstack_layout: Union[CallstackLayout, None] = None
        self._callstack_layout_error: Union[str, None] = None

        if not self.db_path.exists():
            raise DatabaseNotFoundError(f"Database not found: {self.db_path}")

        try:
            self._validate_schema()
        except BaseException:
            # A failed constructor never reaches its owner's cache. Release
            # even a persistent connection before propagating the failure.
            self.close()
            raise

    def _validate_schema(self) -> None:
        """Validate database has required schema (dictionary table)."""
        with self.connect() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='dictionary'")
            if not cursor.fetchone():
                raise SchemaVersionError(
                    "Invalid database schema: 'dictionary' table not found. "
                    "This may not be a valid PyTorch memory snapshot database."
                )
            self._callstack_layout, self._callstack_layout_error = self._detect_callstack_layout(conn)

    @property
    def callstack_layout(self) -> Union[CallstackLayout, None]:
        """Return the detected callstack schema, or None when it is unrecognized.

        ``v1`` is inline ``callstack`` text on each ``trace_entry_<device>``
        table. ``v2`` stores ``callstackId`` and a shared ``callstack`` table.
        Detection is read-only and cached on this context; it is not written
        to focus files. Conflicting or damaged layouts leave this ``None`` and
        set :attr:`callstack_layout_error` instead of failing construction.
        """
        return self._callstack_layout

    @property
    def callstack_layout_error(self) -> Union[str, None]:
        """Return a layout conflict reason, or None when none was detected."""
        return self._callstack_layout_error

    def _detect_callstack_layout(
        self, conn: sqlite3.Connection
    ) -> Tuple[Union[CallstackLayout, None], Union[str, None]]:
        """Identify v1/v2 callstack layout from table columns and metadata."""
        cursor = conn.cursor()
        layouts: Dict[int, CallstackLayout] = {}
        unrecognized: List[int] = []
        for device_id, table_name in _trace_entry_tables(cursor):
            columns = _table_columns(cursor, table_name)
            has_id = "callstackid" in columns
            has_text = "callstack" in columns
            if has_id and has_text:
                return None, (
                    f"Incompatible callstack layout: '{table_name}' has both callstack and callstackId columns."
                )
            if has_id:
                layouts[device_id] = "v2"
            elif has_text:
                layouts[device_id] = "v1"
            else:
                unrecognized.append(device_id)

        if layouts and unrecognized:
            return None, (
                "Incompatible callstack layout: some devices have a recognized "
                "callstack schema but others do not "
                f"(unrecognized devices: {unrecognized})."
            )

        distinct = set(layouts.values())
        if len(distinct) > 1:
            return None, (f"Incompatible callstack layout: devices disagree ({', '.join(sorted(distinct))}).")

        layout = next(iter(distinct), None)
        callstack_table = _find_table(cursor, "callstack")
        if layout == "v1" and callstack_table is not None:
            return None, (
                "Incompatible callstack layout: inline callstack text coexists with a shared callstack table."
            )
        if layout == "v2":
            if callstack_table is None:
                return None, (
                    "Incompatible callstack layout: callstackId is present but the shared callstack table is missing."
                )
            callstack_columns = _table_columns(cursor, callstack_table)
            if not {"id", "callstack"}.issubset(callstack_columns):
                return None, (
                    "Incompatible callstack layout: shared callstack table is missing id or callstack columns."
                )

        metadata_version = _import_format_version(cursor)
        if metadata_version in (1, 2, 3):
            expected: CallstackLayout = "v1" if metadata_version == 1 else "v2"
            if layout is None:
                return None, (
                    "Incompatible callstack layout: "
                    f"pt_snap_metadata.import_format_version is {metadata_version} "
                    "but the database structure is unrecognized."
                )
            if layout != expected:
                return None, (
                    "Incompatible callstack layout: "
                    f"pt_snap_metadata.import_format_version is {metadata_version} "
                    f"but the database structure is {layout}."
                )

        return layout, None

    @property
    def device_ids(self) -> List[int]:
        """Get list of device IDs available in the database."""
        if self._device_ids is None:
            self._device_ids = self._discover_device_ids()
        return self._device_ids

    def discover_devices(self) -> List[int]:
        """Discover device IDs available in the database.

        Method-style alias of the ``device_ids`` property, exposed for
        callers (e.g. import service) that prefer an explicit method.
        """
        return self.device_ids

    def device_trace_bounds(self) -> List[Tuple[int, Union[int, None], Union[int, None]]]:
        """Return ``(device_id, first_event_id, last_event_id)`` for each device.

        Bounds come from nonnegative real IDs on ``trace_entry_<device>``.
        Negative synthetic boundary rows do not extend the real trace.
        Empty tables report ``None`` for both ends. The connection stays
        read-only (``mode=ro``).
        """
        bounds: List[Tuple[int, Union[int, None], Union[int, None]]] = []
        with self.connect() as conn:
            cursor = conn.cursor()
            for device_id in self.device_ids:
                table = f"trace_entry_{device_id}"
                cursor.execute(f"SELECT MIN(id), MAX(id) FROM {_quote_ident(table)} WHERE id >= 0")  # nosec B608 # Identifiers pass through _quote_ident; no unquoted user value is inserted.
                row = cursor.fetchone()
                first = int(row[0]) if row is not None and row[0] is not None else None
                last = int(row[1]) if row is not None and row[1] is not None else None
                bounds.append((device_id, first, last))
        return bounds

    def _discover_device_ids(self) -> List[int]:
        """Discover device IDs from database table names."""
        device_ids = set()
        with self.connect() as conn:
            for device_id, _table_name in _trace_entry_tables(conn.cursor()):
                if self._devices is None or device_id in self._devices:
                    device_ids.add(device_id)
        return sorted(device_ids)

    def cursor(self) -> sqlite3.Cursor:
        """Get a database cursor.

        Returns:
            SQLite cursor for database operations.

        Raises:
            RuntimeError: If database is not connected.
        """
        if self._conn is None:
            raise RuntimeError("Database not connected. Use connect() context manager.")
        return self._conn.cursor()

    @contextmanager
    def connect(self) -> Generator[sqlite3.Connection, None, None]:
        """Context manager for database connection.

        Opens database in read-only mode for safe analysis. When the
        context was constructed with ``persistent=True`` the underlying
        SQLite connection remains open after the context exits and is
        reused by subsequent ``connect()`` calls until ``close()`` is
        invoked explicitly.

        Yields:
            SQLite connection object.
        """
        if self._conn is None:
            # Keep the colon in Windows drive prefixes while encoding SQLite URI metacharacters.
            encoded_path = quote(self.db_path.as_posix(), safe="/:")
            uri = f"file:{encoded_path}?mode=ro"
            if self._immutable:
                uri += "&immutable=1"
            self._conn = sqlite3.connect(uri, uri=True)
            self._conn.row_factory = sqlite3.Row

        self._connect_depth += 1
        try:
            yield self._conn
        finally:
            if self._connect_depth > 0:
                self._connect_depth -= 1
            if not self._persistent and self._connect_depth == 0:
                self.close()

    def close(self) -> None:
        """Close the database connection.

        Safe to call multiple times and on already-closed contexts.
        """
        if self._conn is not None:
            self._conn.close()
            self._conn = None
        self._connect_depth = 0


def _quote_ident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def _find_table(cursor: sqlite3.Cursor, name: str) -> Union[str, None]:
    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=? COLLATE NOCASE",
        (name,),
    )
    row = cursor.fetchone()
    return str(row[0]) if row is not None else None


def _has_table(cursor: sqlite3.Cursor, name: str) -> bool:
    return _find_table(cursor, name) is not None


def _table_columns(cursor: sqlite3.Cursor, table_name: str) -> Set[str]:
    cursor.execute(f"PRAGMA table_info({_quote_ident(table_name)})")
    return {str(row[1]).lower() for row in cursor.fetchall()}


def _trace_entry_tables(cursor: sqlite3.Cursor) -> List[Tuple[int, str]]:
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'trace_entry_%'")
    tables: List[Tuple[int, str]] = []
    for row in cursor.fetchall():
        table_name = row[0]
        suffix = table_name.rsplit("_", 1)[-1]
        try:
            tables.append((int(suffix), table_name))
        except ValueError:
            continue
    return tables


def _import_format_version(cursor: sqlite3.Cursor) -> Union[int, None]:
    metadata_table = _find_table(cursor, _METADATA_TABLE)
    if metadata_table is None:
        return None
    columns = _table_columns(cursor, metadata_table)
    if "import_format_version" not in columns:
        return None
    try:
        rows = cursor.execute(f"SELECT import_format_version FROM {_quote_ident(metadata_table)}").fetchall()  # nosec B608 # Identifiers pass through _quote_ident; no unquoted user value is inserted.
    except sqlite3.DatabaseError:
        return None
    if len(rows) != 1:
        return None
    try:
        return int(rows[0][0])
    except (TypeError, ValueError):
        return None
