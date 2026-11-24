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

"""Focus compensation preserves exact bytes, configuration state, and recovery evidence."""

import copy
import os
import sqlite3
from contextlib import closing
from pathlib import Path

import pytest

import pt_snap_cli.core.analysis.focus_service as focus_module
from pt_snap_cli.config import Config
from pt_snap_cli.core.analysis.focus_service import FocusService
from pt_snap_cli.core.common.errors import ImportExecutionError


@pytest.fixture
def focus(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("PT_SNAP_DB_PATH", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    service = FocusService(Config())
    path = service._config.project_focus_path()
    path.parent.mkdir()
    original = b'{ "db_path" : "previous.db", "extra" : [1,2] }\n'
    path.write_bytes(original)
    service._config._config = {"nested": {"value": "original"}}
    return service, path, original


@pytest.fixture
def checkpoint_descriptors(monkeypatch):
    descriptors = []
    mkstemp = focus_module.tempfile.mkstemp

    def track(*args, **kwargs):
        descriptor, name = mkstemp(*args, **kwargs)
        descriptors.append(descriptor)
        return descriptor, name

    monkeypatch.setattr(focus_module.tempfile, "mkstemp", track)
    yield descriptors
    leaked = []
    for descriptor in descriptors:
        try:
            os.fstat(descriptor)
        except OSError:
            continue
        os.close(descriptor)
        leaked.append(descriptor)
    assert not leaked, "focus checkpoint descriptors must close on every outcome"


def test_short_checkpoint_writes_restore_exact_focus_and_memory(focus, checkpoint_descriptors, monkeypatch):
    service, path, original = focus
    old_state = copy.deepcopy(service._config._config)
    write = os.write
    writes = []

    def short_write(descriptor, content):
        writes.append(len(content))
        return write(descriptor, content[:3])

    monkeypatch.setattr(focus_module.os, "write", short_write)
    with pytest.raises(RuntimeError, match="focus mutation failed"):
        with service.project_focus_transaction():
            path.write_bytes(b"partial focus")
            service._config._config["nested"]["value"] = "changed"
            raise RuntimeError("focus mutation failed")
    assert path.read_bytes() == original
    assert service._config._config == old_state
    assert len(writes) > 1
    assert len(checkpoint_descriptors) == 1
    assert list(path.parent.iterdir()) == [path]


def test_zero_checkpoint_write_fails_before_any_focus_mutation(focus, checkpoint_descriptors, monkeypatch):
    service, path, original = focus
    monkeypatch.setattr(focus_module.os, "write", lambda *args: 0)
    with pytest.raises(OSError, match="recovery checkpoint"):
        with service.project_focus_transaction():
            pytest.fail("a failed checkpoint must prevent publication")
    assert path.read_bytes() == original
    assert len(checkpoint_descriptors) == 1
    assert list(path.parent.iterdir()) == [path]


def test_checkpoint_permission_fallback_is_verified_and_cleaned(focus, checkpoint_descriptors, monkeypatch):
    service, path, _ = focus
    with monkeypatch.context() as patch:
        patch.delattr(focus_module.os, "fchmod", raising=False)
        with service.project_focus_transaction():
            path.write_bytes(b"committed focus")
    assert path.read_bytes() == b"committed focus"
    assert len(checkpoint_descriptors) == 1
    assert list(path.parent.iterdir()) == [path]


def test_late_restore_error_does_not_hide_successful_rollback(focus, monkeypatch):
    service, path, original = focus
    replace = os.replace

    def restore_then_raise(source, destination):
        replace(source, destination)
        raise OSError("late rename error")

    monkeypatch.setattr(focus_module.os, "replace", restore_then_raise)
    with pytest.raises(RuntimeError, match="original focus failure"):
        with service.project_focus_transaction():
            path.write_bytes(b"new focus")
            raise RuntimeError("original focus failure")
    assert path.read_bytes() == original
    assert list(path.parent.iterdir()) == [path]


def test_unrestored_focus_reports_failure_and_keeps_exact_recovery(focus, monkeypatch):
    service, path, original = focus
    monkeypatch.setattr(service, "_restore_project_focus", lambda *args: None)
    with pytest.raises(ImportExecutionError, match="rollback also failed") as caught:
        with service.project_focus_transaction():
            path.write_bytes(b"new focus")
            raise RuntimeError("focus failed")
    backups = list(path.parent.glob("*.recovery"))
    assert len(backups) == 1
    assert backups[0].read_bytes() == original
    assert str(backups[0]) in str(caught.value)
    assert "prior focus existed: True" in str(caught.value)
    assert path.read_bytes() == b"new focus"
    assert isinstance(caught.value.__cause__, RuntimeError)


def test_cleanup_failure_preserves_checkpoint_without_masking_commit(focus, monkeypatch):
    service, path, original = focus
    verify = service._verify_checkpoint
    committed = False

    def fail_cleanup(checkpoint, identity):
        if committed:
            raise OSError("cleanup denied")
        verify(checkpoint, identity)

    monkeypatch.setattr(FocusService, "_verify_checkpoint", staticmethod(fail_cleanup))
    with service.project_focus_transaction():
        path.write_bytes(b"committed focus")
        committed = True
    backups = list(path.parent.glob("*.recovery"))
    assert len(backups) == 1
    assert backups[0].read_bytes() == original
    assert path.read_bytes() == b"committed focus"


def test_failure_before_first_focus_write_leaves_no_focus_or_checkpoint(focus):
    service, path, _ = focus
    path.unlink()
    with pytest.raises(RuntimeError, match="before write"):
        with service.project_focus_transaction():
            raise RuntimeError("before write")
    assert not path.exists()
    assert list(path.parent.iterdir()) == []


def test_unsafe_focus_and_substituted_checkpoint_are_not_deleted(focus):
    service, path, original = focus
    unsafe = path.parent / "directory"
    unsafe.mkdir()
    with pytest.raises(OSError, match="Unsafe project focus"):
        service._safe_focus_path(unsafe)
    with pytest.raises(OSError, match="checkpoint substituted"):
        service._verify_checkpoint(path, (-1, -1))
    assert unsafe.is_dir()
    assert path.read_bytes() == original


def test_invalid_focused_schema_keeps_focus_but_has_no_available_devices(focus):
    service, path, _ = focus
    db = path.parent.parent / "invalid.db"
    with closing(sqlite3.connect(db)) as conn, conn:
        conn.execute("CREATE TABLE unrelated (value INTEGER)")
    service._config.write_project_focus(db)
    before = path.read_bytes()
    state = service.get_focus()
    assert state.db_path == db
    assert state.available_devices == []
    assert path.read_bytes() == before


def test_global_device_update_keeps_project_focus_unchanged(focus, monkeypatch):
    service, path, original = focus
    db = path.parent.parent / "snapshot.db"
    with closing(sqlite3.connect(db)) as conn, conn:
        conn.execute('CREATE TABLE dictionary ("table" TEXT, "column" TEXT, "key" TEXT, "value" TEXT)')
        conn.execute("CREATE TABLE trace_entry_0 (id INTEGER PRIMARY KEY)")
        conn.execute("CREATE TABLE trace_entry_1 (id INTEGER PRIMARY KEY)")
    service.set_global_focus(db, device_id=0)
    # An explicit environment focus selects the real DB while retaining the
    # unrelated project file; --global still updates only the global selection.
    monkeypatch.setenv("PT_SNAP_DB_PATH", str(db))
    state = service.set_device(1, scope="global")
    assert state.source == "global"
    assert state.device_id == 1
    assert service._config.current_device_id == 1
    assert path.read_bytes() == original
