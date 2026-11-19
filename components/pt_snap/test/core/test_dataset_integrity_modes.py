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

"""Issue #219 acceptance: strong default versus explicit immutable publication."""

import json
import os
import sqlite3
import subprocess
import sys
from collections import Counter
from contextlib import closing
from pathlib import Path

import pytest

from pt_snap_cli.core.analysis.query_service import QueryService
from pt_snap_cli.core.common.errors import DatabaseSchemaError, QueryTimeoutError
from pt_snap_cli.core.dataset import dataset_resolver as resolver
from pt_snap_cli.core.dataset import native_dataset_contract as native
from pt_snap_cli.core.dataset.dataset_files import hash_file
from test.core.test_dataset_validation_cache import CancellableBudget
from test.test_dataset_focus import make_dataset
from test.test_native_dataset import dataset as native_dataset


@pytest.fixture(params=["strong", "immutable"])
def mode(request, monkeypatch):
    if request.param == "immutable":
        monkeypatch.setenv("PT_SNAP_DATASET_CACHE", "immutable")
    else:
        monkeypatch.delenv("PT_SNAP_DATASET_CACHE", raising=False)
    resolver._VALIDATED.clear()
    yield request.param
    resolver._VALIDATED.clear()


@pytest.fixture(params=["v1", "v2"])
def artifact(request, tmp_path, mode):
    root = make_dataset(tmp_path / "dataset") if request.param == "v1" else native_dataset(tmp_path)
    resolver._VALIDATED.clear()  # Import-time validation is not reader admission.
    return root, request.param


@pytest.fixture
def work(monkeypatch):
    """Count bytes actually returned by hash reads, excluding header preflights."""
    counts = Counter()
    active = []
    real_open = Path.open

    class Reader:
        def __init__(self, source, path):
            self.source, self.path = source, path

        def __enter__(self):
            self.source.__enter__()
            return self

        def __exit__(self, *args):
            return self.source.__exit__(*args)

        def read(self, *args):
            data = self.source.read(*args)
            counts[("bytes", self.path)] += len(data)
            return data

    def opened(path, *args, **kwargs):
        source = real_open(path, *args, **kwargs)
        return Reader(source, path) if active else source

    def hashed(path, **kwargs):
        counts[("hashes", path)] += 1
        active.append(path)
        try:
            return hash_file(path, **kwargs)
        finally:
            active.pop()

    monkeypatch.setattr(Path, "open", opened)
    monkeypatch.setattr(resolver, "_hash_file", hashed)
    monkeypatch.setattr(native, "_hash_file", hashed)
    for name in ("validate_dataset", "validate_native_dataset"):
        original = getattr(resolver, name)

        def validated(*args, _original=original, **kwargs):
            counts["validators"] += 1
            return _original(*args, **kwargs)

        monkeypatch.setattr(resolver, name, validated)
    return counts


def test_cold_warm_actual_hash_bytes_and_validator_counts(artifact, mode, work):
    root, layout = artifact
    members = sorted(root.glob("*/*.db"))
    manifest = root / "manifest.json"
    cold_member_passes = 1 if (layout, mode) == ("v1", "immutable") else 2
    evidence = {
        "layout": layout,
        "mode": mode,
        "member_bytes": sum(p.stat().st_size for p in members),
    }
    for state in ("cold", "warm"):
        work.clear()
        assert resolver.DatasetResolver().inspect(root) is not None
        # Immutable reuse requires POSIX change-time tokens; Windows revalidates.
        cold_validation = state == "cold" or (mode == "immutable" and os.name != "posix")
        passes = cold_member_passes if cold_validation else int(mode == "strong")
        for path in members:
            assert work[("hashes", path)] == passes
            assert work[("bytes", path)] == passes * path.stat().st_size
        manifest_passes = 2 if cold_validation else int(mode == "strong")
        assert work[("bytes", manifest)] == manifest_passes * manifest.stat().st_size
        assert work["validators"] == int(cold_validation)
        evidence[state] = {
            "hash_read_bytes": sum(v for k, v in work.items() if isinstance(k, tuple) and k[0] == "bytes"),
            "validators": work["validators"],
        }
    print(json.dumps(evidence, sort_keys=True))


@pytest.mark.parametrize("target", ["member", "manifest"])
def test_atomic_replacement_revalidates_even_identical_bytes(artifact, mode, work, target):
    root, _ = artifact
    resolver.DatasetResolver().inspect(root)
    path = root / "manifest.json" if target == "manifest" else next(root.glob("*/*.db"))
    replacement = path.with_suffix(".replacement")
    replacement.write_bytes(path.read_bytes())
    replacement.replace(path)
    work.clear()
    resolver.DatasetResolver().inspect(root)
    assert work["validators"] == 1
    assert work[("bytes", path)] >= path.stat().st_size


def test_hidden_change_tokens_document_immutable_trust_boundary(artifact, mode, monkeypatch):
    root, _ = artifact
    first = resolver.DatasetResolver().inspect(root)
    member = next(root.glob("*/*.db"))
    before = member.stat()
    device = member.parent.name.removeprefix("device_")
    with closing(sqlite3.connect(member)) as conn, conn:
        conn.execute(f"UPDATE trace_entry_{device} SET action=100 WHERE id>=0")
    os.utime(member, ns=(before.st_atime_ns, before.st_mtime_ns))
    assert (member.stat().st_size, member.stat().st_mtime_ns) == (
        before.st_size,
        before.st_mtime_ns,
    )
    # Simulate a filesystem concealing ctime too. This violates immutable mode's
    # explicit caller contract; that mode must not be described as strong integrity.
    monkeypatch.setattr(resolver, "_generation", lambda *args: first.generation)
    if mode == "strong" or os.name != "posix":
        with pytest.raises(DatabaseSchemaError):
            resolver.DatasetResolver().inspect(root)
        assert root not in resolver._VALIDATED
    else:
        assert resolver.DatasetResolver().inspect(root) == first
        first.require_unchanged()


@pytest.mark.parametrize("warm", [False, True], ids=["cold", "warm"])
def test_expired_deadline_evicts_and_full_retry_closes_connections(artifact, mode, work, monkeypatch, warm):
    root, _ = artifact
    if warm:
        resolver.DatasetResolver().inspect(root)
    work.clear()
    budget = CancellableBudget()
    budget.cancelled = True
    with pytest.raises(QueryTimeoutError):
        resolver.DatasetResolver().inspect(root, budget=budget)
    assert not work and root not in resolver._VALIDATED
    connections = []
    original = sqlite3.connect

    def connect(*args, **kwargs):
        conn = original(*args, **kwargs)
        connections.append(conn)
        return conn

    monkeypatch.setattr(sqlite3, "connect", connect)
    resolver.DatasetResolver().inspect(root)
    assert work["validators"] == 1 and connections
    for conn in connections:
        with pytest.raises(sqlite3.ProgrammingError, match="closed"):
            conn.execute("SELECT 1")


def test_owned_query_cache_close_and_service_reuse(artifact, mode, monkeypatch):
    root, layout = artifact
    connections = []
    original = sqlite3.connect

    def connect(*args, **kwargs):
        conn = original(*args, **kwargs)
        connections.append(conn)
        return conn

    monkeypatch.setattr(sqlite3, "connect", connect)
    service = QueryService()
    try:
        for _ in range(2):
            result = service.execute_query("event", {"id": 0 if layout == "v1" else 7}, db_path=root)
            assert len(result.rows) == 1
            service.close()
            for conn in connections:
                with pytest.raises(sqlite3.ProgrammingError, match="closed"):
                    conn.execute("SELECT 1")
    finally:
        service.close()


def test_new_process_is_cold_even_after_parent_admission(artifact, mode):
    root, _ = artifact
    resolver.DatasetResolver().inspect(root)
    code = """
import sys
from pt_snap_cli.core.dataset import dataset_resolver as r
assert not r._VALIDATED
calls = []
for name in ('validate_dataset', 'validate_native_dataset'):
    original = getattr(r, name)
    def tracked(*args, _original=original, **kwargs):
        calls.append(1)
        return _original(*args, **kwargs)
    setattr(r, name, tracked)
assert r.DatasetResolver().inspect(sys.argv[1]) is not None
assert calls == [1]
"""
    result = subprocess.run([sys.executable, "-c", code, str(root)], capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr


def test_cancellation_inside_validation_closes_and_cannot_seed_retry(artifact, mode, work, monkeypatch):
    root, _ = artifact
    budget = CancellableBudget()
    connections = []
    original = sqlite3.connect

    def connect(*args, **kwargs):
        conn = original(*args, **kwargs)
        conn.set_trace_callback(lambda sql: setattr(budget, "cancelled", True))
        connections.append(conn)
        return conn

    with monkeypatch.context() as patch:
        patch.setattr(sqlite3, "connect", connect)
        with pytest.raises(QueryTimeoutError):
            resolver.DatasetResolver().inspect(root, budget=budget)
    assert work["validators"] == 1 and connections
    assert root not in resolver._VALIDATED
    for conn in connections:
        with pytest.raises(sqlite3.ProgrammingError, match="closed"):
            conn.execute("SELECT 1")
    work.clear()
    resolver.DatasetResolver().inspect(root)
    assert work["validators"] == 1
