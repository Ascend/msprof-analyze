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

"""Tests for the LRU Context cache that powers connection reuse."""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

import pytest

from pt_snap_cli.context import Context, DatabaseNotFoundError, SchemaVersionError
from pt_snap_cli.core.cache.context_cache import ContextCache


def _make_db(tmp_path: Path, name: str = "sample.db") -> Path:
    db_path = tmp_path / name
    conn = sqlite3.connect(str(db_path))
    conn.execute("CREATE TABLE dictionary (`table` TEXT, `column` TEXT, `key` TEXT, `value` TEXT)")
    conn.execute("CREATE TABLE trace_entry_0 (id INTEGER PRIMARY KEY, size INTEGER)")
    conn.execute("INSERT INTO trace_entry_0 (size) VALUES (1), (2), (3)")
    conn.commit()
    conn.close()
    return db_path


def _make_invalid_db(tmp_path: Path, name: str = "invalid.db") -> Path:
    db_path = tmp_path / name
    conn = sqlite3.connect(str(db_path))
    conn.execute("CREATE TABLE other (id INTEGER PRIMARY KEY)")
    conn.commit()
    conn.close()
    return db_path


class TestContextCache:
    def test_get_creates_context(self, tmp_path: Path, request) -> None:
        db_path = _make_db(tmp_path)
        cache = ContextCache(maxsize=4)
        request.addfinalizer(cache.close)

        ctx = cache.get(db_path)

        assert isinstance(ctx, Context)
        assert ctx.db_path == db_path.resolve()
        assert ctx.device_ids == [0]
        assert len(cache) == 1

    def test_get_returns_cached_context_on_second_call(self, tmp_path: Path, request) -> None:
        db_path = _make_db(tmp_path)
        cache = ContextCache(maxsize=4)
        request.addfinalizer(cache.close)

        first = cache.get(db_path)
        second = cache.get(db_path)

        assert first is second
        assert len(cache) == 1

    def test_get_raises_for_missing_file(self, tmp_path: Path) -> None:
        cache = ContextCache(maxsize=4)
        missing = tmp_path / "missing.db"

        with pytest.raises(DatabaseNotFoundError):
            cache.get(missing)

        # A failed get must not leave a stale entry behind.
        assert len(cache) == 0

    def test_get_propagates_schema_errors(self, tmp_path: Path) -> None:
        bad_db = _make_invalid_db(tmp_path)
        cache = ContextCache(maxsize=4)

        with pytest.raises(SchemaVersionError):
            cache.get(bad_db)

    def test_same_mtime_replacement_refreshes_cached_context(self, tmp_path: Path, request) -> None:
        """Replacing a database with the same mtime must refresh its context."""
        db_path = _make_db(tmp_path)
        cache = ContextCache(maxsize=4)
        request.addfinalizer(cache.close)
        first = cache.get(db_path)
        original_stat = db_path.stat()

        replacement = tmp_path / "same-mtime.db"
        conn = sqlite3.connect(str(replacement))
        conn.execute("CREATE TABLE dictionary (`table` TEXT, `column` TEXT, `key` TEXT, `value` TEXT)")
        conn.execute("CREATE TABLE trace_entry_1 (id INTEGER PRIMARY KEY, size INTEGER)")
        conn.commit()
        conn.close()
        os.utime(replacement, ns=(original_stat.st_atime_ns, original_stat.st_mtime_ns))
        if os.name == "nt":
            # Windows forbids replacing an open SQLite file. Release the handle
            # but retain the cache entry so signature invalidation is still tested.
            first.close()
        os.replace(replacement, db_path)

        second = cache.get(db_path)

        assert second is not first
        assert second.device_ids == [1]

    def test_replaced_database_redetects_callstack_layout(self, tmp_path: Path, request) -> None:
        db_path = tmp_path / "layout.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute("CREATE TABLE dictionary (`table` TEXT, `column` TEXT, `key` TEXT, `value` TEXT)")
        conn.execute("CREATE TABLE trace_entry_0 (id INTEGER PRIMARY KEY, callstack TEXT)")
        conn.commit()
        conn.close()

        cache = ContextCache(maxsize=4)
        request.addfinalizer(cache.close)
        first = cache.get(db_path)
        assert first.callstack_layout == "v1"

        replacement = tmp_path / "v2.db"
        conn = sqlite3.connect(str(replacement))
        conn.execute("CREATE TABLE dictionary (`table` TEXT, `column` TEXT, `key` TEXT, `value` TEXT)")
        conn.execute("CREATE TABLE callstack (id INTEGER PRIMARY KEY, callstack TEXT)")
        conn.execute("CREATE TABLE trace_entry_0 (id INTEGER PRIMARY KEY, callstackId INTEGER)")
        conn.commit()
        conn.close()
        if os.name == "nt":
            # Windows forbids replacing an open SQLite file. Release the handle
            # but retain the cache entry so signature invalidation is still tested.
            first.close()
        os.replace(replacement, db_path)

        second = cache.get(db_path)
        assert second is not first
        assert second.callstack_layout == "v2"

    def test_invalidate_path_drops_entry(self, tmp_path: Path, request) -> None:
        db_path = _make_db(tmp_path)
        cache = ContextCache(maxsize=4)
        request.addfinalizer(cache.close)
        ctx = cache.get(db_path)
        assert len(cache) == 1

        cache.invalidate(db_path)

        assert len(cache) == 0
        # Re-fetching creates a new Context.
        new_ctx = cache.get(db_path)
        assert new_ctx is not ctx

    def test_invalidate_all_drops_every_entry(self, tmp_path: Path) -> None:
        db1 = _make_db(tmp_path, "a.db")
        db2 = _make_db(tmp_path, "b.db")
        cache = ContextCache(maxsize=4)
        cache.get(db1)
        cache.get(db2)
        assert len(cache) == 2

        cache.invalidate()
        assert len(cache) == 0

    def test_lru_eviction(self, tmp_path: Path, request) -> None:
        cache = ContextCache(maxsize=2)
        request.addfinalizer(cache.close)
        db_a = _make_db(tmp_path, "a.db")
        db_b = _make_db(tmp_path, "b.db")
        db_c = _make_db(tmp_path, "c.db")

        ctx_a = cache.get(db_a)
        ctx_b = cache.get(db_b)

        # Touching db_a promotes it; inserting db_c should evict db_b.
        ctx_a_again = cache.get(db_a)
        cache.get(db_c)

        assert ctx_a is ctx_a_again
        assert len(cache) == 2
        # db_b was evicted: a fresh fetch must return a brand new Context.
        ctx_b_new = cache.get(db_b)
        assert ctx_b_new is not ctx_b

    def test_maxsize_must_be_positive(self) -> None:
        with pytest.raises(ValueError):
            ContextCache(maxsize=0)
        with pytest.raises(ValueError):
            ContextCache(maxsize=-1)


class TestPersistentContext:
    def test_persistent_context_keeps_connection_alive(self, tmp_path: Path) -> None:
        db_path = _make_db(tmp_path)
        ctx = Context(db_path, persistent=True)

        with ctx.connect() as conn:
            assert conn is not None
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM trace_entry_0")
            assert cursor.fetchone()[0] == 3

        # Connection must still be open; a second connect() reuses it.
        assert ctx._conn is not None
        with ctx.connect() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM trace_entry_0")
            assert cursor.fetchone()[0] == 3

        ctx.close()
        assert ctx._conn is None

    def test_non_persistent_context_closes_after_block(self, tmp_path: Path) -> None:
        """Default behaviour is unchanged: the connection closes when the
        ``connect()`` context exits so the existing Context contract is
        preserved.
        """
        db_path = _make_db(tmp_path)
        ctx = Context(db_path)

        with ctx.connect():
            assert ctx._conn is not None
        assert ctx._conn is None

    def test_nested_non_persistent_connect_closes_after_outer_block(self, tmp_path: Path) -> None:
        db_path = _make_db(tmp_path)
        ctx = Context(db_path)

        with ctx.connect() as outer:
            with ctx.connect() as inner:
                assert inner is outer
                inner.execute("SELECT 1")
            outer.execute("SELECT 1")
            assert ctx._conn is not None

        assert ctx._conn is None
