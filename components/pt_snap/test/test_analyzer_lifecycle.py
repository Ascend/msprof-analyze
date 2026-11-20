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

"""Real SQLite connection lifetime contracts for API and short-lived CLI owners."""

import gc
import sqlite3
import warnings
from contextlib import closing
from pathlib import Path

import pytest
from typer.testing import CliRunner

from pt_snap_cli.api import SnapshotAnalyzer
from pt_snap_cli.cli import app
from pt_snap_cli.core import DatabaseSchemaError, QueryExecutionError, TemplateNotFoundError
from pt_snap_cli.core.analysis.overview_service import OverviewService
from pt_snap_cli.core.analysis.query_service import QueryService
from pt_snap_cli.core.cache.context_cache import ContextCache


@pytest.fixture(autouse=True)
def isolated_focus(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("PT_SNAP_DB_PATH", raising=False)
    monkeypatch.delenv("PT_SNAP_QUERY_TIMEOUT", raising=False)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)


@pytest.fixture
def db(tmp_path):
    path = tmp_path / "snapshot.db"
    with closing(sqlite3.connect(path)) as conn:
        conn.executescript(
            "CREATE TABLE dictionary (id INTEGER);"
            "CREATE TABLE trace_entry_0 (id INTEGER, active INTEGER, allocated INTEGER, "
            "reserved INTEGER, callstack TEXT);"
            "INSERT INTO trace_entry_0 VALUES (1, 0, 0, 0, '');"
            "CREATE TABLE block_0 (id INTEGER, address INTEGER, size INTEGER, "
            "requestedSize INTEGER, state INTEGER, allocEventId INTEGER, freeEventId INTEGER);"
        )
    return path


def assert_closed(conn):
    with pytest.raises(sqlite3.ProgrammingError, match="closed database"):
        conn.execute("SELECT 1")


@pytest.fixture
def connections(monkeypatch):
    """Observe actual handles, including ones never published to a cache."""
    opened = []
    original_connect = sqlite3.connect

    def connect(*args, **kwargs):
        conn = original_connect(*args, **kwargs)
        opened.append(conn)
        return conn

    monkeypatch.setattr(sqlite3, "connect", connect)
    yield opened
    try:
        for conn in opened:
            assert_closed(conn)
    finally:
        for conn in opened:
            conn.close()


@pytest.mark.parametrize("operation", ["query", "overview"])
def test_close_releases_real_cached_connection(db, connections, operation):
    analyzer = SnapshotAnalyzer(db)
    try:
        if operation == "query":
            analyzer.execute_query("memory_peak")
        else:
            analyzer.get_database_overview()
        ctx = analyzer.context_cache.get(db)
        with ctx.connect() as conn:
            assert conn.execute("SELECT 1").fetchone()[0] == 1
        analyzer.close()
        assert len(analyzer.context_cache) == 0
        assert_closed(conn)
        analyzer.close()
    finally:
        analyzer.close()


def test_with_reuses_query_overview_connection_then_closes_all_databases(db, connections, tmp_path):
    second_db = tmp_path / "second.db"
    second_db.write_bytes(db.read_bytes())
    analyzer = SnapshotAnalyzer(db)
    with analyzer as entered:
        assert entered is analyzer
        analyzer.execute_query("memory_peak")
        first_ctx = analyzer.context_cache.get(db)
        analyzer.get_database_overview()
        assert analyzer.context_cache.get(db) is first_ctx
        analyzer.get_database_overview(str(second_db))
        assert len(analyzer.context_cache) == 2
    assert len(analyzer.context_cache) == 0
    assert connections


@pytest.mark.parametrize("failure", ["body", "template", "sql", "schema", "overview"])
def test_exception_exit_closes_connections_without_suppressing_error(db, connections, failure):
    expected = {
        "body": RuntimeError,
        "template": TemplateNotFoundError,
        "sql": QueryExecutionError,
        "schema": ValueError,
        "overview": ValueError,
    }[failure]
    if failure in ("sql", "schema", "overview"):
        with closing(sqlite3.connect(db)) as conn:
            if failure == "sql":
                conn.execute("DROP TABLE block_0")
            elif failure == "schema":
                conn.execute("DROP TABLE dictionary")
            else:
                conn.execute("ALTER TABLE trace_entry_0 RENAME COLUMN id TO bad_id")
    analyzer = SnapshotAnalyzer(db)
    with pytest.raises(expected):
        with analyzer:
            if failure == "body":
                analyzer.get_database_overview()
                raise RuntimeError("body failed")
            if failure == "template":
                analyzer.execute_query("not_a_template")
            elif failure == "sql":
                analyzer.execute_query("leak_detection")
            else:
                analyzer.get_database_overview()
    assert len(analyzer.context_cache) == 0
    assert connections


@pytest.mark.parametrize(
    "method,args",
    [
        ("get_focus", ()),
        ("set_focus", ("missing.db",)),
        ("list_templates", ()),
        ("get_template_info", ("memory_peak",)),
        ("execute_query", ("memory_peak",)),
        ("list_capabilities", ()),
        ("get_database_overview", ()),
        ("get_database_metadata", ()),
        ("__enter__", ()),
    ],
)
def test_closed_analyzer_rejects_operations_without_opening_connections(db, connections, method, args):
    analyzer = SnapshotAnalyzer(db)
    analyzer.close()
    analyzer.close()
    with pytest.raises(RuntimeError, match="^SnapshotAnalyzer is closed\\.$"):
        getattr(analyzer, method)(*args)
    analyzer.invalidate_context_cache()
    assert len(analyzer.context_cache) == 0
    assert connections == []


@pytest.mark.parametrize("exception_exit", [False, True])
def test_borrower_close_preserves_other_analyzers_connection(db, connections, exception_exit):
    with closing(ContextCache()) as shared:
        with SnapshotAnalyzer(db, context_cache=shared) as second:
            first = SnapshotAnalyzer(db, context_cache=shared)
            assert first.context_cache is shared  # Even an initially empty cache is borrowed.
            try:
                with first:
                    first.execute_query("memory_peak")
                    second.execute_query("memory_peak")
                    ctx = shared.get(db)
                    with ctx.connect() as conn:
                        assert conn.execute("SELECT 1").fetchone()[0] == 1
                    if exception_exit:
                        raise LookupError("caller failed")
            except LookupError:
                assert exception_exit
            first.close()
            second.get_database_overview()
            second.execute_query("memory_peak")
            assert shared.get(db) is ctx
            assert conn.execute("SELECT 1").fetchone()[0] == 1
        assert len(shared) == 1
    assert_closed(conn)


@pytest.mark.parametrize("cleanup", ["invalidate_one", "invalidate_all", "public_close"])
def test_existing_cache_cleanup_allows_open_analyzer_to_resume(db, connections, cleanup):
    with SnapshotAnalyzer(db) as analyzer:
        analyzer.execute_query("memory_peak")
        old_ctx = analyzer.context_cache.get(db)
        with old_ctx.connect() as old_conn:
            pass
        if cleanup == "public_close":
            analyzer.context_cache.close()
        else:
            analyzer.invalidate_context_cache(db if cleanup == "invalidate_one" else None)
        assert_closed(old_conn)
        analyzer.execute_query("memory_peak")
        analyzer.get_database_overview()
        assert analyzer.context_cache.get(db) is not old_ctx


def test_explicit_invalidation_of_borrowed_cache_remains_available_after_close(db, connections):
    with closing(ContextCache()) as shared:
        with SnapshotAnalyzer(db, context_cache=shared) as first:
            first.get_database_overview()
        with SnapshotAnalyzer(db, context_cache=shared) as second:
            ctx = shared.get(db)
            with ctx.connect() as conn:
                pass
            first.invalidate_context_cache(db)
            assert_closed(conn)
            second.execute_query("memory_peak")
            assert shared.get(db) is not ctx


@pytest.mark.parametrize("service_type", [QueryService, OverviewService])
@pytest.mark.parametrize("borrowed", [False, True])
def test_service_cleanup_respects_ownership_and_allows_reuse(db, connections, service_type, borrowed):
    def run(service):
        if isinstance(service, QueryService):
            service.execute_query("memory_peak", db_path=db)
        else:
            service.inspect(db)

    with closing(ContextCache()) as shared:
        with closing(service_type(context_cache=shared if borrowed else None)) as service:
            run(service)
            service.close()
            service.close()
            if borrowed:
                assert len(shared) == 1
                with shared.get(db).connect() as conn:
                    assert conn.execute("SELECT 1").fetchone()[0] == 1
            else:
                for conn in connections:
                    assert_closed(conn)
            run(service)


@pytest.mark.parametrize("operation", ["query", "overview", "report"])
@pytest.mark.parametrize("failure", [False, True])
def test_cli_closes_short_lived_service_connections(db, connections, operation, failure):
    if failure:
        with closing(sqlite3.connect(db)) as conn:
            conn.execute("ALTER TABLE trace_entry_0 RENAME COLUMN id TO bad_id")
    commands = {
        "query": ["query", str(db), "--template-use", "memory_peak", "--json"],
        "overview": ["overview", str(db), "--json"],
        "report": ["report", "peak-memory", str(db), "--json"],
    }
    result = CliRunner().invoke(app, commands[operation])
    assert result.exit_code == (1 if failure else 0), result.output
    assert connections


def test_query_schema_failure_closes_connection_before_cache_publication(db, connections):
    with closing(sqlite3.connect(db)) as conn:
        conn.execute("DROP TABLE dictionary")
    with SnapshotAnalyzer(db) as analyzer:
        with pytest.raises(DatabaseSchemaError, match="dictionary"):
            analyzer.execute_query("memory_peak")
        assert len(analyzer.context_cache) == 0
        for conn in connections:
            assert_closed(conn)


@pytest.mark.parametrize("operation", ["query", "overview"])
def test_explicit_cleanup_is_resource_warning_free_on_collection(db, operation):
    # Python 3.13 reports unclosed SQLite connections during collection. Keep
    # this independent of the handle-tracking fixture so collection really runs.
    gc.collect()
    with warnings.catch_warnings(record=True) as recorded:
        warnings.simplefilter("always", ResourceWarning)
        with SnapshotAnalyzer(db) as analyzer:
            if operation == "query":
                analyzer.execute_query("memory_peak")
            else:
                analyzer.get_database_overview()
        del analyzer
        gc.collect()
    assert not [item for item in recorded if issubclass(item.category, ResourceWarning)]
