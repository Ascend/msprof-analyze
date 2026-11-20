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

"""Import receipts avoid row scans across processes without trusting timestamps."""

import dataclasses
import json
import os
import sqlite3
from contextlib import closing
from pathlib import Path

import pytest

from pt_snap_cli.core.common.errors import ImportExecutionError, QueryTimeoutError
from pt_snap_cli.core.dataset import dataset_resolver
from pt_snap_cli.core.importing import import_service
from pt_snap_cli.core.importing.import_service import ImportService
from pt_snap_cli.core.importing.validation_receipts import (
    import_receipts,
    load_receipt,
    save_receipt,
)
from test.core.test_dataset_validation_cache import CancellableBudget
from test.core.test_msinsight_export import options


@pytest.fixture(autouse=True)
def isolate(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.delenv("PT_SNAP_DB_PATH", raising=False)
    monkeypatch.delenv("PT_SNAP_DATASET_CACHE", raising=False)
    dataset_resolver._VALIDATED.clear()
    yield
    dataset_resolver._VALIDATED.clear()


def unexpected(*args, **kwargs):
    pytest.fail("unchanged imported bytes must not require another row validation")


def test_first_import_seeds_cold_repeat_including_focus(tmp_path, monkeypatch):
    request = dataclasses.replace(options(tmp_path), format=None)
    first = ImportService().import_snapshot(request)
    dataset_resolver._VALIDATED.clear()  # A fresh CLI process has no in-memory entries.
    for name in ("validate_native_dataset", "validate_dataset", "validate_cache"):
        monkeypatch.setattr(dataset_resolver, name, unexpected)
    monkeypatch.setattr(import_service, "frame_member_digest", unexpected)
    hashed = []
    original = dataset_resolver._hash_file

    def hash_file(path, **kwargs):
        hashed.append(path)
        return original(path, **kwargs)

    monkeypatch.setattr(dataset_resolver, "_hash_file", hash_file)
    second = ImportService().import_snapshot(request)
    assert second.reused and second.metadata == first.metadata
    assert second.focus_state.available_devices == first.focus_state.available_devices
    members = list(first.db_path.glob("device_*/*.db"))
    assert members and all(path in hashed for path in members)


def test_same_size_and_mtime_frame_edit_misses_receipt(tmp_path):
    request = dataclasses.replace(options(tmp_path, focus=False), format=None)
    first = ImportService().import_snapshot(request)
    member = next(first.db_path.glob("device_*/*.db"))
    before = member.stat()
    with closing(sqlite3.connect(member)) as conn, conn:
        row = conn.execute("SELECT id,frameJson FROM pt_snap_frame_value LIMIT 1").fetchone()
        # Same-length valid JSON, without changing the number or size of rows.
        changed = row[1].replace("name", "nAme", 1)
        assert changed != row[1]
        conn.execute("UPDATE pt_snap_frame_value SET frameJson=? WHERE id=?", (changed, row[0]))
    assert member.stat().st_size == before.st_size
    os.utime(member, ns=(before.st_atime_ns, before.st_mtime_ns))
    dataset_resolver._VALIDATED.clear()
    with pytest.raises(ImportExecutionError):
        ImportService().import_snapshot(request)
    assert member.exists()


def test_compatible_consumer_table_change_reuses_without_receipt(tmp_path, monkeypatch):
    request = options(tmp_path, focus=False)
    first = ImportService().import_snapshot(request)
    member = next(first.db_path.glob("device_*/*.db"))
    with closing(sqlite3.connect(member)) as conn, conn:
        conn.execute("CREATE TABLE gui_cache(value TEXT)")
        conn.execute("INSERT INTO gui_cache VALUES ('consumer')")
    dataset_resolver._VALIDATED.clear()
    monkeypatch.setattr(dataset_resolver, "validate_dataset", unexpected)
    assert ImportService().import_snapshot(request).reused
    dataset_resolver._VALIDATED.clear()
    assert ImportService().import_snapshot(request).reused


@pytest.mark.parametrize("damage", ["missing", "malformed", "checksum", "version"])
def test_missing_or_damaged_receipt_falls_back(tmp_path, monkeypatch, damage):
    request = dataclasses.replace(options(tmp_path, focus=False), format=None)
    ImportService().import_snapshot(request)
    folder = tmp_path / ".cache/pt-snap-cli/validation-v1"
    receipts = list(folder.glob("*.json"))
    assert receipts
    for path in receipts:
        if damage == "missing":
            path.unlink()
        elif damage == "malformed":
            path.write_text("{", encoding="utf-8")
        elif damage == "checksum":
            data = json.loads(path.read_bytes())
            data["sha256"] = "0" * 64
            path.write_text(json.dumps(data), encoding="utf-8")
        else:
            path.rename(path.with_suffix(".old"))
    dataset_resolver._VALIDATED.clear()
    calls = []
    original = dataset_resolver.validate_native_dataset

    def validate(*args, **kwargs):
        calls.append(1)
        return original(*args, **kwargs)

    monkeypatch.setattr(dataset_resolver, "validate_native_dataset", validate)
    assert ImportService().import_snapshot(request).reused
    assert calls == [1]


def test_receipt_is_import_only_and_off_disables_it(tmp_path, monkeypatch):
    request = dataclasses.replace(options(tmp_path, focus=False), format=None)
    result = ImportService().import_snapshot(request)
    dataset_resolver._VALIDATED.clear()
    calls = []
    original = dataset_resolver.validate_native_dataset

    def validate(*args, **kwargs):
        calls.append(1)
        return original(*args, **kwargs)

    monkeypatch.setattr(dataset_resolver, "validate_native_dataset", validate)
    dataset_resolver.DatasetResolver().inspect(result.db_path)
    assert calls == [1]  # Ordinary analysis retains its existing admission contract.
    calls.clear()
    dataset_resolver._VALIDATED.clear()
    monkeypatch.setenv("PT_SNAP_DATASET_CACHE", "off")
    assert ImportService().import_snapshot(request).reused
    assert calls == [1]


def test_unwritable_receipt_directory_is_only_a_cache_miss(tmp_path):
    (tmp_path / ".cache").write_text("file blocks directory creation", encoding="utf-8")
    with import_receipts():
        save_receipt(tmp_path, "dataset", "fingerprint", {})
        assert load_receipt(tmp_path, "dataset", "fingerprint") is None
    request = dataclasses.replace(options(tmp_path, focus=False), format=None)
    assert not ImportService().import_snapshot(request).reused
    dataset_resolver._VALIDATED.clear()
    assert ImportService().import_snapshot(request).reused


def test_receipt_hit_hashing_respects_cancellation(tmp_path, monkeypatch):
    request = dataclasses.replace(options(tmp_path, focus=False), format=None)
    first = ImportService().import_snapshot(request)
    dataset_resolver._VALIDATED.clear()
    budget = CancellableBudget()
    original = dataset_resolver._hash_file

    def cancelled(path, **kwargs):
        if path.suffix == ".db":
            budget.cancelled = True
        return original(path, **kwargs)

    with monkeypatch.context() as patch, import_receipts():
        patch.setattr(dataset_resolver, "_hash_file", cancelled)
        with pytest.raises(QueryTimeoutError):
            dataset_resolver.DatasetResolver().inspect(first.db_path, budget=budget)
    assert first.db_path not in dataset_resolver._VALIDATED
    assert ImportService().import_snapshot(request).reused


def test_compatible_committed_wal_frame_edits_do_not_trigger_content_checks(tmp_path):
    request = options(tmp_path, focus=False)
    first = ImportService().import_snapshot(request)
    member = next(first.db_path.glob("device_*/*.db"))
    with closing(sqlite3.connect(member)) as writer:
        writer.execute("PRAGMA journal_mode=WAL")
        writer.execute("CREATE TABLE gui_cache(value TEXT)")
        writer.commit()
        assert ImportService().import_snapshot(request).reused
        writer.execute('UPDATE pt_snap_frame_value SET frameJson=\'{"name":"changed"}\'')
        writer.commit()
        assert Path(str(member) + "-wal").stat().st_size > 0
        dataset_resolver._VALIDATED.clear()
        assert ImportService().import_snapshot(request).reused
