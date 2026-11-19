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

import dataclasses
import json
import sqlite3
from contextlib import closing
from pathlib import Path

import pytest

from pt_snap_cli.api import SnapshotAnalyzer
from pt_snap_cli.core.cache.context_cache import ContextCache
from pt_snap_cli.core.common.errors import DatabaseSchemaError, InvalidParameterError
from pt_snap_cli.core.dataset.dataset_contract import (
    DatasetContractError,
    QueryScope,
    parse_manifest,
)
from pt_snap_cli.core.dataset.dataset_resolver import DatasetResolver, _hash_file
from pt_snap_cli.core.dataset.native_dataset_contract import parse_native_manifest
from pt_snap_cli.core.importing.import_service import ImportService
from test.core.test_dataset_import import hashes, source_options


@pytest.fixture(autouse=True)
def isolate(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.delenv("PT_SNAP_DB_PATH", raising=False)


def dataset(tmp_path):
    return (
        ImportService()
        .import_snapshot(dataclasses.replace(source_options(tmp_path, multiple=True), set_focus=False))
        .db_path
    )


def test_native_sparse_ids_positions_device_scope_borrowed_cache_and_readonly(tmp_path):
    root = dataset(tmp_path)
    before = hashes(root)
    cache = ContextCache(maxsize=2)
    try:
        with SnapshotAnalyzer(root, context_cache=cache) as analyzer:
            assert analyzer.get_database_metadata()["status"] == "available"
            overview = analyzer.get_database_overview()
            assert overview["devices"] == [{"device_id": d, "first_event_id": 7, "last_event_id": 87} for d in (0, 1)]
            assert overview["dataset"]["real_event_count"] == 18
            assert overview["dataset"]["structured_frames"] is False
            for device in (0, 1):
                for position in range(9):
                    result = analyzer.execute_query("event", {"id": position * 10 + 7}, device_id=device)
                    assert result["rows"][0]["id"] == position * 10 + 7
                    assert result["scope"]["slice_index"] == position // 2
                    assert len(cache) <= 2
            assert len(analyzer.execute_query("event", {}, device_id=1, slice_index=0)["rows"]) == 2
            peak = analyzer.execute_query("memory_peak")
            assert peak["scope"]["slice_indices"] == [0, 1, 2, 3, 4]
            assert peak["scope"]["boundary_events_included"] is False
            assert peak["rows"][0]["peak_active_event_id"] in range(7, 88, 10)
            assert len(cache) <= 2
            with pytest.raises(InvalidParameterError):
                analyzer.execute_query("event", {"id": -1})
            held = cache.get(root / "device_1/slice_00000.db")
        assert len(cache) > 0
        with held.connect() as conn:
            assert conn.execute("SELECT 1").fetchone()[0] == 1
        resolved = DatasetResolver().inspect(root / "manifest.json")
        assert len(resolved.paths(QueryScope("dataset"))) == 10
        assert len(resolved.paths(QueryScope("event_range", 0, start_event_id=7, end_event_id=87))) == 5
        with pytest.raises(InvalidParameterError):
            resolved.paths(QueryScope("event_range", 0, start_event_id=0, end_event_id=87))
    finally:
        cache.close()
    assert hashes(root) == before
    assert not list(root.rglob("*-wal")) and not list(root.rglob("*-journal"))
    raw = json.loads((root / "manifest.json").read_text())
    with pytest.raises(DatasetContractError):
        parse_manifest(raw)  # Never relabel native-v2 as compatibility-v1.


@pytest.mark.parametrize(
    "part",
    ["manifest", "device", "member", "wal", "journal", "shm", "dangling-wal", "persistent-wal"],
)
def test_native_alias_sidecar_and_persistent_wal_checks_precede_any_sqlite_open(tmp_path, monkeypatch, part):
    root = dataset(tmp_path)
    member = root / "device_1/slice_00004.db"
    if part in ("manifest", "device", "member"):
        path = {"manifest": root / "manifest.json", "device": root / "device_1", "member": member}[part]
        original = tmp_path / ("original-" + part)
        path.rename(original)
        path.symlink_to(original, target_is_directory=part == "device")
    elif part == "persistent-wal":
        with closing(sqlite3.connect(member)) as conn:
            assert conn.execute("PRAGMA journal_mode=WAL").fetchone() == ("wal",)
        assert not Path(str(member) + "-wal").exists()
    else:
        sidecar = Path(str(member) + "-" + part.removeprefix("dangling-"))
        if part.startswith("dangling"):
            sidecar.symlink_to(tmp_path / "missing-sidecar")
        else:
            sidecar.write_bytes(b"live")
    monkeypatch.setattr(sqlite3, "connect", lambda *a, **k: pytest.fail("unsafe artifact opened SQLite"))
    with pytest.raises(DatabaseSchemaError):
        DatasetResolver().inspect(root)


@pytest.mark.parametrize(
    "field,value",
    [
        ("format", "compatibility-v1"),
        ("schemaVersion", 99),
        ("status", "building"),
        ("omittedDevices", [0]),
        ("omittedDevices", [2, 2]),
    ],
)
def test_native_manifest_publication_and_version_validation(tmp_path, field, value):
    root = dataset(tmp_path)
    raw = json.loads((root / "manifest.json").read_text())
    raw[field] = value
    with pytest.raises(DatasetContractError):
        parse_native_manifest(raw)


@pytest.mark.parametrize(
    "field,value",
    [("eventCount", 89), ("sliceCount", True), ("readySlices", [0]), ("sliceCount", 3)],
)
def test_native_manifest_count_and_ready_validation(tmp_path, field, value):
    root = dataset(tmp_path)
    raw = json.loads((root / "manifest.json").read_text())
    raw["devices"]["0"][field] = value
    with pytest.raises(DatasetContractError):
        parse_native_manifest(raw)


@pytest.mark.parametrize(
    "field,value",
    [
        ("startPosition", 1),
        ("endPosition", 999),
        ("index", True),
        ("startEventId", -1),
        ("endEventId", 0),
        ("file", "../escape.db"),
        ("sha256", "bad"),
        ("ready", False),
    ],
)
def test_native_slice_validation(tmp_path, field, value):
    root = dataset(tmp_path)
    raw = json.loads((root / "manifest.json").read_text())
    raw["devices"]["0"]["slices"][0][field] = value
    with pytest.raises(DatasetContractError):
        parse_native_manifest(raw)


@pytest.mark.parametrize(
    "sql",
    [
        "UPDATE trace_entry_0 SET action=99 WHERE id=7",
        "UPDATE block_0 SET id=id+1000 WHERE allocEventId>=0",
        "DELETE FROM pt_snap_block_reference",
        "UPDATE pt_snap_metadata SET source_name='wrong'",
        "DELETE FROM dictionary",
        "DROP TABLE callstack",
        "UPDATE trace_entry_0 SET callstackId=9999 WHERE id=7",
    ],
)
def test_full_native_validation_not_only_manifest_or_member_hash(tmp_path, sql):
    root = dataset(tmp_path)
    member = root / "device_0/slice_00000.db"
    with closing(sqlite3.connect(member)) as conn, conn:
        conn.execute(sql)
    raw = json.loads((root / "manifest.json").read_text())
    raw["devices"]["0"]["slices"][0]["sha256"] = _hash_file(member)
    (root / "manifest.json").write_text(json.dumps(raw))
    with pytest.raises(DatabaseSchemaError):
        DatasetResolver().inspect(root)


def test_unknown_frame_extension_never_promotes_structured_capability_and_generation_changes(
    tmp_path,
):
    root = dataset(tmp_path)
    cache = ContextCache()
    try:
        with SnapshotAnalyzer(root, context_cache=cache) as analyzer:
            analyzer.execute_query("event", {"id": 7})
            old = next(iter(cache._entries.values()))[0]
            old_connection = old._conn
            raw = json.loads((root / "manifest.json").read_text())
            raw["extensions"] = {"structuredFrames": {"version": 999, "present": True}}
            (root / "manifest.json").write_text(json.dumps(raw))
            analyzer.execute_query("event", {"id": 7})
            assert next(iter(cache._entries.values()))[0] is not old
            assert analyzer.get_database_overview()["dataset"]["structured_frames"] is False
            assert not hasattr(analyzer, "import_snapshot")
            with pytest.raises(sqlite3.ProgrammingError):
                old_connection.execute("SELECT 1")
    finally:
        cache.close()
