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

"""Default reuse must prove content equality, even with untrustworthy stat tokens."""

import os
import sqlite3
from collections import Counter
from contextlib import closing
from pathlib import Path

import pytest

from pt_snap_cli.core.common.errors import DatabaseSchemaError, QueryTimeoutError
from pt_snap_cli.core.dataset import dataset_resolver as resolver
from pt_snap_cli.core.dataset import native_dataset_contract as native
from pt_snap_cli.core.dataset.dataset_files import hash_file
from test.core.test_dataset_validation_cache import CancellableBudget
from test.test_dataset_focus import make_dataset
from test.test_native_dataset import dataset as native_dataset


@pytest.fixture(autouse=True)
def default_cache(monkeypatch):
    monkeypatch.delenv("PT_SNAP_DATASET_CACHE", raising=False)
    resolver._VALIDATED.clear()
    yield
    resolver._VALIDATED.clear()


@pytest.fixture(params=[False, True], ids=["compatibility", "native"])
def artifact(tmp_path, request):
    return native_dataset(tmp_path) if request.param else make_dataset(tmp_path / "dataset")


def test_default_cold_and_warm_work_counts(artifact, monkeypatch):
    hashes = Counter()

    def tracked(path, **kwargs):
        hashes[path] += 1
        return hash_file(path, **kwargs)

    monkeypatch.setattr(resolver, "_hash_file", tracked)
    monkeypatch.setattr(native, "_hash_file", tracked)
    first = resolver.DatasetResolver().inspect(artifact)
    for member in artifact.glob("*/*.db"):
        assert hashes[member] == 2
    assert hashes[artifact / "manifest.json"] == 2
    hashes.clear()

    def forbidden(*args, **kwargs):
        pytest.fail("content-verified warm hit must not repeat SQLite/row validation")

    monkeypatch.setattr(resolver, "validate_dataset", forbidden)
    monkeypatch.setattr(resolver, "validate_native_dataset", forbidden)
    monkeypatch.setattr(sqlite3, "connect", forbidden)
    second = resolver.DatasetResolver().inspect(artifact / "manifest.json")
    assert first == second and first is not second
    for member in artifact.glob("*/*.db"):
        assert hashes[member] == 1
    assert hashes[artifact / "manifest.json"] == 1
    # Report guards remain independently strong, even following a cache hit.
    second.require_unchanged()
    for member in artifact.glob("*/*.db"):
        assert hashes[member] == 2


def test_default_detects_tampering_with_all_change_tokens_hidden(artifact, monkeypatch):
    resolved = resolver.DatasetResolver().inspect(artifact)
    member = next(artifact.glob("*/*.db"))
    before = member.stat()
    device = member.parent.name.removeprefix("device_")
    with closing(sqlite3.connect(member)) as conn, conn:
        conn.execute(f"UPDATE trace_entry_{device} SET action=100 WHERE id>=0")
    os.utime(member, ns=(before.st_atime_ns, before.st_mtime_ns))
    assert (member.stat().st_size, member.stat().st_mtime_ns) == (
        before.st_size,
        before.st_mtime_ns,
    )
    monkeypatch.setattr(resolver, "_generation", lambda *args: resolved.generation)
    with pytest.raises(DatabaseSchemaError):
        resolver.DatasetResolver().inspect(artifact)
    assert artifact not in resolver._VALIDATED


@pytest.mark.parametrize("change", ["touch", "replace", "manifest"])
def test_default_metadata_changes_fully_revalidate(artifact, monkeypatch, change):
    first = resolver.DatasetResolver().inspect(artifact)
    member = artifact / "manifest.json" if change == "manifest" else next(artifact.glob("*/*.db"))
    if change == "replace":
        replacement = member.with_suffix(".replacement")
        replacement.write_bytes(member.read_bytes())
        replacement.replace(member)
    else:
        before = member.stat()
        os.utime(member, ns=(before.st_atime_ns, before.st_mtime_ns + 1000000))
    calls = []
    for name in ("validate_dataset", "validate_native_dataset"):
        original = getattr(resolver, name)

        def tracked(*args, _original=original, **kwargs):
            calls.append(1)
            return _original(*args, **kwargs)

        monkeypatch.setattr(resolver, name, tracked)
    second = resolver.DatasetResolver().inspect(artifact)
    assert first.fingerprint == second.fingerprint
    assert len(calls) == 1


@pytest.mark.parametrize("change", ["wal", "journal", "shm", "member-alias", "root-alias", "missing"])
def test_default_preflight_failure_evicts_cached_entry(artifact, tmp_path, change):
    resolver.DatasetResolver().inspect(artifact)
    member = next(artifact.glob("*/*.db"))
    if change == "missing":
        member.unlink()
    elif change in ("member-alias", "root-alias"):
        source = member if change == "member-alias" else artifact
        saved = tmp_path / "renamed"
        source.rename(saved)
        source.symlink_to(saved, target_is_directory=change == "root-alias")
    else:
        Path(str(member) + "-" + change).touch()
    with pytest.raises(DatabaseSchemaError):
        resolver.DatasetResolver().inspect(artifact)
    assert artifact not in resolver._VALIDATED


def test_native_unlisted_member_invalidates(tmp_path):
    root = native_dataset(tmp_path)
    resolver.DatasetResolver().inspect(root)
    (root / "device_0" / "slice_99999.db").write_bytes(b"extra")
    with pytest.raises(DatabaseSchemaError):
        resolver.DatasetResolver().inspect(root)
    assert root not in resolver._VALIDATED


def test_warm_hash_cancellation_evicts_and_next_call_recovers(artifact, monkeypatch):
    resolver.DatasetResolver().inspect(artifact)
    budget = CancellableBudget()
    original = resolver._hash_file

    def cancelled(path, **kwargs):
        if path.suffix == ".db":
            budget.cancelled = True
        return original(path, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(resolver, "_hash_file", cancelled)
        with pytest.raises(QueryTimeoutError):
            resolver.DatasetResolver().inspect(artifact, budget=budget)
    assert artifact not in resolver._VALIDATED
    assert resolver.DatasetResolver().inspect(artifact) is not None


def test_expired_budget_evicts_without_any_hash(artifact, monkeypatch):
    resolver.DatasetResolver().inspect(artifact)
    budget = CancellableBudget()
    budget.cancelled = True

    def forbidden(*args, **kwargs):
        pytest.fail("expired deadline must precede file hashing")

    monkeypatch.setattr(resolver, "_hash_file", forbidden)
    with pytest.raises(QueryTimeoutError):
        resolver.DatasetResolver().inspect(artifact, budget=budget)
    assert artifact not in resolver._VALIDATED


def test_warm_concurrent_change_refuses_and_evicts(artifact, monkeypatch):
    resolver.DatasetResolver().inspect(artifact)
    original = resolver._hash_file

    def changed(path, **kwargs):
        value = original(path, **kwargs)
        if path.suffix == ".db":
            before = path.stat()
            os.utime(path, ns=(before.st_atime_ns, before.st_mtime_ns + 1000000))
        return value

    monkeypatch.setattr(resolver, "_hash_file", changed)
    with pytest.raises(DatabaseSchemaError, match="changed during inspection"):
        resolver.DatasetResolver().inspect(artifact)
    assert artifact not in resolver._VALIDATED


def test_compatibility_cold_hashes_bracket_validation(tmp_path, monkeypatch):
    root = make_dataset(tmp_path / "dataset", devices=(0,), slices=1)
    original = resolver.validate_dataset

    def changed(*args, **kwargs):
        result = original(*args, **kwargs)
        with closing(sqlite3.connect(root / "device_0/slice_00000.db")) as conn, conn:
            conn.execute("UPDATE trace_entry_0 SET callstack='valid changed text'")
        return result

    monkeypatch.setattr(resolver, "validate_dataset", changed)
    with pytest.raises(DatabaseSchemaError, match="content changed during inspection"):
        resolver.DatasetResolver().inspect(root)
    assert root not in resolver._VALIDATED


def test_default_cache_is_bounded_deep_copied_and_owns_no_connections(tmp_path, monkeypatch):
    monkeypatch.setattr(resolver, "_CACHE_LIMIT", 2)
    roots = [make_dataset(tmp_path / str(i), devices=(0,), slices=1) for i in range(3)]
    for root in roots:
        resolver.DatasetResolver().inspect(root)
    assert list(resolver._VALIDATED) == roots[1:]
    first = resolver.DatasetResolver().inspect(roots[1])
    object.__setattr__(first.validation, "real_event_count", -1)
    assert resolver.DatasetResolver().inspect(roots[1]).validation.real_event_count == 2
    assert list(resolver._VALIDATED) == [roots[2], roots[1]]
    # Cached entries only contain result data; file removal needs no cache close.
    for root in roots:
        for path in root.glob("*/*.db"):
            path.unlink()
    assert all(not tuple(root.glob("*/*.db")) for root in roots)


def test_immutable_v1_entry_cannot_seed_default_reuse(tmp_path, monkeypatch):
    root = make_dataset(tmp_path / "dataset", devices=(0,), slices=1)
    monkeypatch.setenv("PT_SNAP_DATASET_CACHE", "immutable")
    resolver.DatasetResolver().inspect(root)
    if os.name == "posix":
        assert not resolver._VALIDATED[root].content_verified
    else:
        assert root not in resolver._VALIDATED
    monkeypatch.delenv("PT_SNAP_DATASET_CACHE")
    calls = []
    original = resolver.validate_dataset

    def tracked(*args, **kwargs):
        calls.append(1)
        return original(*args, **kwargs)

    monkeypatch.setattr(resolver, "validate_dataset", tracked)
    resolver.DatasetResolver().inspect(root)
    resolver.DatasetResolver().inspect(root)
    assert calls == [1]
    assert resolver._VALIDATED[root].content_verified


def test_default_reuse_does_not_require_trusted_posix_tokens(artifact, monkeypatch):
    monkeypatch.setattr(resolver, "_cacheable", lambda generation: False)
    resolver.DatasetResolver().inspect(artifact)
    assert resolver.DatasetResolver().inspect(artifact) is not None
    assert artifact in resolver._VALIDATED


def test_valid_compatibility_content_change_revalidates_with_hidden_tokens(tmp_path, monkeypatch):
    root = make_dataset(tmp_path / "dataset", devices=(0,), slices=1)
    first = resolver.DatasetResolver().inspect(root)
    with closing(sqlite3.connect(root / "device_0/slice_00000.db")) as conn, conn:
        conn.execute("UPDATE trace_entry_0 SET callstack='valid new content'")
    monkeypatch.setattr(resolver, "_generation", lambda *args: first.generation)
    calls = []
    original = resolver.validate_dataset

    def tracked(*args, **kwargs):
        calls.append(1)
        return original(*args, **kwargs)

    monkeypatch.setattr(resolver, "validate_dataset", tracked)
    second = resolver.DatasetResolver().inspect(root)
    assert second.fingerprint != first.fingerprint
    assert calls == [1]
    assert resolver.DatasetResolver().inspect(root) == second
    assert calls == [1]


def test_hash_io_failure_evicts_entry(artifact, monkeypatch):
    resolver.DatasetResolver().inspect(artifact)

    def failed(*args, **kwargs):
        raise PermissionError("unreadable member")

    monkeypatch.setattr(resolver, "_hash_file", failed)
    with pytest.raises(DatabaseSchemaError, match="unreadable member"):
        resolver.DatasetResolver().inspect(artifact)
    assert artifact not in resolver._VALIDATED


def test_dataset_directory_named_manifest_cancellation_evicts_exact_entry(tmp_path):
    root = make_dataset(tmp_path / "manifest.json", devices=(0,), slices=1)
    resolver.DatasetResolver().inspect(root)
    budget = CancellableBudget()
    budget.cancelled = True
    with pytest.raises(QueryTimeoutError):
        resolver.DatasetResolver().inspect(root, budget=budget)
    assert root not in resolver._VALIDATED
