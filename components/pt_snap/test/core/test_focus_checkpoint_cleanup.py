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

"""Checkpoint failure cleanup closes owned descriptors before verified deletion."""

import copy
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

import pt_snap_cli.core.analysis.focus_service as focus_module
from pt_snap_cli.config import Config
from pt_snap_cli.core.analysis.focus_service import FocusService


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
def checkpoint_io(monkeypatch):
    probe = SimpleNamespace(fd=None, path=None, events=[])
    mkstemp = focus_module.tempfile.mkstemp
    close = os.close
    fstat = os.fstat
    unlink = Path.unlink
    verify = FocusService._verify_checkpoint

    def create(*args, **kwargs):
        probe.fd, name = mkstemp(*args, **kwargs)
        probe.path = Path(name)
        return probe.fd, name

    def close_checkpoint(fd):
        if fd == probe.fd:
            probe.events.append("close")
        close(fd)

    def verify_checkpoint(path, identity):
        if path == probe.path:
            probe.events.append("verify")
        verify(path, identity)

    def unlink_checkpoint(path, *args, **kwargs):
        if path == probe.path:
            # Enforce Windows' close-before-unlink requirement on every runner.
            with pytest.raises(OSError):
                fstat(probe.fd)
            assert probe.events[-1] == "verify"
            probe.events.append("unlink")
        return unlink(path, *args, **kwargs)

    monkeypatch.setattr(focus_module.tempfile, "mkstemp", create)
    monkeypatch.setattr(focus_module.os, "close", close_checkpoint)
    monkeypatch.setattr(FocusService, "_verify_checkpoint", staticmethod(verify_checkpoint))
    monkeypatch.setattr(Path, "unlink", unlink_checkpoint)
    yield probe
    if probe.fd is not None:
        try:
            fstat(probe.fd)
        except OSError:
            pass
        else:
            close(probe.fd)
            pytest.fail("checkpoint descriptor leaked")
        assert probe.events.count("close") == 1


@pytest.mark.parametrize("failure", ["zero", "short-zero", "write", "fchmod", "permissions", "fsync", "verify"])
def test_checkpoint_failure_closes_before_cleanup(focus, checkpoint_io, monkeypatch, failure):
    service, path, original = focus
    state = copy.deepcopy(service._config._config)
    error = OSError("injected checkpoint failure")
    write = os.write
    verify = FocusService._verify_checkpoint
    calls = []

    def fail(*args):
        raise error

    def partial_write(fd, content):
        calls.append(len(content))
        if failure == "short-zero" and len(calls) == 1:
            return write(fd, content[:3])
        return 0

    def fail_preparation_verify(target, identity):
        verify(target, identity)
        if "close" not in checkpoint_io.events:
            raise error

    if failure in {"zero", "short-zero"}:
        monkeypatch.setattr(focus_module.os, "write", partial_write)
    elif failure == "permissions":
        # Exercise the portable pathname fallback, including real identity checks.
        monkeypatch.delattr(focus_module.os, "fchmod", raising=False)
        monkeypatch.setattr(focus_module.os, "chmod", fail)
    elif failure == "fchmod":
        monkeypatch.setattr(focus_module.os, "fchmod", fail, raising=False)
    elif failure == "verify":
        monkeypatch.setattr(FocusService, "_verify_checkpoint", staticmethod(fail_preparation_verify))
    else:
        monkeypatch.setattr(focus_module.os, failure, fail)

    with pytest.raises(OSError) as caught:
        with service.project_focus_transaction():
            pytest.fail("checkpoint failure must prevent focus publication")

    if failure in {"zero", "short-zero"}:
        assert str(caught.value) == "Could not write focus recovery checkpoint"
        assert calls == ([len(original)] if failure == "zero" else [len(original), len(original) - 3])
    else:
        assert caught.value is error
    assert checkpoint_io.events[-3:] == ["close", "verify", "unlink"]
    assert path.read_bytes() == original
    assert service._config._config == state
    assert list(path.parent.iterdir()) == [path]


@pytest.mark.parametrize("rollback", [False, True], ids=["commit", "rollback"])
def test_short_writes_keep_successful_transaction_semantics(focus, checkpoint_io, monkeypatch, rollback):
    service, path, original = focus
    state = copy.deepcopy(service._config._config)
    write = os.write
    writes = []
    error = RuntimeError("focus mutation failed")

    def short_write(fd, content):
        writes.append(len(content))
        return write(fd, content[:3])

    def mutate():
        with service.project_focus_transaction():
            assert checkpoint_io.events[-1] == "close"
            assert checkpoint_io.path.read_bytes() == original
            path.write_bytes(b"committed focus")
            service._config._config["nested"]["value"] = "changed"
            if rollback:
                raise error

    monkeypatch.setattr(focus_module.os, "write", short_write)
    if rollback:
        with pytest.raises(RuntimeError) as caught:
            mutate()
        assert caught.value is error
        assert path.read_bytes() == original
        assert service._config._config == state
    else:
        mutate()
        assert path.read_bytes() == b"committed focus"
        assert service._config._config == {"nested": {"value": "changed"}}
        assert checkpoint_io.events[-2:] == ["verify", "unlink"]
    assert len(writes) > 1
    assert list(path.parent.iterdir()) == [path]


@pytest.mark.parametrize("cleanup_failure", ["close", "unlink", "verify"])
def test_cleanup_error_keeps_original_checkpoint_error(focus, checkpoint_io, monkeypatch, cleanup_failure):
    service, path, original = focus
    error = OSError("original checkpoint write failure")
    close = os.close
    verify = FocusService._verify_checkpoint

    def fail_write(*args):
        raise error

    def close_then_fail(fd):
        close(fd)
        raise OSError("late close error")

    def fail_unlink(target, *args, **kwargs):
        assert target == checkpoint_io.path
        with pytest.raises(OSError):
            os.fstat(checkpoint_io.fd)
        assert checkpoint_io.events[-2:] == ["close", "verify"]
        raise OSError("unlink denied")

    def fail_verify(target, identity):
        verify(target, identity)
        raise OSError("verification denied")

    monkeypatch.setattr(focus_module.os, "write", fail_write)
    if cleanup_failure == "close":
        monkeypatch.setattr(focus_module.os, "close", close_then_fail)
    elif cleanup_failure == "unlink":
        monkeypatch.setattr(Path, "unlink", fail_unlink)
    else:
        monkeypatch.setattr(FocusService, "_verify_checkpoint", staticmethod(fail_verify))

    with pytest.raises(OSError) as caught:
        with service.project_focus_transaction():
            pytest.fail("checkpoint failure must prevent focus publication")
    assert caught.value is error
    assert path.read_bytes() == original
    assert checkpoint_io.path.exists() is (cleanup_failure != "close")


def test_close_failure_after_checkpoint_write_does_not_retry_close(focus, checkpoint_io, monkeypatch):
    service, path, original = focus
    close = os.close
    error = OSError("late checkpoint close error")

    def close_then_fail(fd):
        close(fd)
        raise error

    monkeypatch.setattr(focus_module.os, "close", close_then_fail)
    with pytest.raises(OSError) as caught:
        with service.project_focus_transaction():
            pytest.fail("checkpoint close failure must prevent focus publication")
    assert caught.value is error
    assert checkpoint_io.events[-3:] == ["close", "verify", "unlink"]
    assert path.read_bytes() == original
    assert list(path.parent.iterdir()) == [path]


def test_unknown_checkpoint_identity_closes_without_unverified_deletion(focus, checkpoint_io, monkeypatch):
    service, path, original = focus
    error = OSError("checkpoint identity unavailable")
    fstat = os.fstat

    def fail_fstat(fd):
        if fd == checkpoint_io.fd:
            raise error
        return fstat(fd)

    with monkeypatch.context() as patch:
        patch.setattr(focus_module.os, "fstat", fail_fstat)
        with pytest.raises(OSError) as caught:
            with service.project_focus_transaction():
                pytest.fail("unverified checkpoint must prevent focus publication")
    assert caught.value is error
    assert checkpoint_io.events == ["close"]
    assert checkpoint_io.path.read_bytes() == b""
    assert path.read_bytes() == original


def test_replaced_checkpoint_after_close_is_not_deleted(focus, checkpoint_io, monkeypatch):
    service, path, original = focus
    close = os.close
    replacement = path.parent / "replacement"
    replacement.write_bytes(b"independent file")
    saved = path.parent / "owned-checkpoint"
    error = OSError("original checkpoint write failure")

    def fail_write(*args):
        raise error

    def close_then_replace(fd):
        close(fd)
        # Keep both real files alive, so their distinct identities cannot be reused.
        checkpoint_io.path.rename(saved)
        replacement.rename(checkpoint_io.path)

    monkeypatch.setattr(focus_module.os, "write", fail_write)
    monkeypatch.setattr(focus_module.os, "close", close_then_replace)
    with pytest.raises(OSError) as caught:
        with service.project_focus_transaction():
            pytest.fail("checkpoint failure must prevent focus publication")
    assert caught.value is error
    assert checkpoint_io.events == ["close", "verify"]
    assert checkpoint_io.path.read_bytes() == b"independent file"
    assert saved.read_bytes() == b""
    assert path.read_bytes() == original


def test_symlink_metadata_at_cleanup_is_rejected(focus, checkpoint_io, monkeypatch):
    service, path, original = focus
    is_symlink = Path.is_symlink
    error = OSError("original checkpoint write failure")

    def fail_write(*args):
        raise error

    def checkpoint_is_symlink(target):
        # Inject only the metadata observation; no Windows symlink privilege is needed.
        return target == checkpoint_io.path or is_symlink(target)

    monkeypatch.setattr(focus_module.os, "write", fail_write)
    monkeypatch.setattr(Path, "is_symlink", checkpoint_is_symlink)
    with pytest.raises(OSError) as caught:
        with service.project_focus_transaction():
            pytest.fail("checkpoint failure must prevent focus publication")
    assert caught.value is error
    assert checkpoint_io.events == ["close", "verify"]
    assert checkpoint_io.path.read_bytes() == b""
    assert path.read_bytes() == original
