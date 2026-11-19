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

"""Issue #238: measure report hashing without weakening either content guard.

These are logical bytes returned by real hash reads, not physical disk I/O.
No timing threshold or assumption about the operating system's page cache.
"""

import dataclasses
import os
import sqlite3
from collections import Counter
from contextlib import closing, contextmanager
from pathlib import Path

import pytest

from pt_snap_cli.core.analysis import query_service as queries
from pt_snap_cli.core.analysis.report_service import ReportService
from pt_snap_cli.core.common.errors import DatabaseSchemaError, QueryTimeoutError
from pt_snap_cli.core.dataset import dataset_resolver as resolver
from pt_snap_cli.core.dataset import native_dataset_contract as native
from pt_snap_cli.core.dataset.dataset_files import hash_file
from test.test_dataset_focus import make_dataset
from test.test_native_dataset import dataset as native_dataset


@pytest.fixture(autouse=True)
def isolate(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    for name in ("PT_SNAP_DB_PATH", "PT_SNAP_QUERY_TIMEOUT", "PT_SNAP_DATASET_CACHE"):
        monkeypatch.delenv(name, raising=False)
    resolver._VALIDATED.clear()
    yield
    resolver._VALIDATED.clear()


@pytest.fixture(params=["compatibility", "native"])
def artifact(request, tmp_path):
    root = (
        make_dataset(tmp_path / "dataset", devices=(0, 1), slices=2)
        if request.param == "compatibility"
        else native_dataset(tmp_path)
    )
    resolver._VALIDATED.clear()  # Producer validation is not reader admission.
    return root, request.param


@dataclasses.dataclass
class HashRead:
    phase: str
    path: Path
    bytes_read: int = 0
    completed: bool = False


class ReportWork:
    def __init__(self):
        self.phases = []
        self.events = []
        self.hashes = []
        self.readers = []
        self.connections = []
        self.inspections = []
        self.validators = Counter()
        self.guards = 0
        self.read_limit = None
        self.before_read = None
        self.after_read = None

    @contextmanager
    def phase(self, name):
        self.events.append(name + ":start")
        self.phases.append(name)
        try:
            yield
        except BaseException:
            self.events.append(name + ":failed")
            raise
        else:
            self.events.append(name + ":done")
        finally:
            self.phases.pop()

    def counts(self, phase):
        return Counter(item.path for item in self.hashes if item.phase == phase)

    def assert_closed(self):
        assert all(reader.closed for reader in self.readers)
        for connection in self.connections:
            with pytest.raises(sqlite3.ProgrammingError, match="closed"):
                connection.execute("SELECT 1")


@pytest.fixture
def work(monkeypatch):
    """Wrap both imported hash aliases; count only bytes the real hasher reads."""
    work = ReportWork()
    active = []
    real_open, real_connect = Path.open, sqlite3.connect

    class Reader:
        def __init__(self, source, item, budget):
            self.source, self.item, self.budget = source, item, budget

        def __enter__(self):
            self.source.__enter__()
            return self

        def __exit__(self, *args):
            return self.source.__exit__(*args)

        def read(self, size):
            if work.before_read is not None:
                work.before_read(self.item)
            data = self.source.read(min(size, work.read_limit) if work.read_limit else size)
            self.item.bytes_read += len(data)
            if work.after_read is not None:
                work.after_read(self.item, self.budget, data)
            return data

    def opened(path, *args, **kwargs):
        source = real_open(path, *args, **kwargs)
        if active and path == active[-1][0].path:
            work.readers.append(source)
            return Reader(source, *active[-1])
        return source

    def hashed(path, **kwargs):
        item = HashRead(work.phases[-1], path)
        work.hashes.append(item)
        active.append((item, kwargs.get("budget")))
        try:
            result = hash_file(path, **kwargs)
            item.completed = True
            return result
        finally:
            active.pop()

    def connect(*args, **kwargs):
        connection = real_connect(*args, **kwargs)
        work.connections.append(connection)
        return connection

    inspect, guard = resolver.DatasetResolver.inspect, resolver.ResolvedDataset.require_unchanged

    def inspected(self, *args, **kwargs):
        with work.phase("inspect"):
            result = inspect(self, *args, **kwargs)
            work.inspections.append(result)
            return result

    def guarded(self, *args, **kwargs):
        work.guards += 1
        with work.phase(f"guard{work.guards}"):
            return guard(self, *args, **kwargs)

    for name in ("validate_dataset", "validate_native_dataset"):
        original = getattr(resolver, name)

        def validated(*args, _original=original, _name=name, **kwargs):
            work.validators[_name] += 1
            with work.phase("validator"):
                return _original(*args, **kwargs)

        monkeypatch.setattr(resolver, name, validated)
    for name, phase in (("global_query", "peak"), ("event_attribution", "attribution")):
        original = getattr(queries, name)

        def queried(*args, _original=original, _phase=phase, **kwargs):
            with work.phase(_phase):
                return _original(*args, **kwargs)

        monkeypatch.setattr(queries, name, queried)
    monkeypatch.setattr(Path, "open", opened)
    monkeypatch.setattr(sqlite3, "connect", connect)
    monkeypatch.setattr(resolver, "_hash_file", hashed)
    monkeypatch.setattr(native, "_hash_file", hashed)
    monkeypatch.setattr(resolver.DatasetResolver, "inspect", inspected)
    monkeypatch.setattr(resolver.ResolvedDataset, "require_unchanged", guarded)
    return work


@pytest.fixture(params=[False, True], ids=["cold", "warm"])
def admission(artifact, request):
    root, _ = artifact
    if request.param:
        assert resolver.DatasetResolver().inspect(root) is not None
    return request.param


def report(root, **kwargs):
    service = ReportService()
    try:
        return service.peak_memory_report(root, device_id=0, **kwargs)
    finally:
        service.close()


@pytest.mark.parametrize("empty", [False, True], ids=["peak", "no-peak"])
def test_report_phase_hash_calls_and_actual_read_bytes(artifact, admission, work, monkeypatch, empty):
    root, layout = artifact
    params = {}
    if empty and layout == "native":
        params = {"start_id": 18, "end_id": 26}  # Real sparse-ID empty range.
    elif empty:
        # Valid compatibility-v1 has contiguous IDs and non-NULL counters, so
        # no in-bounds empty peak exists. Inject only the no-peak result branch
        # after a real query; admission and its guard still execute unchanged.
        original = queries.global_query

        def no_peak(*args, **kwargs):
            result = original(*args, **kwargs)
            return dataclasses.replace(result, rows=[dict.fromkeys(result.rows[0])])

        monkeypatch.setattr(queries, "global_query", no_peak)
    result = report(root, **params)
    paths = [root / "manifest.json", *sorted(root.glob("*/*.db"))]
    expected_inspect = Counter(dict.fromkeys(paths, 1 if admission else 2))
    expected_validator = Counter()
    if not admission and layout == "native":
        expected_inspect = Counter({paths[0]: 2})
        expected_validator = Counter(dict.fromkeys(paths[1:], 2))
    assert work.counts("inspect") == expected_inspect
    assert work.counts("validator") == expected_validator
    assert work.counts("guard1") == Counter(dict.fromkeys(paths, 1))
    assert work.counts("guard2") == (Counter() if empty else Counter(dict.fromkeys(paths, 1)))
    assert len(work.inspections) == 1
    validator = "validate_dataset" if layout == "compatibility" else "validate_native_dataset"
    assert work.validators == (Counter() if admission else Counter({validator: 1}))
    assert all(item.completed and item.bytes_read == item.path.stat().st_size for item in work.hashes)
    passes = (1 if admission else 2) + (1 if empty else 2)
    assert sum(item.bytes_read for item in work.hashes) == passes * sum(path.stat().st_size for path in paths)
    expected_events = ["inspect:start"]
    if not admission:
        expected_events += ["validator:start", "validator:done"]
    expected_events += ["inspect:done", "peak:start", "peak:done", "guard1:start", "guard1:done"]
    if not empty:
        expected_events += ["attribution:start", "attribution:done", "guard2:start", "guard2:done"]
    assert work.events == expected_events
    assert (result.event_id is None) == empty
    if empty:
        assert result.callstack_groups == [] and result.allocator_gap is None
    assert result.scope["fingerprint"] == work.inspections[0].fingerprint
    # A warm sparse native range can exclude every shard before SQLite opens.
    assert bool(work.connections) == (not (admission and empty and layout == "native"))
    work.assert_closed()


def change_content(root, target):
    path = (
        root / "manifest.json"
        if target == "manifest"
        else root / f"device_{1 if target == 'other-device' else 0}/slice_00000.db"
    )
    before, contents = path.stat(), path.read_bytes()
    if target == "manifest":
        # JSON whitespace only: same length and meaning, different content hash.
        changed = contents.replace(b" ", b"\t", 1)
        assert changed != contents
        path.write_bytes(changed)
    else:
        device = 1 if target == "other-device" else 0
        with closing(sqlite3.connect(path)) as conn, conn:
            conn.execute(f"UPDATE trace_entry_{device} SET reserved=reserved+1 WHERE id>=0")
    os.utime(path, ns=(before.st_atime_ns, before.st_mtime_ns))
    assert path.stat().st_size == before.st_size
    assert path.stat().st_mtime_ns == before.st_mtime_ns
    assert path.read_bytes() != contents
    return path, contents


@pytest.mark.parametrize("stage", ["peak", "attribution"])
@pytest.mark.parametrize("target", ["member", "other-device", "manifest"])
def test_hidden_content_change_fails_at_each_report_guard(artifact, work, monkeypatch, stage, target):
    root, _ = artifact
    name = "global_query" if stage == "peak" else "event_attribution"
    original = getattr(queries, name)
    changes = []

    def changed(*args, **kwargs):
        result = original(*args, **kwargs)
        pinned = work.inspections[0]
        changes.append(change_content(root, target))
        # Simulate all generation tokens being hidden, not merely restored mtime.
        monkeypatch.setattr(resolver, "_generation", lambda *a: pinned.generation)
        return result

    monkeypatch.setattr(queries, name, changed)
    guard = 1 if stage == "peak" else 2
    with pytest.raises(DatabaseSchemaError, match="content changed during operation"):
        report(root)
    assert len(changes) == 1 and work.guards == guard
    assert work.events[-1] == f"guard{guard}:failed"
    if stage == "peak":
        assert "attribution:start" not in work.events
    assert changes[0][0] in work.counts(f"guard{guard}")
    # A pinned guard refuses the report but does not evict resolver admission.
    assert resolver._VALIDATED[root].resolved.fingerprint == work.inspections[0].fingerprint
    work.assert_closed()


def test_first_guard_rejects_change_even_if_attribution_would_restore_it(artifact, work, monkeypatch):
    root, _ = artifact
    peak, attribution = queries.global_query, queries.event_attribution
    changes, restored = [], []

    def changed(*args, **kwargs):
        result = peak(*args, **kwargs)
        changes.append(change_content(root, "member"))
        monkeypatch.setattr(resolver, "_generation", lambda *a: work.inspections[0].generation)
        return result

    def restore_then_attribute(*args, **kwargs):
        path, contents = changes[0]
        path.write_bytes(contents)
        restored.append(path)
        return attribution(*args, **kwargs)

    monkeypatch.setattr(queries, "global_query", changed)
    monkeypatch.setattr(queries, "event_attribution", restore_then_attribute)
    with pytest.raises(DatabaseSchemaError, match="content changed during operation"):
        report(root)
    assert changes and not restored
    assert work.guards == 1 and work.events[-1] == "guard1:failed"
    assert "attribution:start" not in work.events
    work.assert_closed()


def test_compatibility_cold_report_brackets_validator_and_refuses_cache_admission(tmp_path, work, monkeypatch):
    root = make_dataset(tmp_path / "dataset", devices=(0, 1), slices=2)
    validator, generation = resolver.validate_dataset, resolver._generation
    baseline = []

    def pinned(*args):
        if not baseline:
            baseline.append(generation(*args))
        return baseline[0]

    def changed(*args, **kwargs):
        result = validator(*args, **kwargs)
        change_content(root, "other-device")
        return result

    monkeypatch.setattr(resolver, "_generation", pinned)
    monkeypatch.setattr(resolver, "validate_dataset", changed)
    with pytest.raises(DatabaseSchemaError, match="content changed during inspection"):
        report(root)
    assert root not in resolver._VALIDATED
    assert work.guards == 0 and "peak:start" not in work.events
    assert work.validators == Counter({"validate_dataset": 1})
    assert work.counts("inspect")[root / "manifest.json"] == 1
    assert all(work.counts("inspect")[path] == 2 for path in root.glob("*/*.db"))
    assert all(item.completed and item.bytes_read == item.path.stat().st_size for item in work.hashes)
    work.assert_closed()


@pytest.mark.parametrize("phase", ["inspect", "guard1", "guard2"])
@pytest.mark.parametrize("failure", ["timeout", "read-error"])
def test_partial_hash_failure_closes_resources_and_preserves_cache_contract(artifact, admission, work, phase, failure):
    root, layout = artifact
    fired = []

    def expire(item, budget, data):
        if item.phase == phase and data and not fired:
            fired.append(item)
            budget.started -= 100

    def fail_read(item):
        if item.phase == phase and item.bytes_read and not fired:
            fired.append(item)
            raise OSError("injected hash read failure")

    # Force a short successful read before cancellation; file size * call count
    # would overstate work, including on the very first manifest hash.
    work.read_limit = 17
    if failure == "timeout":
        work.after_read = expire
    else:
        work.before_read = fail_read
    error = QueryTimeoutError if failure == "timeout" else DatabaseSchemaError
    with pytest.raises(error):
        report(root, timeout_s=10)
    assert len(fired) == 1
    assert fired[0].bytes_read == 17 < fired[0].path.stat().st_size
    assert not fired[0].completed
    assert work.hashes[-1] is fired[0]
    assert all(item.completed and item.bytes_read == item.path.stat().st_size for item in work.hashes[:-1])
    assert (root in resolver._VALIDATED) == (phase != "inspect")
    assert all(reader.closed for reader in work.readers)
    for connection in work.connections:
        with pytest.raises(sqlite3.ProgrammingError, match="closed"):
            connection.execute("SELECT 1")
    # The next operation must still succeed; guard failure is not a fabricated
    # cache-eviction contract. Inspection cancellation does evict its admission.
    work.after_read = None
    work.before_read = None
    work.read_limit = None
    validators = work.validators.copy()
    assert report(root).event_id is not None
    if phase == "inspect":
        name = "validate_dataset" if layout == "compatibility" else "validate_native_dataset"
        validators[name] += 1
    assert work.validators == validators
    work.assert_closed()
