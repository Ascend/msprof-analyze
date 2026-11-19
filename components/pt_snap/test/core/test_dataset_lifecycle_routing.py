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

"""Observation-count routing reuses reduction without weakening coverage or budgets."""

import sqlite3
import time
from contextlib import closing

import pytest

from pt_snap_cli.core.common.errors import QueryExecutionError, QueryTimeoutError
from pt_snap_cli.core.dataset.dataset_resolver import DatasetResolver
from pt_snap_cli.core.dataset.dataset_sources import DatasetSourceResolver, QueryBudget
from pt_snap_cli.core.dataset.lifecycle import dataset_lifecycle_scratch as scratch
from pt_snap_cli.core.dataset.lifecycle import dataset_lifecycle_sql as sql
from test.core.test_dataset_lifecycle_scratch import capture_storage
from test.core.test_dataset_sql_pushdown import run_resolved
from test.test_dataset_focus import hashes, make_dataset


def observations(tmp_path, count):
    root = make_dataset(tmp_path / "observations", devices=(0,), slices=3)
    # Distinct preexisting identities avoid a row count that depends on proof-owner
    # expansion. Split the observations to exercise the cumulative probe bound.
    counts = [count // 3, count // 3, count - 2 * (count // 3)]
    for index, size in enumerate(counts):
        with closing(sqlite3.connect(root / f"device_0/slice_{index:05d}.db")) as conn, conn:
            conn.executemany(
                "INSERT INTO block_0 VALUES (?,?,8,8,1,-1,-1)",
                ((-(1 + index * count + i), 100 + i * 8) for i in range(size)),
            )
    return root


@pytest.mark.parametrize("extra", [-1, 0, 1])
def test_three_shard_boundary_uses_bounded_probe_and_one_reduction(tmp_path, monkeypatch, extra):
    count = sql._ATTACHED_OBSERVATION_LIMIT + extra
    root = observations(tmp_path, count)
    before = hashes(root)
    resolved = DatasetResolver().inspect(root)
    expected = run_resolved(resolved, "block", budget=QueryBudget(None, time.monotonic(), max_scratch_db_bytes=0))
    reads, builds, statements = [], [], []
    original_read = DatasetSourceResolver.read
    original_build = scratch._ScratchSources.build
    original_execute = scratch._ScratchSources.execute

    def read(source, path, statement, values=None):
        if statement.startswith("SELECT COUNT(*) AS count FROM (SELECT 1"):
            reads.append(values[0])
        return original_read(source, path, statement, values)

    def build(database, items, maximum):
        builds.append([item.index for item in items])
        return original_build(database, items, maximum)

    def execute(database, statement, values=()):
        statements.append(statement)
        return original_execute(database, statement, values)

    monkeypatch.setattr(DatasetSourceResolver, "read", read)
    monkeypatch.setattr(scratch._ScratchSources, "build", build)
    monkeypatch.setattr(scratch._ScratchSources, "execute", execute)
    budget = QueryBudget(None, time.monotonic(), max_work_rows=32)
    actual = run_resolved(resolved, "block", budget=budget)
    assert actual.rows == expected.rows
    assert actual.total == expected.total == count
    assert actual.has_more == expected.has_more
    coverage = actual.scope["source_coverage"]
    assert coverage["lifecycles"] == count
    assert coverage["unproved_identities"] == 0
    assert len(reads) == 3
    assert reads == [sql._ATTACHED_OBSERVATION_LIMIT + 1 - index * (count // 3) for index in range(3)]
    assert builds == ([[0, 1, 2]] if extra == 1 else [])
    assert sum(s.startswith("INSERT INTO lifecycle_state") for s in statements) == (3 if extra == 1 else 0)
    assert budget.work_rows <= 32
    assert hashes(root) == before


def test_disabled_scratch_keeps_readonly_attached_route_without_probe(tmp_path, monkeypatch):
    root = observations(tmp_path, sql._ATTACHED_OBSERVATION_LIMIT + 1)
    resolved = DatasetResolver().inspect(root)
    monkeypatch.setattr(sql, "_large_observation_set", lambda *a: pytest.fail("disabled probe"))
    monkeypatch.setattr(scratch, "scratch_lifecycles", lambda *a: pytest.fail("disabled scratch"))
    result = run_resolved(
        resolved,
        "block",
        budget=QueryBudget(None, time.monotonic(), max_work_rows=32, max_scratch_db_bytes=0),
    )
    assert result.total == sql._ATTACHED_OBSERVATION_LIMIT + 1


@pytest.mark.parametrize("failure", ["unavailable", "page_limit"])
def test_selected_three_shard_scratch_failure_is_terminal_and_cleans_up(tmp_path, monkeypatch, failure):
    root = observations(tmp_path, sql._ATTACHED_OBSERVATION_LIMIT + 1)
    before = hashes(root)
    resolved = DatasetResolver().inspect(root)
    parent, created = capture_storage(monkeypatch, tmp_path)
    monkeypatch.setattr(sql, "_lifecycle_cte", lambda *a: pytest.fail("ATTACH fallback"))
    maximum = 4096 if failure == "page_limit" else 512 * 1024**2
    if failure == "unavailable":

        def unavailable(*args, **kwargs):
            raise PermissionError("injected unwritable temporary directory")

        monkeypatch.setattr(scratch.tempfile, "TemporaryDirectory", unavailable)
    with pytest.raises(QueryExecutionError, match="scratch"):
        run_resolved(
            resolved,
            "block",
            budget=QueryBudget(None, time.monotonic(), max_scratch_db_bytes=maximum),
        )
    assert bool(created) == (failure == "page_limit")
    assert not list(parent.iterdir())
    assert hashes(root) == before


def test_routing_probe_consumes_same_operation_deadline(tmp_path, monkeypatch):
    resolved = DatasetResolver().inspect(observations(tmp_path, 12))
    original = DatasetSourceResolver.read

    def expired(source, path, statement, values=None):
        if statement.startswith("SELECT COUNT(*) AS count FROM (SELECT 1"):
            source.budget.started -= 10
        return original(source, path, statement, values)

    monkeypatch.setattr(DatasetSourceResolver, "read", expired)
    monkeypatch.setattr(scratch, "scratch_lifecycles", lambda *a: pytest.fail("late scratch"))
    with pytest.raises(QueryTimeoutError):
        run_resolved(resolved, "block", budget=QueryBudget(5, time.monotonic()))


def test_python310_attachment_limit_fallback(tmp_path, monkeypatch):
    original = sqlite3.connect

    class NoGetlimit(sqlite3.Connection):
        getlimit = None

    monkeypatch.setattr(sqlite3, "connect", lambda *a, **k: original(*a, factory=NoGetlimit, **k))
    assert sql._attachment_limit() == 10
