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

"""Many-owner lifecycle queries retain exact semantics and bounded private storage."""

import contextlib
import hashlib
import os
import sqlite3
import time
from pathlib import Path

import pytest

from pt_snap_cli.core.common.errors import QueryExecutionError, QueryTimeoutError
from pt_snap_cli.core.dataset.dataset_resolver import DatasetResolver
from pt_snap_cli.core.dataset.dataset_sources import QueryBudget
from pt_snap_cli.core.dataset.lifecycle import dataset_lifecycle_scratch as scratch
from pt_snap_cli.core.dataset.lifecycle import dataset_lifecycle_sql
from test.core.test_dataset_sql_pushdown import run_resolved
from test.test_dataset_focus import make_dataset


def many_owners(tmp_path):
    root = make_dataset(tmp_path / "many", devices=(0,), slices=12)
    with contextlib.closing(sqlite3.connect(root / "device_0/slice_00011.db")) as conn, conn:
        conn.executemany(
            "INSERT INTO block_0 VALUES (?,?,8,8,1,?,-1)",
            ((i, 100 + i * 8, i) for i in range(24)),
        )
    return root


def limited_connections(monkeypatch, limit):
    if not hasattr(sqlite3.Connection, "setlimit"):
        pytest.skip("Real per-connection SQLite limits require Python 3.11+")
    original = sqlite3.connect

    def connect(*args, **kwargs):
        connection = original(*args, **kwargs)
        connection.setlimit(sqlite3.SQLITE_LIMIT_ATTACHED, limit)
        return connection

    monkeypatch.setattr(sqlite3, "connect", connect)


def capture_storage(monkeypatch, tmp_path):
    parent = tmp_path / "scratch"
    parent.mkdir()
    original = scratch.tempfile.TemporaryDirectory
    created = []

    def directory(*args, **kwargs):
        result = original(*args, dir=parent, **kwargs)
        created.append(Path(result.name))
        return result

    monkeypatch.setattr(scratch.tempfile, "TemporaryDirectory", directory)
    return parent, created


@pytest.mark.parametrize("limit", [1, 2])
@pytest.mark.parametrize("template", ["block", "leak_detection", "freed_block_lifetime"])
@pytest.mark.parametrize("slice_index", [None, 11])
def test_real_attach_limit_and_many_proof_owners(tmp_path, monkeypatch, limit, template, slice_index):
    if template == "leak_detection" and slice_index is not None:
        pytest.skip("Slice leak query is intentionally unsupported")
    root = many_owners(tmp_path)
    resolved = DatasetResolver().inspect(root)
    expected = run_resolved(
        resolved,
        template,
        slice_index=slice_index,
        budget=QueryBudget(None, time.monotonic(), max_scratch_db_bytes=0),
    )
    hashes = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in root.rglob("*.db")}
    limited_connections(monkeypatch, limit)
    parent, created = capture_storage(monkeypatch, tmp_path)
    original = scratch._ScratchSources.build
    observed = []

    def build(database, items, maximum):
        original(database, items, maximum)
        path = Path(database.connection.execute("PRAGMA database_list").fetchone()[2])
        observed.append(database.connection)
        # Windows exposes read-only flags, not POSIX permission bits. The
        # actual route, byte bound and handle/temporary cleanup run everywhere.
        if os.name != "nt":
            assert os.stat(path.parent).st_mode & 0o777 == 0o700
            assert os.stat(path).st_mode & 0o777 == 0o600
        assert path.stat().st_size <= maximum
        assert database.connection.getlimit(sqlite3.SQLITE_LIMIT_ATTACHED) == limit

    monkeypatch.setattr(scratch._ScratchSources, "build", build)
    budget = QueryBudget(None, time.monotonic(), max_work_rows=128)
    actual = run_resolved(resolved, template, slice_index=slice_index, budget=budget)
    assert actual.rows == expected.rows
    assert (actual.total, actual.has_more) == (expected.total, expected.has_more)
    assert {k: v for k, v in actual.scope["source_coverage"].items() if k != "source_queries"} == {
        k: v for k, v in expected.scope["source_coverage"].items() if k != "source_queries"
    }
    assert created and not list(parent.iterdir())
    assert all(not path.exists() for path in created)
    for connection in observed:
        with pytest.raises(sqlite3.ProgrammingError, match="closed"):
            connection.execute("SELECT 1")
    assert {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in hashes} == hashes
    assert not any(root.rglob("*-journal"))
    assert budget.work_rows <= 128


@pytest.mark.parametrize("maximum", [-1, 1, 4095, 4 * 1024**3 + 1, True, 1.5])
def test_invalid_scratch_budget_is_domain_error(tmp_path, maximum):
    resolved = DatasetResolver().inspect(many_owners(tmp_path))
    with pytest.raises(QueryExecutionError, match="scratch limit"):
        run_resolved(
            resolved,
            "block",
            budget=QueryBudget(None, time.monotonic(), max_scratch_db_bytes=maximum),
        )


def test_actual_page_limit_failure_cleans_private_storage(tmp_path, monkeypatch):
    resolved = DatasetResolver().inspect(many_owners(tmp_path))
    parent, created = capture_storage(monkeypatch, tmp_path)
    with pytest.raises(QueryExecutionError, match="scratch space exhausted"):
        run_resolved(resolved, "block", budget=QueryBudget(None, time.monotonic(), max_scratch_db_bytes=4096))
    assert created and not list(parent.iterdir())


@pytest.mark.parametrize(
    "phase", ["INSERT OR IGNORE", "UPDATE refs", "INSERT INTO lifecycle_state", "PRAGMA query_only"]
)
@pytest.mark.parametrize("failure", [QueryTimeoutError("expired"), KeyboardInterrupt(), OSError("full")])
def test_phase_failures_leave_no_storage_or_connection(tmp_path, monkeypatch, phase, failure):
    resolved = DatasetResolver().inspect(many_owners(tmp_path))
    parent, created = capture_storage(monkeypatch, tmp_path)
    original = scratch._ScratchSources.execute
    connections = []

    def execute(database, sql, values=()):
        if sql.startswith(phase):
            connections.append(database.connection)
            raise failure
        return original(database, sql, values)

    monkeypatch.setattr(scratch._ScratchSources, "execute", execute)
    expected = QueryExecutionError if isinstance(failure, OSError) else type(failure)
    with pytest.raises(expected):
        run_resolved(resolved, "block")
    assert created and not list(parent.iterdir())
    for connection in connections:
        with pytest.raises(sqlite3.ProgrammingError, match="closed"):
            connection.execute("SELECT 1")


def test_disabled_scratch_preserves_fetched_work_budget(tmp_path, monkeypatch):
    resolved = DatasetResolver().inspect(many_owners(tmp_path))
    monkeypatch.setattr(scratch, "scratch_lifecycles", lambda *args: pytest.fail("disabled"))
    with pytest.raises(QueryExecutionError, match="work budget"):
        run_resolved(
            resolved,
            "block",
            budget=QueryBudget(None, time.monotonic(), max_work_rows=3, max_scratch_db_bytes=0),
        )


def test_shared_deadline_expires_during_build_and_cleans_up(tmp_path, monkeypatch):
    resolved = DatasetResolver().inspect(many_owners(tmp_path))
    parent, created = capture_storage(monkeypatch, tmp_path)
    original = scratch._ScratchSources.execute

    def execute(database, sql, values=()):
        if sql.startswith("UPDATE refs"):
            database.sources.budget.started -= 10
        return original(database, sql, values)

    monkeypatch.setattr(scratch._ScratchSources, "execute", execute)
    with pytest.raises(QueryTimeoutError):
        run_resolved(resolved, "block", budget=QueryBudget(5, time.monotonic()))
    assert created and not list(parent.iterdir())


def test_scratch_source_writes_rejected_while_main_is_writable(tmp_path, monkeypatch):
    resolved = DatasetResolver().inspect(many_owners(tmp_path))
    original = scratch._ScratchSources.source
    visited = []

    @contextlib.contextmanager
    def source(database, item):
        with original(database, item):
            with pytest.raises(sqlite3.DatabaseError, match="authorized|readonly"):
                database.connection.execute("DELETE FROM src.block_0")
            visited.append(item.index)
            yield

    monkeypatch.setattr(scratch._ScratchSources, "source", source)
    run_resolved(resolved, "block")
    assert len(set(visited)) == 12


@pytest.mark.parametrize("variant", ["earlier_free", "null_invariant", "wrong_action", "same_slice_tie"])
@pytest.mark.parametrize("template", ["block", "leak_detection", "freed_block_lifetime"])
@pytest.mark.parametrize("routing", ["attachment_limit", "observation_count"])
def test_scratch_semantics_match_attached_path(tmp_path, monkeypatch, variant, template, routing):
    from test.core.test_dataset_attribution import case
    from test.core.test_dataset_sql_pushdown import last_observation

    root = case(tmp_path, devices=(0,))
    # Mutate after admission to exercise reducer defenses independently of validation.
    resolved = DatasetResolver().inspect(root)
    if variant == "earlier_free":
        with contextlib.closing(sqlite3.connect(last_observation(root, 0))) as conn, conn:
            conn.execute("UPDATE block_0 SET state=0,freeEventId=-1 WHERE id=0")
    elif variant == "null_invariant":
        for path in root.glob("device_0/*.db"):
            with contextlib.closing(sqlite3.connect(path)) as conn, conn:
                conn.execute("UPDATE block_0 SET requestedSize=NULL WHERE id=0")
    elif variant == "wrong_action":
        for path in root.glob("device_0/*.db"):
            with contextlib.closing(sqlite3.connect(path)) as conn, conn:
                conn.execute("UPDATE trace_entry_0 SET action=5 WHERE id=0")
    else:
        with contextlib.closing(sqlite3.connect(last_observation(root, 0))) as conn, conn:
            conn.execute(
                "INSERT INTO block_0 SELECT 900,address,size,requestedSize,0,allocEventId,freeEventId "
                "FROM block_0 WHERE id=0"
            )
    params = {"offset": 1, "limit": 3} if template == "block" else {}
    expected = run_resolved(resolved, template, params)
    if routing == "attachment_limit":
        limited_connections(monkeypatch, 1)
    else:
        monkeypatch.setattr(dataset_lifecycle_sql, "_ATTACHED_OBSERVATION_LIMIT", 0)
    actual = run_resolved(resolved, template, params)
    assert actual.rows == expected.rows
    assert (actual.total, actual.has_more) == (expected.total, expected.has_more)


@pytest.mark.parametrize("variant", ["invariant", "null", "free"])
@pytest.mark.parametrize("params", [{"id": 7}, {"limit": 0}, {"offset": 100}])
@pytest.mark.parametrize("routing", ["attachment_limit", "observation_count"])
@pytest.mark.parametrize("exact_total", [False, True])
def test_scratch_conflicts_outside_page_still_fail(tmp_path, monkeypatch, variant, params, routing, exact_total):
    from test.core.test_dataset_attribution import case
    from test.core.test_dataset_sql_pushdown import last_observation

    root = case(tmp_path, devices=(0,))
    # Mutate after admission to exercise reducer defenses independently of validation.
    resolved = DatasetResolver().inspect(root)
    with contextlib.closing(sqlite3.connect(last_observation(root, 0))) as conn, conn:
        if variant == "invariant":
            conn.execute("UPDATE block_0 SET size=size+1 WHERE id=0")
        elif variant == "null":
            conn.execute("UPDATE block_0 SET requestedSize=NULL WHERE id=0")
        else:
            conn.execute("UPDATE block_0 SET freeEventId=4 WHERE id=0")
    if variant == "free":
        for path in root.glob("device_0/*.db"):
            with contextlib.closing(sqlite3.connect(path)) as conn, conn:
                conn.execute("UPDATE trace_entry_0 SET action=6 WHERE id=4")
    with pytest.raises(QueryExecutionError, match="Conflicting"):
        run_resolved(resolved, "block", params, exact_total=exact_total)
    if routing == "attachment_limit":
        limited_connections(monkeypatch, 1)
    else:
        monkeypatch.setattr(dataset_lifecycle_sql, "_ATTACHED_OBSERVATION_LIMIT", 0)
    with pytest.raises(QueryExecutionError, match="Conflicting"):
        run_resolved(resolved, "block", params, exact_total=exact_total)


@pytest.mark.parametrize("stage", ["open", "detach"])
def test_setup_or_detach_sqlite_failure_cleans_storage(tmp_path, monkeypatch, stage):
    resolved = DatasetResolver().inspect(many_owners(tmp_path))
    parent, created = capture_storage(monkeypatch, tmp_path)
    original = sqlite3.connect
    connections = []

    class DetachFailure(sqlite3.Connection):
        def execute(self, sql, parameters=()):
            if sql == "DETACH DATABASE src":
                raise sqlite3.OperationalError("injected detach failure")
            return super().execute(sql, parameters)

    def connect(path, *args, **kwargs):
        if str(path).endswith("derived.db"):
            if stage == "open":
                raise sqlite3.OperationalError("injected open failure")
            kwargs["factory"] = DetachFailure
            connection = original(path, *args, **kwargs)
            connections.append(connection)
            return connection
        return original(path, *args, **kwargs)

    monkeypatch.setattr(sqlite3, "connect", connect)
    with pytest.raises(QueryExecutionError, match=f"injected {stage} failure"):
        run_resolved(resolved, "block")
    assert created and not list(parent.iterdir())
    for connection in connections:
        with pytest.raises(sqlite3.ProgrammingError, match="closed"):
            connection.execute("SELECT 1")


@pytest.mark.parametrize("failure", ["rows", "bytes", "timeout", "cancel", "io"])
def test_result_phase_failure_preserves_sources_cleans_storage_and_allows_retry(tmp_path, monkeypatch, failure):
    """Exercise failure after construction, while the scratch owner is yielded."""
    root = many_owners(tmp_path)
    resolved = DatasetResolver().inspect(root)
    expected = run_resolved(resolved, "block")
    hashes = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in root.rglob("*.db")}
    parent, created = capture_storage(monkeypatch, tmp_path)
    original_build = scratch._ScratchSources.build
    original_read = scratch._ScratchSources.read
    connections = []
    ready = set()

    def build(database, items, maximum):
        original_build(database, items, maximum)
        connections.append(database.connection)
        ready.add(id(database))
        budget = database.sources.budget
        if failure == "rows":
            budget.max_work_rows = budget.work_rows
        elif failure == "bytes":
            budget.max_work_bytes = budget.work_bytes
        elif failure == "timeout":
            budget.timeout_s = 1
            budget.started = time.monotonic() - 2

    def read(database, sql, values=None):
        if id(database) in ready:
            if failure == "cancel":
                raise KeyboardInterrupt()
            if failure == "io":
                raise sqlite3.OperationalError("injected result read I/O failure")
        return original_read(database, sql, values)

    with monkeypatch.context() as fault:
        fault.setattr(scratch._ScratchSources, "build", build)
        fault.setattr(scratch._ScratchSources, "read", read)
        error, message = {
            "rows": (QueryExecutionError, "work budget exceeded"),
            "bytes": (QueryExecutionError, "work budget exceeded"),
            "timeout": (QueryTimeoutError, "timed out"),
            "cancel": (KeyboardInterrupt, "^$"),
            "io": (QueryExecutionError, "result read I/O failure"),
        }[failure]
        with pytest.raises(error, match=message):
            run_resolved(resolved, "block")

    assert len(connections) == 1
    with pytest.raises(sqlite3.ProgrammingError, match="closed"):
        connections[0].execute("SELECT 1")
    assert created and not list(parent.iterdir())
    assert all(not path.exists() for path in created)
    assert {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in hashes} == hashes
    assert not any(root.rglob("*-journal"))
    assert not any(root.rglob("*-wal"))
    assert not any(root.rglob("*-shm"))

    retried = run_resolved(resolved, "block")
    assert retried.rows == expected.rows
    assert (retried.total, retried.has_more) == (expected.total, expected.has_more)
    assert len(created) == 2 and not list(parent.iterdir())
    assert {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in hashes} == hashes
