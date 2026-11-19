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

"""Original deterministic temporary snapshots; no new committed pickle fixtures."""

import copy
import dataclasses
import hashlib
import json
import sqlite3
from contextlib import closing
from pathlib import Path

import pytest

from pt_snap_cli.core.analysis.focus_service import FocusService
from pt_snap_cli.core.common.errors import (
    ImportExecutionError,
    InvalidParameterError,
    SourceChangedError,
)
from pt_snap_cli.core.common.models import ImportOptions
from pt_snap_cli.core.dataset import native_dataset_contract
from pt_snap_cli.core.dataset.dataset_resolver import DatasetResolver
from pt_snap_cli.core.dataset.native_dataset_contract import NATIVE_FORMAT
from pt_snap_cli.core.importing import import_metadata, import_service
from pt_snap_cli.core.importing.dataset_import_backend import DatasetImportBackend
from pt_snap_cli.core.importing.import_service import ImportService
from pt_snap_cli.snapshot.tools.adaptors import sharded_replay
from test.snapshot.test_sharded_replay import lifecycle_data, write_source


@pytest.fixture(autouse=True)
def isolate(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.delenv("PT_SNAP_DB_PATH", raising=False)


def source_options(tmp_path, *, multiple=False):
    data = lifecycle_data()
    for index, event in enumerate(data["device_traces"][0]):
        event["id"] = index * 10 + 7
    if multiple:
        data["device_traces"].append(copy.deepcopy(data["device_traces"][0]))
        data["segments"] += [{**copy.deepcopy(s), "device": 1} for s in data["segments"]]
        data["device_traces"].append([])
    return ImportOptions(write_source(tmp_path, data), tmp_path / "output", events_per_slice=2)


def hashes(root):
    return {
        str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest() for p in root.rglob("*") if p.is_file()
    }


def saved_state(tmp_path):
    service = ImportService()
    options = source_options(tmp_path)
    first = service.import_snapshot(options)
    focus = tmp_path / ".pt-snap/focus.json"
    return (
        service,
        dataclasses.replace(options, force=True),
        first,
        hashes(first.db_path),
        focus.read_bytes(),
    )


def assert_preserved(tmp_path, first, old, focus):
    assert hashes(first.db_path) == old
    assert (tmp_path / ".pt-snap/focus.json").read_bytes() == focus
    assert list(first.db_path.parent.iterdir()) == [first.db_path]


def test_generation_complete_focus_result_and_all_devices(tmp_path):
    options = source_options(tmp_path, multiple=True)
    result = ImportService().import_snapshot(options)
    assert result.dataset_path == result.db_path
    assert result.devices == (0, 1) and result.omitted_devices == (2,)
    assert result.slice_count == 10 and result.format == NATIVE_FORMAT
    assert result.focus_state.callstack_layout == "v2"
    dataset = DatasetResolver().inspect(result.db_path)
    assert dataset.validation.real_event_count == 18
    assert dataset.validation.manifest.devices[0].event_count == 9
    assert result.metadata.source_sha256 == hashlib.sha256(options.snapshot_file.read_bytes()).hexdigest()
    manifest = json.loads((result.db_path / "manifest.json").read_text())
    assert "cacheHash" not in manifest and manifest["format"] == NATIVE_FORMAT
    assert manifest["devices"]["0"]["slices"][-1]["endEventId"] == 87


def test_cache_reuses_full_artifact_without_loading_or_cli_version_invalidation(tmp_path, monkeypatch):
    options = dataclasses.replace(source_options(tmp_path), set_focus=False)
    service = ImportService()
    first = service.import_snapshot(options)
    monkeypatch.setattr(
        service._dataset_backend.replay,
        "stage",
        lambda *a, **k: pytest.fail("cache hit loaded source"),
    )
    monkeypatch.setattr(import_metadata, "__version__", "future-cli-release")
    second = service.import_snapshot(options)
    assert second.reused and second.metadata == first.metadata
    assert second.focus_state is None and not (tmp_path / ".pt-snap").exists()


@pytest.mark.parametrize(
    "axis",
    [
        "content",
        "device",
        "capacity",
        "format",
        "manifest",
        "import",
        "extension",
        "metadata",
        "db-layout",
    ],
)
def test_cache_axes_require_force_and_rebuild(tmp_path, monkeypatch, axis):
    service, options, first, old, focus = saved_state(tmp_path)
    requested = dataclasses.replace(options, force=False)
    if axis == "content":
        options.snapshot_file.write_bytes(options.snapshot_file.read_bytes() + b"trailing-content")
    elif axis == "device":
        requested = dataclasses.replace(requested, device=0)
    elif axis == "capacity":
        requested = dataclasses.replace(requested, events_per_slice=3)
    else:
        constants = {
            "format": (native_dataset_contract, "NATIVE_FORMAT_VERSION"),
            "manifest": (native_dataset_contract, "NATIVE_MANIFEST_VERSION"),
            "import": (native_dataset_contract, "NATIVE_IMPORT_VERSION"),
            "extension": (native_dataset_contract, "NATIVE_EXTENSION_VERSION"),
            "metadata": (import_metadata, "METADATA_SCHEMA_VERSION"),
            "db-layout": (import_metadata, "IMPORT_FORMAT_VERSION"),
        }
        module, key = constants[axis]
        # A manifest protocol upgrade cannot adopt/replace an unknown older schema.
        # This axis is therefore exercised as identity invalidation, not schema relabeling.
        if axis in ("manifest", "metadata", "db-layout"):
            path = first.db_path / "manifest.json"
            data = json.loads(path.read_text())
            identity_key = {
                "manifest": "manifestContractVersion",
                "metadata": "metadataSchemaVersion",
                "db-layout": "importFormatVersion",
            }[axis]
            data["identity"][identity_key] += 1
            if axis != "manifest":
                column = "metadata_schema_version" if axis == "metadata" else "import_format_version"
                data["metadata"][column] += 1
                for device_data in data["devices"].values():
                    for shard in device_data["slices"]:
                        member = first.db_path / shard["file"]
                        with closing(sqlite3.connect(member)) as conn, conn:
                            conn.execute(
                                f"UPDATE pt_snap_metadata SET {column}=?",
                                (data["metadata"][column],),
                            )
                        shard["sha256"] = hashlib.sha256(member.read_bytes()).hexdigest()
            path.write_text(json.dumps(data))
            old = hashes(first.db_path)
        else:
            monkeypatch.setattr(module, key, getattr(module, key) + 1)
    with pytest.raises(ImportExecutionError, match="not reusable"):
        service.import_snapshot(requested)
    assert_preserved(tmp_path, first, old, focus)
    result = service.import_snapshot(dataclasses.replace(requested, force=True))
    assert not result.reused and result.cache_miss_reason == "forced"
    assert DatasetResolver().inspect(result.db_path) is not None


def test_corrupt_late_member_never_reuses_first_ready_shard(tmp_path):
    service, options, first, _, focus = saved_state(tmp_path)
    last = first.db_path / "device_0/slice_00004.db"
    last.write_bytes(b"corrupt last member")
    old = hashes(first.db_path)
    with pytest.raises(ImportExecutionError, match="not reusable"):
        service.import_snapshot(dataclasses.replace(options, force=False))
    assert_preserved(tmp_path, first, old, focus)
    assert not service.import_snapshot(options).reused


@pytest.mark.parametrize(
    "phase",
    ["load", "write", "finalize", "registry-validation", "metadata", "manifest", "validation"],
)
def test_prepublication_failure_preserves_artifact_focus_and_closes_connections(tmp_path, monkeypatch, phase):
    service, options, first, old, focus = saved_state(tmp_path)
    handles = []
    connect = sqlite3.connect

    def counted(*args, **kwargs):
        conn = connect(*args, **kwargs)
        handles.append(conn)
        return conn

    monkeypatch.setattr(sqlite3, "connect", counted)

    def fail(*args, **kwargs):
        raise OSError(phase + " injected failure")

    if phase == "load":
        monkeypatch.setattr("pt_snap_cli.core.splitting.sharded_replay_service.load_snapshot_representation", fail)
    elif phase == "write":
        monkeypatch.setattr(sharded_replay.SnapshotDbHandler, "insert_event", fail)
    elif phase == "finalize":
        monkeypatch.setattr(sharded_replay.BlockRegistry, "finalize", fail)
    elif phase == "registry-validation":
        monkeypatch.setattr(sharded_replay.BlockRegistry, "validate", fail)
    elif phase == "metadata":
        monkeypatch.setattr(service._metadata_service, "write", fail)
    elif phase == "manifest":
        monkeypatch.setattr(import_service.json, "dump", fail)
    elif phase == "validation":
        monkeypatch.setattr(import_service.DatasetResolver, "inspect", fail)
    with pytest.raises(ImportExecutionError, match="injected failure"):
        service.import_snapshot(options)
    assert_preserved(tmp_path, first, old, focus)
    for conn in handles:
        with pytest.raises(sqlite3.ProgrammingError):
            conn.execute("SELECT 1")


@pytest.mark.parametrize("move", ["old", "new"])
@pytest.mark.parametrize("after_move", [False, True])
def test_publication_rename_failure_even_after_mutation_compensates(tmp_path, monkeypatch, move, after_move):
    service, options, first, old, focus = saved_state(tmp_path)
    real = service._dataset_backend._move
    fired = False

    def fault(source, dest, identity):
        nonlocal fired
        selected = source == first.db_path if move == "old" else dest == first.db_path and source.name == "artifact"
        if selected and not fired:
            fired = True
            if after_move:
                real(source, dest, identity)
            raise OSError("publication injected failure")
        real(source, dest, identity)

    monkeypatch.setattr(service._dataset_backend, "_move", fault)
    with pytest.raises(ImportExecutionError, match="publication injected failure"):
        service.import_snapshot(options)
    assert_preserved(tmp_path, first, old, focus)


@pytest.mark.parametrize("existing", [False, True])
def test_focus_mutates_before_raising_restores_exact_bytes_memory_and_artifact(tmp_path, monkeypatch, existing):
    if existing:
        service, options, first, old, focus = saved_state(tmp_path)
    else:
        service = ImportService()
        options = source_options(tmp_path)
    fs = FocusService()
    fs._config._config = {"remember": ["old-memory-state"]}
    service._focus_service = fs

    def mutate_then_fail(*a, **k):
        path = tmp_path / ".pt-snap/focus.json"
        path.write_bytes(b"mutated before raising")
        fs._config._config["remember"].append("changed")
        raise OSError("focus injected failure")

    monkeypatch.setattr(fs._config, "write_project_focus", mutate_then_fail)
    with pytest.raises(ImportExecutionError, match="focus injected failure"):
        service.import_snapshot(options)
    assert fs._config._config == {"remember": ["old-memory-state"]}
    if existing:
        assert_preserved(tmp_path, first, old, focus)
    else:
        assert not (tmp_path / ".pt-snap/focus.json").exists()
        assert not list(options.output_dir.iterdir())


def test_source_change_after_validation_rejects_publication(tmp_path, monkeypatch):
    service, options, first, old, focus = saved_state(tmp_path)
    initial = service._metadata_service.calculate_sha256(options.snapshot_file)
    sequence = iter([initial, "f" * 64])
    monkeypatch.setattr(service._metadata_service, "calculate_sha256", lambda p: next(sequence))
    with pytest.raises(SourceChangedError, match="source changed"):
        service.import_snapshot(options)
    assert_preserved(tmp_path, first, old, focus)


def test_directory_rollback_failure_keeps_recovery_bytes_and_reports(tmp_path, monkeypatch):
    service, options, first, old, focus = saved_state(tmp_path)
    real = service._dataset_backend._move

    def fault(source, dest, identity):
        if source.name == "previous":
            raise OSError("rollback injected failure")
        real(source, dest, identity)

    monkeypatch.setattr(service._dataset_backend, "_move", fault)
    monkeypatch.setattr(
        service._focus_service._config,
        "write_project_focus",
        lambda *a, **k: (_ for _ in ()).throw(OSError("focus failed")),
    )
    with pytest.raises(ImportExecutionError, match="rollback also failed.*Recovery directory"):
        service.import_snapshot(options)
    backup = list(options.output_dir.glob("*.recovery-*/previous"))
    assert len(backup) == 1 and hashes(backup[0]) == old
    assert (tmp_path / ".pt-snap/focus.json").read_bytes() == focus


def test_focus_rollback_failure_preserves_checkpoint_and_restores_old_dataset(tmp_path, monkeypatch):
    service, options, first, old, focus = saved_state(tmp_path)
    fs = service._focus_service

    def mutate(*a, **k):
        (tmp_path / ".pt-snap/focus.json").write_bytes(b"changed")
        raise OSError("focus failed")

    monkeypatch.setattr(fs._config, "write_project_focus", mutate)
    monkeypatch.setattr(fs, "_restore_project_focus", lambda *a: (_ for _ in ()).throw(OSError("restore failed")))
    with pytest.raises(ImportExecutionError, match="focus rollback also failed.*Recovery focus checkpoint"):
        service.import_snapshot(options)
    backups = list((tmp_path / ".pt-snap").glob("*.recovery"))
    assert len(backups) == 1 and backups[0].read_bytes() == focus
    assert hashes(first.db_path) == old


@pytest.mark.parametrize("kind", ["empty", "unknown", "symlink", "dangling", "extra"])
def test_force_never_deletes_unrecognized_targets_or_aliases(tmp_path, kind):
    service = ImportService()
    options = source_options(tmp_path)
    target = DatasetImportBackend.target_path(options.snapshot_file, options.output_dir)
    target.parent.mkdir()
    if kind in ("symlink", "dangling"):
        victim = tmp_path / "victim"
        if kind == "symlink":
            victim.mkdir()
            (victim / "owner").write_text("safe")
        target.symlink_to(victim, target_is_directory=True)
    elif kind == "extra":
        service.import_snapshot(options)
        (target / "unrelated").write_text("preserve")
    else:
        target.mkdir()
        if kind == "unknown":
            (target / "owner").write_text("safe")
    with pytest.raises(ImportExecutionError):
        service.import_snapshot(dataclasses.replace(options, force=True))
    assert target.exists() or target.is_symlink()
    if kind == "symlink":
        assert (victim / "owner").read_text() == "safe"
    if kind == "extra":
        assert (target / "unrelated").read_text() == "preserve"


def test_concurrent_creation_is_not_replaced(tmp_path, monkeypatch):
    service = ImportService()
    options = dataclasses.replace(source_options(tmp_path), set_focus=False)
    target = DatasetImportBackend.target_path(options.snapshot_file, options.output_dir)
    real = service._dataset_backend._move

    def race(source, dest, identity):
        if dest == target:
            dest.mkdir()
            (dest / "racing-owner").write_text("safe")
        real(source, dest, identity)

    monkeypatch.setattr(service._dataset_backend, "_move", race)
    with pytest.raises(ImportExecutionError):
        service.import_snapshot(options)
    assert (target / "racing-owner").read_text() == "safe"
    assert list(target.parent.iterdir()) == [target]


@pytest.mark.parametrize(
    "capacity,fmt,device",
    [
        (0, None, None),
        (True, None, None),
        (2, "single-db", None),
        (None, NATIVE_FORMAT, None),
        (2, "compatibility-v2", None),
        (2, "inline", None),
        (2, "unknown", None),
        (2, None, -1),
        (2, None, True),
    ],
)
def test_invalid_options_precede_loading(tmp_path, capacity, fmt, device):
    with pytest.raises(InvalidParameterError):
        ImportService().import_snapshot(
            ImportOptions(tmp_path / "missing.pkl", events_per_slice=capacity, format=fmt, device=device)
        )


def test_default_single_db_unchanged_and_separate_target(tmp_path):
    options = source_options(tmp_path)
    service = ImportService()
    single = service.import_snapshot(dataclasses.replace(options, events_per_slice=None, set_focus=False))
    native = service.import_snapshot(dataclasses.replace(options, set_focus=False))
    assert single.db_path.is_file() and single.dataset_path is None
    assert single.format == "single-db" and native.db_path.is_dir()
    assert service.import_snapshot(dataclasses.replace(options, events_per_slice=None, set_focus=False)).reused
