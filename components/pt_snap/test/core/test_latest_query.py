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

"""Latest-only coordination does not publish superseded or reset work."""

import sqlite3
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from threading import Event, Lock

import pytest

from pt_snap_cli.api import SnapshotAnalyzer
from pt_snap_cli.core.analysis.query_service import QueryService
from pt_snap_cli.core.common.errors import QueryCancelledError, QueryTimeoutError
from pt_snap_cli.core.common.latest_query import LatestQuery
from pt_snap_cli.core.common.validation_budget import validation_progress
from pt_snap_cli.core.dataset.dataset_sources import QueryBudget
from pt_snap_cli.query.config import QueryParameter, QueryTemplate
from pt_snap_cli.query.executor import QueryExecutor


@pytest.mark.parametrize("supplied_budget", [False, True])
def test_queued_tree_timeout_includes_wait_and_does_not_start_worker(monkeypatch, supplied_budget):
    now = [100.0]
    monkeypatch.setattr("pt_snap_cli.core.analysis.query_service.time.monotonic", lambda: now[0])
    waiting = Event()
    work = Lock()
    work.acquire()

    class ObservedLock:
        def acquire(self, *, timeout):
            waiting.set()
            return work.acquire(timeout=timeout)

        def release(self):
            work.release()

    def unexpected_worker(*args, **kwargs):
        pytest.fail("An expired queued request must not start its query worker")

    service = QueryService()
    service._frame_tree_queries._work = ObservedLock()
    monkeypatch.setattr(QueryService, "_execute_query", unexpected_worker)
    budget = QueryBudget(1.0, now[0]) if supplied_budget else None
    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            request = pool.submit(
                service.execute_query,
                "active_memory_frame_tree_at_event",
                timeout_s=1.0,
                _budget=budget,
            )
            try:
                assert waiting.wait(3)
                now[0] += 5.0
                # The caller returns while the old task still owns the lock.
                with pytest.raises(QueryTimeoutError):
                    request.result(timeout=3)
                assert work.locked()
                assert service._frame_tree_queries._active is None
            finally:
                work.release()
    finally:
        service.close()


def test_deadline_is_checked_after_acquiring_work_lock():
    queries = LatestQuery()
    checks = 0

    def remaining():
        nonlocal checks
        checks += 1
        if checks == 2:
            raise QueryTimeoutError("expired while acquiring lock")
        return 1.0

    with pytest.raises(QueryTimeoutError):
        with queries.run(remaining):
            pytest.fail("Expired work must not run")
    # Timeout releases the lock and does not poison a subsequent request.
    with queries.run():
        pass


def test_cancel_discards_result_and_next_query_can_run():
    queries = LatestQuery()
    with pytest.raises(QueryCancelledError):
        with queries.run() as cancelled:
            assert not cancelled()
            queries.cancel()
            assert cancelled()
    with queries.run() as cancelled:
        assert not cancelled()


def test_query_failure_does_not_poison_future_queries():
    queries = LatestQuery()
    with pytest.raises(ValueError):
        with queries.run():
            raise ValueError("query failed")
    with queries.run() as cancelled:
        assert not cancelled()


def test_queued_obsolete_request_is_skipped():
    queries = LatestQuery()
    entered = []
    queries._work.acquire()

    def run(number):
        with queries.run():
            entered.append(number)

    def wait_for_token(previous):
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            with queries._state:
                token = queries._active
            if token is not None and token is not previous:
                return token
            Event().wait(0.005)
        pytest.fail("The request did not register its cancellation token")

    with ThreadPoolExecutor(max_workers=2) as pool:
        try:
            first = pool.submit(run, 1)
            token = wait_for_token(None)
            second = pool.submit(run, 2)
            wait_for_token(token)
        finally:
            queries._work.release()
        with pytest.raises(QueryCancelledError):
            first.result(timeout=3)
        second.result(timeout=3)
    assert entered == [2]


def test_independent_services_do_not_cancel_each_other():
    first, second = LatestQuery(), LatestQuery()
    with first.run() as cancelled:
        with pytest.raises(QueryCancelledError):
            with second.run():
                second.cancel()
                assert not cancelled()


def test_cancellation_during_dataset_validation_preserves_error_and_cleans_handler():
    class Budget:
        def __init__(self):
            self.checks = 0

        def remaining(self):
            self.checks += 1
            if self.checks >= 3:
                raise QueryCancelledError("cancelled during validation")
            return None

    with closing(sqlite3.connect(":memory:")) as conn:
        with pytest.raises(QueryCancelledError, match="during validation"):
            with validation_progress(conn, Budget()):
                conn.execute(
                    "WITH RECURSIVE n(x) AS (VALUES(0) UNION ALL SELECT x+1 FROM n WHERE x<100000000) "
                    "SELECT SUM(x) FROM n"
                ).fetchall()
        assert conn.execute("SELECT 1").fetchone() == (1,)


@pytest.mark.parametrize("timeout", [0, 30])
def test_standalone_tree_interrupts_sql_and_preserves_runtime_templates(tmp_path, monkeypatch, timeout):
    path = tmp_path / "standalone.db"
    with closing(sqlite3.connect(path)) as conn:
        conn.executescript("CREATE TABLE dictionary (id INTEGER);CREATE TABLE trace_entry_0 (id INTEGER);")
    started = Event()
    execute = QueryExecutor.execute

    def observed(self, sql, *args, **kwargs):
        if "WITH RECURSIVE" in sql:
            started.set()
        return execute(self, sql, *args, **kwargs)

    monkeypatch.setattr(QueryExecutor, "execute", observed)
    template = "active_memory_frame_tree_at_event"
    with SnapshotAnalyzer(path) as analyzer, ThreadPoolExecutor(max_workers=2) as pool:
        source = analyzer._query_service._get_executor(analyzer.context_cache.get(path))
        source.register_template(
            QueryTemplate(
                name=template,
                parameters={"event_id": QueryParameter(name="event_id", type="int", required=True)},
                query="{% if event_id == 1 %}"
                "WITH RECURSIVE n(x) AS (VALUES(0) UNION ALL SELECT x+1 FROM n WHERE x<100000000) "
                "SELECT SUM(x) AS value FROM n"
                "{% else %}SELECT 7 AS value{% endif %}",
            )
        )
        old = pool.submit(analyzer.execute_query, template, {"event_id": 1}, timeout_s=timeout)
        assert started.wait(3)
        new = pool.submit(analyzer.execute_query, template, {"event_id": 2})
        with pytest.raises(QueryCancelledError):
            old.result(timeout=5)
        assert new.result(timeout=5)["rows"] == [{"value": 7}]
        assert analyzer.execute_query(template, {"event_id": 2})["rows"] == [{"value": 7}]
