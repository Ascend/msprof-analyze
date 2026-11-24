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

"""Synthetic finalized artifacts: no pickle, metadata or optional reference tables."""

import hashlib
import json
import os
import sqlite3
from contextlib import closing
from pathlib import Path

import pytest
from typer.testing import CliRunner

from pt_snap_cli.api import SnapshotAnalyzer
from pt_snap_cli.cli import app
from pt_snap_cli.completion import complete_device_ids
from pt_snap_cli.core.analysis.focus_service import FocusService
from pt_snap_cli.core.cache.context_cache import ContextCache
from pt_snap_cli.core.common.errors import (
    DatabaseSchemaError,
    InvalidDeviceError,
    InvalidParameterError,
    QueryExecutionError,
    TemplateNotFoundError,
    TemplateRenderError,
)
from pt_snap_cli.core.dataset.dataset_contract import (
    ACTION_NAMES,
    BLOCK_STATES,
    DatasetContractError,
    QueryScope,
    validate_dataset,
)
from pt_snap_cli.core.dataset.dataset_resolver import DatasetResolver

runner = CliRunner()


@pytest.fixture(autouse=True)
def isolate(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("PT_SNAP_DB_PATH", raising=False)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)


def make_dataset(root, devices=(0, 2), slices=3):
    root.mkdir()
    data = {
        "schemaVersion": 1,
        "status": "complete",
        "sourceFile": "/archived/missing.pkl",
        "cacheHash": "",
        "eventsPerSlice": 2,
        "devices": {},
    }
    for device in devices:
        directory = root / f"device_{device}"
        directory.mkdir()
        records = []
        for index in range(slices):
            file = f"device_{device}/slice_{index:05d}.db"
            records.append(
                {
                    "index": index,
                    "startEventId": index * 2,
                    "endEventId": index * 2 + 1,
                    "file": file,
                    "ready": True,
                }
            )
            with closing(sqlite3.connect(root / file)) as conn, conn:
                conn.executescript(
                    'CREATE TABLE dictionary ("table" TEXT,"column" TEXT,"key" TEXT,"value" TEXT);'
                    f"CREATE TABLE trace_entry_{device} (id INTEGER PRIMARY KEY, action INTEGER,"
                    "address INTEGER,size INTEGER,stream INTEGER,allocated INTEGER,active INTEGER,"
                    "reserved INTEGER,callstack TEXT);"
                    f"CREATE TABLE block_{device} (id INTEGER PRIMARY KEY,address INTEGER,size INTEGER,"
                    "requestedSize INTEGER,state INTEGER,allocEventId INTEGER,freeEventId INTEGER);"
                )
                conn.executemany(
                    "INSERT INTO dictionary VALUES (?,?,?,?)",
                    [(f"trace_entry_{device}", "action", str(key), value) for key, value in enumerate(ACTION_NAMES)]
                    + [(f"block_{device}", "state", str(key), value) for key, value in BLOCK_STATES],
                )
                conn.executemany(
                    f"INSERT INTO trace_entry_{device} VALUES (?,4,100,8,0,8,8,16,?)",
                    [(event, f"device{device}:event{event}") for event in range(index * 2, index * 2 + 2)],
                )
                conn.execute(f"INSERT INTO trace_entry_{device} VALUES (-1,2,100,16,0,999,999,999,'boundary')")
        data["devices"][str(device)] = {
            "eventCount": slices * 2,
            "sliceCount": slices,
            "readySlices": list(range(slices)),
            "slices": records,
        }
    (root / "manifest.json").write_text(json.dumps(data), encoding="utf-8")
    return root


def hashes(root):
    return {
        str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest() for p in root.rglob("*") if p.is_file()
    }


@pytest.mark.parametrize("manifest_path", [False, True])
def test_dataset_focus_readonly_and_complete_addressing(tmp_path, manifest_path):
    root = make_dataset(tmp_path / "capture.msinsight")
    path = root / "manifest.json" if manifest_path else root
    before = hashes(root)
    with SnapshotAnalyzer() as analyzer:
        state = analyzer.set_focus(str(path), device_id=2)
        assert state.available_devices == [0, 2]
        assert state.callstack_layout == "v1"
        assert not (tmp_path / ".pt-snap/focus.json").exists()
        overview = analyzer.get_database_overview()
        assert overview["devices"] == [{"device_id": d, "first_event_id": 0, "last_event_id": 5} for d in (0, 2)]
        assert overview["dataset"]["format"] == "compatibility-v1"
        assert overview["dataset"]["structured_frames"] is False
        assert overview["dataset"]["text_callstacks"] is True
        assert overview["dataset"]["cross_slice_queries"] is True
        assert overview["dataset"]["boundary_event_count"] == 6
        assert analyzer.get_database_metadata()["status"] == "unavailable"
        for device in (0, 2):
            for event in range(6):
                result = analyzer.execute_query("event", {"id": event}, device_id=device)
                assert result["rows"][0]["callstack"] == f"device{device}:event{event}"
                assert result["scope"]["slice_index"] == event // 2
        assert len(analyzer.context_cache) <= 4
    dataset = DatasetResolver().inspect(path)
    assert dataset is not None
    assert len(dataset.paths(QueryScope("dataset"))) == 6
    assert len(dataset.paths(QueryScope("device", 2))) == 3
    assert len(dataset.paths(QueryScope("event_range", 2, start_event_id=1, end_event_id=4))) == 3
    assert before == hashes(root)
    assert not list(root.rglob("*-journal"))
    assert not list(root.rglob("*-wal"))


def test_precedence_device_and_completion(tmp_path, monkeypatch):
    root = make_dataset(tmp_path / "dataset")
    service = FocusService()
    service.set_global_focus(root, 0)
    service.set_project_focus(root / "manifest.json", 2)
    with SnapshotAnalyzer() as analyzer:
        assert analyzer.execute_query("event", {"id": 4})["device_id"] == 2
        assert analyzer.execute_query("event", {"id": 4}, device_id=0)["device_id"] == 0
    assert complete_device_ids() == ["0", "2"]
    monkeypatch.setenv("PT_SNAP_DB_PATH", str(root))
    with SnapshotAnalyzer() as analyzer:
        assert analyzer.execute_query("event", {"id": 4})["device_id"] == 0
    with SnapshotAnalyzer(root / "manifest.json", 2) as analyzer:
        assert analyzer.execute_query("event", {"id": 4})["device_id"] == 2
    before = json.loads((tmp_path / ".pt-snap/focus.json").read_text())
    monkeypatch.delenv("PT_SNAP_DB_PATH")
    state = service.set_device(0)
    assert state.available_devices == [0, 2]
    assert set(json.loads((tmp_path / ".pt-snap/focus.json").read_text())) == {
        "db_path",
        "device_id",
    }
    assert set(before) == {"db_path", "device_id"}


@pytest.mark.parametrize(
    "template,params,slice_index,error",
    [
        ("event", {"id": -1}, None, InvalidParameterError),
        ("event", {"id": 6}, None, InvalidParameterError),
        ("event", {"id": 4}, 0, InvalidParameterError),
        ("event", {"min_id": -1}, 0, InvalidParameterError),
        ("event", {"min_id": 3, "max_id": 2}, None, InvalidParameterError),
        ("event", {}, 99, InvalidParameterError),
        ("event", {}, True, InvalidParameterError),
        ("event", {"unknown": 0}, 0, TemplateRenderError),
        ("leak_detection", {}, 0, QueryExecutionError),
        ("missing_template", {}, None, TemplateNotFoundError),
    ],
)
def test_unsupported_scope_errors(tmp_path, template, params, slice_index, error):
    root = make_dataset(tmp_path / "dataset")
    with SnapshotAnalyzer(root) as analyzer, pytest.raises(error):
        analyzer.execute_query(template, params, slice_index=slice_index)


def test_slice_and_single_slice_range_exclude_boundary_and_preserve_filters(tmp_path):
    root = make_dataset(tmp_path / "dataset")
    with SnapshotAnalyzer(root) as analyzer:
        result = analyzer.execute_query("event", slice_index=1, exact_total=True)
        assert [row["id"] for row in result["rows"]] == [2, 3]
        assert result["total"] == 2 and result["total_is_exact"]
        assert result["scope"]["boundary_events_included"] is False
        assert analyzer.execute_query("event", {"min_id": 2, "max_id": 3})["rows"] == result["rows"]
        assert analyzer.execute_query("event", {"id": 2, "min_id": 3})["rows"] == []
        with pytest.raises(InvalidDeviceError):
            analyzer.execute_query("event", {"id": 0}, device_id=99)
        with pytest.raises(InvalidDeviceError):
            analyzer.set_focus(str(root), device_id=99)


@pytest.mark.parametrize(
    "failure",
    ["building", "version", "missing", "duplicate", "symlink", "wal", "corrupt", "readiness"],
)
def test_invalid_dataset_is_not_partial_focus(tmp_path, failure):
    root = make_dataset(tmp_path / "dataset")
    manifest = root / "manifest.json"
    data = json.loads(manifest.read_text())
    if failure in ("building", "version", "readiness"):
        if failure == "building":
            data["status"] = "building"
        elif failure == "version":
            data["schemaVersion"] = 999
        else:
            data["devices"]["0"]["slices"][0]["ready"] = False
        manifest.write_text(json.dumps(data))
    elif failure == "duplicate":
        manifest.write_text(
            manifest.read_text().replace('"schemaVersion": 1', '"schemaVersion": 1, "schemaVersion": 1')
        )
    elif failure == "symlink":
        # Keep original data in place; replace the directory input with an alias.
        alias = tmp_path / "alias"
        alias.symlink_to(root, target_is_directory=True)
        root = alias
    elif failure == "wal":
        (root / "device_0/slice_00000.db-wal").touch()
    elif failure == "corrupt":
        (root / "device_0/slice_00000.db").write_bytes(b"not SQLite")
    else:
        (root / "device_0/slice_00000.db").unlink()
    with SnapshotAnalyzer() as analyzer:
        with pytest.raises(ValueError):
            analyzer.set_focus(str(root))
        assert analyzer.get_focus().db_path is None
        with pytest.raises(ValueError):
            analyzer.get_database_overview(str(root))
    with pytest.raises(DatabaseSchemaError):
        FocusService().set_project_focus(root)
    assert not (tmp_path / ".pt-snap/focus.json").exists()


def test_content_generation_reopens_cached_context_and_borrowed_close(tmp_path):
    root = make_dataset(tmp_path / "dataset")
    cache = ContextCache(maxsize=1)
    try:
        with SnapshotAnalyzer(root, context_cache=cache) as analyzer:
            analyzer.execute_query("event", {"id": 0})
            path = root / "device_0/slice_00000.db"
            old = cache.get(path, generation=DatasetResolver().inspect(root).fingerprint)
            stamp = path.stat()
            with closing(sqlite3.connect(path)) as conn, conn:
                conn.execute("UPDATE trace_entry_0 SET callstack='modified:evt0' WHERE id=0")
            os.utime(path, ns=(stamp.st_atime_ns, stamp.st_mtime_ns))
            assert analyzer.execute_query("event", {"id": 0})["rows"][0]["callstack"] == "modified:evt0"
            assert old._conn is None
            manifest = root / "manifest.json"
            data = json.loads(manifest.read_text())
            data["cacheHash"] = "new-generation"
            manifest.write_text(json.dumps(data))
            analyzer.execute_query("event", {"id": 0})
            analyzer.execute_query("event", {"id": 4})
            assert len(cache) == 1
        assert len(cache) == 1  # Injected cache still caller-owned.
        with pytest.raises(RuntimeError, match="closed"):
            analyzer.get_focus()
    finally:
        cache.close()
    assert len(cache) == 0


def test_single_db_native_and_inline_keep_original_query_behavior(tmp_path):
    root = make_dataset(tmp_path / "dataset")
    path = root / "device_0/slice_00000.db"
    for native in (False, True):
        if native:
            with closing(sqlite3.connect(path)) as conn, conn:
                conn.execute("CREATE TABLE callstack (id INTEGER PRIMARY KEY, callstack TEXT)")
                conn.execute("INSERT INTO callstack VALUES (0, 'native')")
                conn.execute("ALTER TABLE trace_entry_0 DROP COLUMN callstack")
                conn.execute("ALTER TABLE trace_entry_0 ADD COLUMN callstackId INTEGER")
                conn.execute("UPDATE trace_entry_0 SET callstackId=0")
        with SnapshotAnalyzer(path) as analyzer:
            assert analyzer.get_focus().callstack_layout == ("v2" if native else "v1")
            assert analyzer.execute_query("event", {"id": -1})["rows"][0]["id"] == -1
            assert analyzer.get_database_overview()["devices"][0]["first_event_id"] == 0
            with pytest.raises(InvalidParameterError):
                analyzer.execute_query("event", slice_index=0)
        if native:
            with pytest.raises(DatabaseSchemaError):
                DatasetResolver().inspect(root)  # Never label native v2 as compatibility v1.


def test_no_manifest_private_staging_is_rejected(tmp_path):
    root = tmp_path / "private-native-staging"
    root.mkdir()
    with pytest.raises(DatabaseSchemaError, match="manifest.json"):
        DatasetResolver().inspect(root)
    assert not list(root.iterdir())


def test_single_slice_default_is_full_real_trace(tmp_path):
    root = make_dataset(tmp_path / "dataset", slices=1)
    with SnapshotAnalyzer(root) as analyzer:
        assert [row["id"] for row in analyzer.execute_query("event")["rows"]] == [0, 1]


def test_cli_releases_owned_context_and_sqlite_is_readonly(tmp_path, monkeypatch):
    root = make_dataset(tmp_path / "dataset")
    opened = []
    original = ContextCache.get

    def get(cache, path, **kwargs):
        context = original(cache, path, **kwargs)
        opened.append(context)
        with context.connect() as conn, pytest.raises(sqlite3.OperationalError, match="readonly"):
            conn.execute("CREATE TABLE illegal (id INTEGER)")
        return context

    monkeypatch.setattr(ContextCache, "get", get)
    result = runner.invoke(app, ["query", str(root), "--template-use", "event", "--params", '{"id": 0}', "--json"])
    assert result.exit_code == 0, result.output
    assert opened and all(context._conn is None for context in opened)
    failure = runner.invoke(
        app,
        [
            "query",
            str(root),
            "--template-use",
            "event",
            "--params",
            '{"id": 0}',
            "--timeout",
            "not-a-number",
            "--json",
        ],
    )
    assert failure.exit_code != 0
    assert all(context._conn is None for context in opened)


@pytest.mark.parametrize("suffix", ["-wal", "-journal", "-shm"])
@pytest.mark.parametrize("dangling", [False, True])
@pytest.mark.parametrize("bare", [False, True])
def test_live_sidecar_rejected_before_any_sqlite_open(tmp_path, monkeypatch, suffix, dangling, bare):
    root = make_dataset(tmp_path / "dataset")
    # The last member must be checked before even the first slice is opened.
    sidecar = root / f"device_2/slice_00002.db{suffix}"
    if dangling:
        sidecar.symlink_to(tmp_path / "missing-sidecar-target")
        assert sidecar.is_symlink() and not sidecar.exists()
        original_target = sidecar.readlink()
    else:
        sidecar.touch()
    before = hashes(root)
    inventory = sorted(str(p.relative_to(root)) for p in root.rglob("*"))

    def forbidden(*args, **kwargs):
        raise AssertionError("SQLite opened before live sidecar rejection")

    monkeypatch.setattr(sqlite3, "connect", forbidden)
    with pytest.raises(
        DatasetContractError if bare else DatabaseSchemaError,
        match="aliased SQLite sidecar" if dangling else "live SQLite sidecar",
    ):
        validate_dataset(root) if bare else DatasetResolver().inspect(root)
    assert before == hashes(root)
    assert inventory == sorted(str(p.relative_to(root)) for p in root.rglob("*"))
    if dangling:
        # Preserve the OS-reported target spelling, including Windows \?\ paths.
        assert sidecar.readlink() == original_target


@pytest.mark.parametrize("manifest_path", [False, True])
@pytest.mark.parametrize("operation", ["inspect", "p0", "focus", "api", "cli"])
def test_checkpointed_wal_read_preserves_database_bytes(tmp_path, monkeypatch, manifest_path, operation):
    root = make_dataset(tmp_path / "dataset")
    member = root / "device_2/slice_00002.db"
    # A genuine checkpointed WAL database retains header versions 2/2 after
    # the last writer closes, even though no WAL/SHM file remains on disk.
    with closing(sqlite3.connect(member)) as conn:
        assert conn.execute("PRAGMA journal_mode=WAL").fetchone() == ("wal",)
    with member.open("rb") as source:
        assert source.read(20)[18:20] == b"\x02\x02"
    assert not list(root.rglob("*-wal")) and not list(root.rglob("*-shm"))
    before = hashes(root)
    opened = []
    original = sqlite3.connect

    def connect(*args, **kwargs):
        opened.append(args[0])
        return original(*args, **kwargs)

    monkeypatch.setattr(sqlite3, "connect", connect)
    path = root / "manifest.json" if manifest_path else root
    if operation == "inspect":
        assert DatasetResolver().inspect(path).validation.real_event_count == 12
    elif operation == "p0":
        assert validate_dataset(root).real_event_count == 12
    elif operation == "focus":
        assert FocusService().set_project_focus(path).callstack_layout == "v1"
    elif operation == "api":
        with SnapshotAnalyzer(path) as analyzer:
            assert analyzer.execute_query("event", {"id": 5}, device_id=2)["rows"][0]["id"] == 5
            assert analyzer.execute_query("event", {"id": 5}, device_id=2)["rows"][0]["id"] == 5
    else:
        result = runner.invoke(
            app,
            [
                "query",
                str(path),
                "--template-use",
                "event",
                "--device",
                "2",
                "--params",
                '{"id":5}',
                "--json",
            ],
        )
        assert result.exit_code == 0, result.output
        assert json.loads(result.output)["rows"][0]["id"] == 5
    after = hashes(root)
    assert before == {name: after[name] for name in before}
    # SQLite's read-only WAL protocol may create transport sidecars, but must
    # neither modify a source DB/manifest nor commit any pages to the WAL.
    relative = str(member.relative_to(root))
    assert set(after) - set(before) <= {relative + "-wal", relative + "-shm"}
    wal = Path(str(member) + "-wal")
    assert not wal.exists() or wal.stat().st_size == 0
    assert opened and all("mode=ro" in str(uri) and "immutable=1" not in str(uri) for uri in opened)


@pytest.mark.parametrize("alias_parent", [False, True])
@pytest.mark.parametrize("bare", [False, True])
def test_member_alias_rejected_before_header_read(tmp_path, monkeypatch, alias_parent, bare):
    source = make_dataset(tmp_path / "source", devices=(0,), slices=1)
    root = tmp_path / "dataset"
    root.mkdir()
    (root / "manifest.json").write_bytes((source / "manifest.json").read_bytes())
    if alias_parent:
        (root / "device_0").symlink_to(source / "device_0", target_is_directory=True)
    else:
        (root / "device_0").mkdir()
        (root / "device_0/slice_00000.db").symlink_to(source / "device_0/slice_00000.db")
    before = hashes(source)
    original = Path.open

    def open_path(path, *args, **kwargs):
        if path.suffix == ".db":
            raise AssertionError("Member alias followed before header rejection")
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", open_path)
    with pytest.raises(DatasetContractError if bare else DatabaseSchemaError, match="symlink"):
        validate_dataset(root) if bare else DatasetResolver().inspect(root)
    monkeypatch.setattr(Path, "open", original)
    assert before == hashes(source)


def test_manifest_change_during_validation_fails(tmp_path, monkeypatch):
    import pt_snap_cli.core.dataset.dataset_resolver as module

    root = make_dataset(tmp_path / "dataset")
    original = module.validate_dataset

    def validate(path, **kwargs):
        result = original(path, **kwargs)
        manifest = root / "manifest.json"
        data = json.loads(manifest.read_text())
        data["cacheHash"] = "replaced"
        manifest.write_text(json.dumps(data))
        return result

    monkeypatch.setattr(module, "validate_dataset", validate)
    with pytest.raises(DatabaseSchemaError, match="changed during inspection"):
        DatasetResolver().inspect(root)


def test_unknown_extension_never_promotes_frames(tmp_path):
    root = make_dataset(tmp_path / "dataset")
    path = root / "manifest.json"
    data = json.loads(path.read_text())
    data["extensions"] = {"frames": {"version": 999}}
    path.write_text(json.dumps(data))
    assert DatasetResolver().inspect(root).to_dict()["structured_frames"] is False
