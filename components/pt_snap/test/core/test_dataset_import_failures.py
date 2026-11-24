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
import os
from pathlib import Path

import pytest

from pt_snap_cli.core.common.errors import ImportExecutionError, SourceChangedError
from pt_snap_cli.core.importing.import_service import ImportService
from pt_snap_cli.core.splitting import sharded_replay_service
from pt_snap_cli.core.splitting.split_service import SplitService
from test.core.test_dataset_import import assert_preserved, hashes, saved_state, source_options


@pytest.fixture(autouse=True)
def isolate(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.delenv("PT_SNAP_DB_PATH", raising=False)


@pytest.mark.parametrize("fail", [False, True])
def test_directory_descriptors_closed_on_success_and_failure(tmp_path, monkeypatch, fail):
    service, options, first, old, focus = saved_state(tmp_path)
    descriptors = []
    identities = []
    original = SplitService._stage_identity

    def track(path):
        result = original(path)
        identities.append(result)
        if result[2] is not None:
            descriptors.append(result[2])
        return result

    monkeypatch.setattr(SplitService, "_stage_identity", track)
    if fail:
        monkeypatch.setattr(
            service._dataset_backend.replay,
            "stage",
            lambda *a, **k: (_ for _ in ()).throw(OSError("load failure")),
        )
        with pytest.raises(ImportExecutionError):
            service.import_snapshot(options)
        assert_preserved(tmp_path, first, old, focus)
    else:
        service.import_snapshot(options)
    assert identities  # Windows uses path identity rather than directory descriptors.
    assert bool(descriptors) == (os.name != "nt")
    assert list(first.db_path.parent.iterdir()) == [first.db_path]
    for fd in descriptors:
        with pytest.raises(OSError):
            os.fstat(fd)


def test_actual_source_mutation_during_load_rejects_before_publish(tmp_path, monkeypatch):
    service, options, first, old, focus = saved_state(tmp_path)
    original = sharded_replay_service.load_snapshot_representation

    def changed(path):
        data = original(path)
        path.write_bytes(path.read_bytes() + b"actual concurrent source change")
        return data

    monkeypatch.setattr(sharded_replay_service, "load_snapshot_representation", changed)
    with pytest.raises(SourceChangedError):
        service.import_snapshot(options)
    assert_preserved(tmp_path, first, old, focus)


def test_existing_target_changed_during_staging_is_not_adopted(tmp_path, monkeypatch):
    service, options, first, old, focus = saved_state(tmp_path)
    original = service._dataset_backend.replay.stage

    def changed(*a, **k):
        result = original(*a, **k)
        (first.db_path / "racing-owner").write_text("preserve")
        return result

    monkeypatch.setattr(service._dataset_backend.replay, "stage", changed)
    with pytest.raises(ImportExecutionError, match="preserved"):
        service.import_snapshot(options)
    assert (first.db_path / "racing-owner").read_text() == "preserve"
    current = hashes(first.db_path)
    current.pop("racing-owner")
    assert current == old
    assert (tmp_path / ".pt-snap/focus.json").read_bytes() == focus
    assert list(options.output_dir.iterdir()) == [first.db_path]


def test_substituted_stage_is_not_deleted_or_followed(tmp_path, monkeypatch):
    options = dataclasses.replace(source_options(tmp_path), set_focus=False)
    service = ImportService()
    original = service._dataset_backend.replay.stage
    stages = []

    def substituted(*a, **k):
        result = original(*a, **k)
        stage = result.directory.parent
        stage.rename(tmp_path / "displaced-owned-stage")
        stage.mkdir()
        (stage / "unknown-owner").write_text("preserve")
        stages.append(stage)
        return result

    monkeypatch.setattr(service._dataset_backend.replay, "stage", substituted)
    with pytest.raises(ImportExecutionError, match="cleanup failed.*preserved"):
        service.import_snapshot(options)
    assert (stages[0] / "unknown-owner").read_text() == "preserve"
    assert not list(options.output_dir.glob("*.pt-snap-native-v2"))


def test_committed_recovery_cleanup_failure_preserves_old_bytes_reports_truthfully(tmp_path, monkeypatch):
    service, options, first, old, _ = saved_state(tmp_path)
    original = service._dataset_backend._remove

    def failed(path, identity):
        if path.name == "previous":
            raise OSError("cleanup injected failure")
        original(path, identity)

    monkeypatch.setattr(service._dataset_backend, "_remove", failed)
    with pytest.raises(ImportExecutionError, match="publication committed.*preserved evidence"):
        service.import_snapshot(options)
    backups = list(options.output_dir.glob("*.recovery-*/previous"))
    assert len(backups) == 1 and hashes(backups[0]) == old
    assert first.db_path.exists()  # Do not falsely report rollback after commit.


@pytest.mark.parametrize("atomic_fault", [False, True])
def test_real_focus_write_mutation_before_error_and_late_restore_error(tmp_path, monkeypatch, atomic_fault):
    service, options, first, old, focus = saved_state(tmp_path)
    options = dataclasses.replace(options, device=0)
    path = tmp_path / ".pt-snap/focus.json"
    if atomic_fault:
        original = os.replace

        def fail_after_rename(source, destination):
            original(source, destination)
            if Path(destination) == path:
                raise OSError("focus rename completed then failed")

        monkeypatch.setattr(os, "replace", fail_after_rename)
    else:
        original = service._focus_service._config.write_project_focus

        def fail_after_write(*a, **k):
            original(*a, **k)
            raise OSError("focus write completed then failed")

        monkeypatch.setattr(service._focus_service._config, "write_project_focus", fail_after_write)
    with pytest.raises(ImportExecutionError, match="focus .*completed then failed") as error:
        service.import_snapshot(options)
    assert "rollback also failed" not in str(error.value)
    assert_preserved(tmp_path, first, old, focus)


def test_parent_finding_substituted_recovery_is_preserved_and_reported(tmp_path, monkeypatch):
    service, options, first, old, focus = saved_state(tmp_path)
    original = service._dataset_backend._move
    displaced = tmp_path / "safe-displaced-previous"
    markers = []

    def fault(source, dest, identity):
        if source.name == "artifact":
            previous = next(options.output_dir.glob("*.recovery-*/previous"))
            assert previous.resolve() == previous and not previous.is_symlink()
            assert displaced.resolve() == displaced and not displaced.exists()
            previous.rename(displaced)
            previous.mkdir()
            marker = previous / "foreign-owner"
            marker.write_text("must survive")
            markers.append(marker)
            raise OSError("publication failed after recovery substitution")
        original(source, dest, identity)

    monkeypatch.setattr(service._dataset_backend, "_move", fault)
    with pytest.raises(ImportExecutionError, match="directory rollback also failed.*Recovery directory"):
        service.import_snapshot(options)
    assert hashes(displaced) == old
    assert markers[0].read_text() == "must survive"
    assert (tmp_path / ".pt-snap/focus.json").read_bytes() == focus
    assert list(options.output_dir.glob("*.stage-*"))


def test_parent_finding_same_inode_focus_checkpoint_is_not_trusted(tmp_path, monkeypatch):
    service, options, first, old, _ = saved_state(tmp_path)
    original = service._focus_service._config.write_project_focus
    checkpoints = []

    def fault(*a, **k):
        original(*a, **k)
        backup = next((tmp_path / ".pt-snap").glob("*.recovery"))
        inode = backup.stat().st_ino
        backup.write_bytes(b"same inode, foreign checkpoint bytes")
        assert backup.stat().st_ino == inode
        checkpoints.append(backup)
        raise OSError("focus failed after checkpoint corruption")

    monkeypatch.setattr(service._focus_service._config, "write_project_focus", fault)
    with pytest.raises(ImportExecutionError, match="focus rollback also failed.*checkpoint content changed"):
        service.import_snapshot(dataclasses.replace(options, device=0))
    assert hashes(first.db_path) == old
    assert checkpoints[0].read_bytes() == b"same inode, foreign checkpoint bytes"
    assert (tmp_path / ".pt-snap/focus.json").read_bytes() != checkpoints[0].read_bytes()


@pytest.mark.parametrize("bad", ["empty", "corrupt", "absent-device", "alias-parent"])
def test_dataset_input_and_output_prerequisites(tmp_path, bad):
    options = source_options(tmp_path)
    if bad == "empty":
        from test.snapshot.test_sharded_replay import write_source

        options = dataclasses.replace(
            options, snapshot_file=write_source(tmp_path, {"segments": [], "device_traces": [[]]})
        )
    elif bad == "corrupt":
        options.snapshot_file.write_bytes(b"not pickle")
    elif bad == "absent-device":
        options = dataclasses.replace(options, device=9)
    elif bad == "alias-parent":
        victim = tmp_path / "other-owner"
        victim.mkdir()
        alias = tmp_path / "alias"
        alias.symlink_to(victim, target_is_directory=True)
        options = dataclasses.replace(options, output_dir=alias / "nested")
    with pytest.raises(ImportExecutionError):
        ImportService().import_snapshot(options)
    if bad == "alias-parent":
        assert list(victim.iterdir()) == []
