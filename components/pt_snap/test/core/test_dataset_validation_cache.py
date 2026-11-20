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

"""Work-count and cancellation regressions for dataset admission (issue #219)."""

import json
import os
import sqlite3
from contextlib import closing
from pathlib import Path

import pytest

from pt_snap_cli.completion import complete_device_ids
from pt_snap_cli.core.common.errors import (
    DatabaseSchemaError,
    QueryCancelledError,
    QueryTimeoutError,
)
from pt_snap_cli.core.common.validation_budget import validation_progress
from pt_snap_cli.core.dataset import dataset_contract, dataset_resolver, native_dataset_contract
from pt_snap_cli.core.dataset.dataset_contract import validate_dataset
from pt_snap_cli.core.dataset.dataset_files import hash_file
from pt_snap_cli.core.dataset.dataset_resolver import DatasetResolver
from test.test_dataset_focus import make_dataset
from test.test_native_dataset import dataset as native_dataset


@pytest.fixture(autouse=True)
def clear_generations(monkeypatch):
    monkeypatch.setenv("PT_SNAP_DATASET_CACHE", "immutable")
    dataset_resolver._VALIDATED.clear()
    yield
    dataset_resolver._VALIDATED.clear()


@pytest.fixture(params=[False, True], ids=["compatibility", "native"])
def artifact(tmp_path, request):
    return native_dataset(tmp_path) if request.param else make_dataset(tmp_path / "dataset")


def test_closed_wal_compatibility_dataset_opens_on_first_inspection(tmp_path, monkeypatch):
    monkeypatch.delenv("PT_SNAP_DATASET_CACHE", raising=False)
    root = make_dataset(tmp_path / "dataset")
    for member in root.glob("*/*.db"):
        with closing(sqlite3.connect(member)) as conn:
            conn.execute("PRAGMA journal_mode=WAL")
        assert not Path(str(member) + "-wal").exists()
    resolved = DatasetResolver().inspect(root)
    assert resolved is not None
    resolved.require_unchanged()
    assert DatasetResolver().inspect(root).fingerprint == resolved.fingerprint


def test_wal_preparation_does_not_hide_subsequent_content_changes(tmp_path, monkeypatch):
    monkeypatch.delenv("PT_SNAP_DATASET_CACHE", raising=False)
    root = make_dataset(tmp_path / "dataset", devices=(0,), slices=1)
    member = root / "device_0/slice_00000.db"
    with closing(sqlite3.connect(member)) as conn:
        conn.execute("PRAGMA journal_mode=WAL")
    validate = dataset_resolver.validate_dataset

    def changed(*args, **kwargs):
        result = validate(*args, **kwargs)
        with closing(sqlite3.connect(member)) as writer, writer:
            writer.execute("UPDATE trace_entry_0 SET callstack='changed after validation'")
        return result

    monkeypatch.setattr(dataset_resolver, "validate_dataset", changed)
    with pytest.raises(DatabaseSchemaError, match="changed during inspection"):
        DatasetResolver().inspect(root)


@pytest.mark.parametrize("cache_mode", [None, "immutable", "disabled"])
@pytest.mark.parametrize("seal", ["parserCache", "ptSnap"])
def test_historical_digests_do_not_reject_valid_content_changes(tmp_path, monkeypatch, cache_mode, seal):
    from pt_snap_cli.core.cache.snapshot_cache import seal_manifest

    if cache_mode is None:
        monkeypatch.delenv("PT_SNAP_DATASET_CACHE", raising=False)
    else:
        monkeypatch.setenv("PT_SNAP_DATASET_CACHE", cache_mode)
    root = make_dataset(tmp_path / "dataset", devices=(0,), slices=1)
    manifest_path = root / "manifest.json"
    manifest = json.loads(manifest_path.read_bytes())
    manifest["cacheHash"] = "a" * 64
    seal_manifest(root, manifest)
    if seal == "ptSnap":
        manifest["ptSnap"] = {
            "memberHashKind": "parser-v1",
            "members": manifest.pop("parserCache")["members"],
        }
    manifest_path.write_text(json.dumps(manifest))
    assert DatasetResolver().inspect(root) is not None
    with closing(sqlite3.connect(root / "device_0/slice_00000.db")) as conn, conn:
        conn.execute("UPDATE trace_entry_0 SET allocated=allocated+1")
    assert DatasetResolver().inspect(root) is not None


def forbidden(*args, **kwargs):
    pytest.fail("warm resolution must not hash or validate shard contents")


def test_new_resolvers_respect_platform_generation_reuse_policy(artifact, monkeypatch):
    first = DatasetResolver().inspect(artifact)
    calls = []
    for module, name in (
        (dataset_resolver, "_hash_file"),
        (native_dataset_contract, "_hash_file"),
        (dataset_resolver, "validate_dataset"),
        (dataset_resolver, "validate_native_dataset"),
        (sqlite3, "connect"),
    ):
        original = getattr(module, name)

        def tracked(*args, _original=original, _name=name, **kwargs):
            calls.append(_name)
            return _original(*args, **kwargs)

        monkeypatch.setattr(module, name, tracked)
    second = DatasetResolver().inspect(artifact / "manifest.json")
    assert second == first and second is not first
    if os.name == "posix":
        assert calls == []
    else:
        # Windows creation time cannot authorize metadata-only immutable reuse.
        assert "_hash_file" in calls and "connect" in calls
        assert "validate_dataset" in calls or "validate_native_dataset" in calls
        assert artifact not in dataset_resolver._VALIDATED
    second.require_unchanged()


@pytest.mark.parametrize("change", ["touch", "replace", "manifest"])
def test_metadata_change_always_revalidates(artifact, monkeypatch, change):
    first = DatasetResolver().inspect(artifact)
    path = artifact / "manifest.json" if change == "manifest" else next(artifact.glob("*/*.db"))
    if change == "replace":
        replacement = path.with_suffix(".replacement")
        replacement.write_bytes(path.read_bytes())
        replacement.replace(path)
    else:
        stat = path.stat()
        os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000))
    calls = []
    real = dataset_resolver._hash_file

    def tracked(*args, **kwargs):
        calls.append(args[0])
        return real(*args, **kwargs)

    monkeypatch.setattr(dataset_resolver, "_hash_file", tracked)
    second = DatasetResolver().inspect(artifact)
    assert first.fingerprint == second.fingerprint
    assert artifact / "manifest.json" in calls
    with pytest.raises(DatabaseSchemaError, match="changed during operation"):
        first.require_unchanged()


def test_restored_mtime_size_does_not_hide_content_tampering(artifact):
    DatasetResolver().inspect(artifact)
    member = next(artifact.glob("*/*.db"))
    before = member.stat()
    device = member.parent.name.removeprefix("device_")
    with closing(sqlite3.connect(member)) as conn, conn:
        conn.execute(f"UPDATE trace_entry_{device} SET action=100 WHERE id>=0")
    os.utime(member, ns=(before.st_atime_ns, before.st_mtime_ns))
    after = member.stat()
    assert (before.st_ino, before.st_size, before.st_mtime_ns) == (
        after.st_ino,
        after.st_size,
        after.st_mtime_ns,
    )
    if os.name == "posix":
        assert before.st_ctime_ns != after.st_ctime_ns
    else:
        assert artifact not in dataset_resolver._VALIDATED
    with pytest.raises(DatabaseSchemaError):
        DatasetResolver().inspect(artifact)


@pytest.mark.parametrize("change", ["wal", "journal", "shm", "symlink", "manifest-symlink"])
def test_cached_generation_still_rejects_sidecars_and_aliases(artifact, tmp_path, change):
    DatasetResolver().inspect(artifact)
    member = next(artifact.glob("*/*.db"))
    if change.endswith("symlink"):
        path = artifact / "manifest.json" if change == "manifest-symlink" else member
        saved = tmp_path / "saved"
        path.rename(saved)
        path.symlink_to(saved)
    else:
        Path(str(member) + "-" + change).touch()
    with pytest.raises(DatabaseSchemaError):
        DatasetResolver().inspect(artifact)


def test_native_hashes_twice_on_admission_not_three_times(tmp_path, monkeypatch):
    root = native_dataset(tmp_path)
    calls = []
    real = hash_file

    def tracked(path, **kwargs):
        calls.append(path)
        return real(path, **kwargs)

    monkeypatch.setattr(dataset_resolver, "_hash_file", tracked)
    monkeypatch.setattr(native_dataset_contract, "_hash_file", tracked)
    DatasetResolver().inspect(root)
    for member in root.glob("*/*.db"):
        assert calls.count(member) == 2
    assert calls.count(root / "manifest.json") == 2


def test_cached_manifest_cannot_be_mutated_by_a_previous_caller(tmp_path):
    root = native_dataset(tmp_path)
    first = DatasetResolver().inspect(root)
    first.validation.manifest.identity["eventsPerSlice"] = "corrupted by caller"
    second = DatasetResolver().inspect(root)
    assert second.validation.manifest.identity["eventsPerSlice"] == 2


def test_cache_is_bounded_and_untrusted_change_tokens_disable_reuse(tmp_path, monkeypatch):
    # Default content-verified caching is available on every platform.
    monkeypatch.delenv("PT_SNAP_DATASET_CACHE")
    monkeypatch.setattr(dataset_resolver, "_CACHE_LIMIT", 2)
    for i in range(3):
        DatasetResolver().inspect(make_dataset(tmp_path / str(i), devices=(0,), slices=1))
    assert len(dataset_resolver._VALIDATED) == 2
    root = make_dataset(tmp_path / "uncached", devices=(0,), slices=1)
    monkeypatch.setenv("PT_SNAP_DATASET_CACHE", "immutable")
    monkeypatch.setattr(dataset_resolver, "_cacheable", lambda generation: False)
    DatasetResolver().inspect(root)
    assert root not in dataset_resolver._VALIDATED


def test_completion_only_reads_bounded_manifest(artifact, monkeypatch):
    monkeypatch.setenv("PT_SNAP_DB_PATH", str(artifact))
    expected = sorted(json.loads((artifact / "manifest.json").read_text())["devices"], key=int)
    monkeypatch.setattr(dataset_resolver, "_hash_file", forbidden)
    monkeypatch.setattr(dataset_resolver, "validate_dataset", forbidden)
    monkeypatch.setattr(dataset_resolver, "validate_native_dataset", forbidden)
    monkeypatch.setattr(sqlite3, "connect", forbidden)
    assert complete_device_ids() == expected
    # Completion candidates do not claim content integrity.
    next(artifact.glob("*/*.db")).write_bytes(b"invalid member")
    assert complete_device_ids() == expected
    (artifact / "manifest.json").write_bytes(b" " * (1024 * 1024 + 1))
    assert complete_device_ids() == []


class CancellableBudget:
    def __init__(self):
        self.cancelled = False
        self.calls = 0

    def remaining(self):
        self.calls += 1
        if self.cancelled:
            raise QueryTimeoutError("Query timed out after 0.01 seconds")
        return 1.0


def test_hash_checks_between_chunks_and_closes_file(tmp_path, monkeypatch):
    path = tmp_path / "large"
    path.write_bytes(b"x" * (4 * 1024 * 1024))
    budget = CancellableBudget()
    original = budget.remaining
    opened = []
    real_open = Path.open

    def tracked_open(self, *args, **kwargs):
        result = real_open(self, *args, **kwargs)
        opened.append(result)
        return result

    def remaining():
        budget.cancelled = budget.calls >= 2
        return original()

    monkeypatch.setattr(Path, "open", tracked_open)
    monkeypatch.setattr(budget, "remaining", remaining)
    with pytest.raises(QueryTimeoutError):
        hash_file(path, budget=budget)
    assert budget.calls == 3
    assert len(opened) == 1 and opened[0].closed
    assert hash_file(path)  # Failure did not retain resources.


def test_sql_progress_translates_timeout_and_clears_handler():
    budget = CancellableBudget()
    with closing(sqlite3.connect(":memory:")) as conn:
        with pytest.raises(QueryTimeoutError):
            with validation_progress(conn, budget):
                budget.cancelled = True
                conn.execute(
                    "WITH RECURSIVE n(x) AS (SELECT 1 UNION ALL SELECT x+1 FROM n WHERE x<10000) SELECT sum(x) FROM n"
                ).fetchone()
        # Still cancelled: this would interrupt if the handler leaked.
        assert conn.execute(
            "WITH RECURSIVE n(x) AS (SELECT 1 UNION ALL SELECT x+1 FROM n WHERE x<1000) SELECT sum(x) FROM n"
        ).fetchone() == (500500,)


def large_compatibility(root, rows=1000):
    root = make_dataset(root, devices=(0,), slices=1)
    with closing(sqlite3.connect(root / "device_0/slice_00000.db")) as conn, conn:
        conn.execute("DELETE FROM trace_entry_0")
        conn.executemany(
            "INSERT INTO trace_entry_0 VALUES (?,4,100,8,0,8,8,16,'stack')",
            ((i,) for i in range(rows)),
        )
        conn.executemany("INSERT INTO block_0 VALUES (?,100,8,8,1,?,-1)", ((i, i) for i in range(rows)))
    path = root / "manifest.json"
    data = json.loads(path.read_text())
    data["eventsPerSlice"] = rows
    data["devices"]["0"]["eventCount"] = rows
    data["devices"]["0"]["slices"][0]["endEventId"] = rows - 1
    path.write_text(json.dumps(data))
    return root


def test_python_validation_loop_cancels_before_finishing_and_closes_connection(tmp_path, monkeypatch):
    root = large_compatibility(tmp_path / "dataset")
    budget = CancellableBudget()
    checked = []
    connections = []
    real_integer = dataset_contract._integer
    real_connect = sqlite3.connect

    def integer(value, location, *args, **kwargs):
        if ".block_0." in location:
            checked.append(location)
            budget.cancelled = True
        return real_integer(value, location, *args, **kwargs)

    def connect(*args, **kwargs):
        conn = real_connect(*args, **kwargs)
        connections.append(conn)
        return conn

    monkeypatch.setattr(dataset_contract, "_integer", integer)
    monkeypatch.setattr(sqlite3, "connect", connect)
    with pytest.raises(QueryTimeoutError):
        validate_dataset(root, budget=budget)
    assert 0 < len(checked) <= 256 * 7
    for conn in connections:
        with pytest.raises(sqlite3.ProgrammingError, match="closed"):
            conn.execute("SELECT 1")
    monkeypatch.setattr(dataset_contract, "_integer", real_integer)
    assert validate_dataset(root).real_event_count == 1000


def test_native_quick_check_can_be_interrupted_and_resolver_recovers(tmp_path, monkeypatch):
    root = native_dataset(tmp_path)
    budget = CancellableBudget()
    connections = []
    real_connect = sqlite3.connect

    def connect(*args, **kwargs):
        conn = real_connect(*args, **kwargs)
        conn.set_trace_callback(lambda sql: setattr(budget, "cancelled", True) if sql == "PRAGMA quick_check" else None)
        connections.append(conn)
        return conn

    monkeypatch.setattr(sqlite3, "connect", connect)
    with pytest.raises(QueryTimeoutError):
        DatasetResolver().inspect(root, budget=budget)
    assert root not in dataset_resolver._VALIDATED
    for conn in connections:
        with pytest.raises(sqlite3.ProgrammingError, match="closed"):
            conn.execute("SELECT 1")
    monkeypatch.setattr(sqlite3, "connect", real_connect)
    assert DatasetResolver().inspect(root) is not None


def test_cold_query_passes_shared_deadline_and_cli_keeps_timeout_code(tmp_path, monkeypatch):
    from typer.testing import CliRunner

    from pt_snap_cli.cli import app
    from pt_snap_cli.core.analysis.query_service import QueryService

    root = make_dataset(tmp_path / "dataset", devices=(0,), slices=1)
    original = dataset_resolver._hash_file
    received = []

    def expire(path, *, budget=None):
        assert budget is not None
        received.append(budget)
        budget.started -= 20
        return original(path, budget=budget)

    monkeypatch.setattr(dataset_resolver, "_hash_file", expire)
    service = QueryService()
    try:
        with pytest.raises(QueryTimeoutError):
            service.execute_query("event", {"id": 0}, db_path=root, timeout_s=10)
    finally:
        service.close()
    result = CliRunner().invoke(app, ["query", str(root), "--template-use", "event", "--timeout", "10", "--json"])
    assert result.exit_code == 1
    assert json.loads(result.stderr)["error"]["code"] == "QUERY_TIMEOUT"
    assert len(received) == 2
    assert root not in dataset_resolver._VALIDATED
    monkeypatch.setattr(dataset_resolver, "_hash_file", original)
    service = QueryService()
    try:
        assert service.execute_query("event", {"id": 0}, db_path=root).rows[0]["id"] == 0
    finally:
        service.close()


def test_native_lock_wait_respects_deadline(tmp_path):
    import time

    from pt_snap_cli.core.dataset.dataset_sources import QueryBudget

    root = native_dataset(tmp_path)
    member = sorted(root.glob("*/*.db"))[0]
    with closing(sqlite3.connect(member)) as writer:
        writer.execute("BEGIN EXCLUSIVE")
        start = time.monotonic()
        with pytest.raises(QueryTimeoutError):
            DatasetResolver().inspect(root, budget=QueryBudget(0.02, start))
        assert time.monotonic() - start < 1.0
        writer.rollback()
    assert DatasetResolver().inspect(root) is not None


@pytest.mark.parametrize("mode", ["off", "unknown"])
def test_disabled_and_unknown_cache_mode_repeat_full_validation(tmp_path, monkeypatch, mode):
    monkeypatch.setenv("PT_SNAP_DATASET_CACHE", mode)
    root = make_dataset(tmp_path / "dataset", devices=(0,), slices=1)
    calls = []
    original = dataset_resolver._hash_file

    def tracked(path, **kwargs):
        calls.append(path)
        return original(path, **kwargs)

    monkeypatch.setattr(dataset_resolver, "_hash_file", tracked)
    first = DatasetResolver().inspect(root)
    second = DatasetResolver().inspect(root)
    assert first.fingerprint == second.fingerprint
    assert calls.count(root / "device_0/slice_00000.db") == 2
    assert root not in dataset_resolver._VALIDATED


def test_strong_operation_guard_hashes_even_when_filesystem_tokens_look_unchanged(tmp_path, monkeypatch):
    monkeypatch.delenv("PT_SNAP_DATASET_CACHE")
    root = make_dataset(tmp_path / "dataset", devices=(0,), slices=1)
    resolved = DatasetResolver().inspect(root)
    resolved.require_unchanged()
    with closing(sqlite3.connect(root / "device_0/slice_00000.db")) as conn, conn:
        conn.execute("UPDATE trace_entry_0 SET callstack='changed'")
    monkeypatch.setattr(dataset_resolver, "_generation", lambda *args: resolved.generation)
    with pytest.raises(DatabaseSchemaError, match="content changed"):
        resolved.require_unchanged()


@pytest.mark.parametrize("error", [QueryTimeoutError, QueryCancelledError])
def test_cancelled_admission_evicts_an_existing_entry(tmp_path, monkeypatch, error):
    monkeypatch.delenv("PT_SNAP_DATASET_CACHE")
    root = make_dataset(tmp_path / "dataset", devices=(0,), slices=1)
    DatasetResolver().inspect(root)
    assert root in dataset_resolver._VALIDATED

    class Budget:
        def remaining(self):
            raise error("interrupted admission")

    with pytest.raises(error, match="interrupted admission"):
        DatasetResolver().inspect(root, budget=Budget())
    assert root not in dataset_resolver._VALIDATED


def test_disabling_cache_does_not_reuse_an_existing_entry(tmp_path, monkeypatch):
    monkeypatch.delenv("PT_SNAP_DATASET_CACHE")
    root = make_dataset(tmp_path / "dataset", devices=(0,), slices=1)
    DatasetResolver().inspect(root)
    assert root in dataset_resolver._VALIDATED
    monkeypatch.setenv("PT_SNAP_DATASET_CACHE", "off")
    with pytest.raises(QueryTimeoutError):
        budget = CancellableBudget()
        budget.cancelled = True
        DatasetResolver().inspect(root, budget=budget)
    DatasetResolver().inspect(root)
    assert root not in dataset_resolver._VALIDATED


def test_strong_operation_guard_normalizes_hash_io_failure(tmp_path, monkeypatch):
    monkeypatch.delenv("PT_SNAP_DATASET_CACHE")
    root = make_dataset(tmp_path / "dataset", devices=(0,), slices=1)
    resolved = DatasetResolver().inspect(root)

    def fail(*args, **kwargs):
        raise PermissionError("member became unreadable")

    monkeypatch.setattr(dataset_resolver, "_hash_file", fail)
    with pytest.raises(DatabaseSchemaError, match="member became unreadable"):
        resolved.require_unchanged()


def test_immutable_request_never_trusts_windows_creation_time(artifact, monkeypatch):
    from types import SimpleNamespace

    # Exercise the real conservative policy even when this regression runs on Linux.
    monkeypatch.setattr(dataset_resolver, "os", SimpleNamespace(name="nt", environ=os.environ))
    first = DatasetResolver().inspect(artifact)
    assert not dataset_resolver._cacheable(first.generation)
    assert artifact not in dataset_resolver._VALIDATED
    assert DatasetResolver().inspect(artifact) == first
    assert artifact not in dataset_resolver._VALIDATED
    member = next(artifact.glob("*/*.db"))
    device = member.parent.name.removeprefix("device_")
    with closing(sqlite3.connect(member)) as conn, conn:
        conn.execute(f"UPDATE trace_entry_{device} SET action=100 WHERE id>=0")
    monkeypatch.setattr(dataset_resolver, "_generation", lambda *args: first.generation)
    with pytest.raises(DatabaseSchemaError):
        DatasetResolver().inspect(artifact)
    with pytest.raises(DatabaseSchemaError, match="content changed"):
        first.require_unchanged()
