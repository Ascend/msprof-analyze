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

"""Unsuccessful replay or exclusive publication must leave no partial result."""

import errno
import os
import pickle
from pathlib import Path
from types import SimpleNamespace

import pytest

import pt_snap_cli.core.splitting.split_service as split_module
from pt_snap_cli.core.common.errors import SplitError
from pt_snap_cli.core.common.models import SplitOptions
from pt_snap_cli.core.splitting.split_service import SplitService


@pytest.fixture
def split_input(tmp_path):
    source = tmp_path / "snapshot.pkl"
    # Test-owned input only. Fault-injected replay below owns the generated
    # output; actual allocator validity is covered by the ordinary split suite.
    source.write_bytes(pickle.dumps({"segments": [], "device_traces": [[{"id": 0}]]}))
    return SplitOptions(snapshot_file=source, output=tmp_path / "split", slices=1)


def assert_unpublished(options):
    assert not options.output.exists()
    assert not list(options.output.parent.glob(".split.pt-snap-*"))


def test_missing_device_trace_list_fails_without_staging(split_input):
    split_input.snapshot_file.write_bytes(pickle.dumps({"device_traces": {}}))
    before = split_input.snapshot_file.read_bytes()
    with pytest.raises(SplitError, match="no device trace list") as caught:
        SplitService().split(split_input)
    assert caught.value.phase == "device"
    assert split_input.snapshot_file.read_bytes() == before
    assert_unpublished(split_input)


def test_stage_creation_failure_is_normalized_without_loading_replay(split_input, monkeypatch):
    def denied(*args, **kwargs):
        raise PermissionError("staging denied")

    monkeypatch.setattr(split_module.tempfile, "mkdtemp", denied)
    monkeypatch.setattr(
        split_module,
        "replay_snapshot",
        lambda *args, **kwargs: pytest.fail("no replay before staging"),
    )
    with pytest.raises(SplitError, match="cannot create staging directory") as caught:
        SplitService().split(split_input)
    assert caught.value.phase == "publication"
    assert isinstance(caught.value.__cause__, PermissionError)
    assert_unpublished(split_input)


@pytest.mark.parametrize(
    ("failure", "phase", "message"),
    [
        ("source-replay", "load/engine", "replay engine returned false"),
        ("empty-output", "load/engine", "engine generated no slices"),
        ("bad-filename", "generated-validation", "Unexpected engine output name"),
        ("generated-replay", "generated-validation", "replay returned false"),
    ],
)
def test_replay_failures_remove_owned_stage_and_preserve_source(split_input, monkeypatch, failure, phase, message):
    before = split_input.snapshot_file.read_bytes()
    calls = []

    def replay(representation, device, **kwargs):
        calls.append("source" if "hooker" in kwargs else "generated")
        if "hooker" not in kwargs:
            return None, False
        if failure in ("bad-filename", "generated-replay"):
            stages = list(split_input.output.parent.glob(".split.pt-snap-*"))
            assert len(stages) == 1
            raw = stages[0] / ".device-0"
            name = "unexpected.pkl" if failure == "bad-filename" else "snapshot_entry_0_0.pkl"
            (raw / name).write_bytes(before)
        return None, failure != "source-replay"

    monkeypatch.setattr(split_module, "replay_snapshot", replay)
    with pytest.raises(SplitError, match=message) as caught:
        SplitService().split(split_input)
    assert caught.value.phase == phase
    assert calls == (["source", "generated"] if failure == "generated-replay" else ["source"])
    assert split_input.snapshot_file.read_bytes() == before
    assert_unpublished(split_input)


@pytest.mark.parametrize("method", ["_stage_identity", "_verify_stage_identity"])
def test_non_directory_stage_is_never_accepted_or_deleted(tmp_path, method):
    path = tmp_path / "not-a-stage"
    path.write_bytes(b"another owner's file")
    with pytest.raises(OSError, match="not an owned directory"):
        if method == "_stage_identity":
            SplitService._stage_identity(path)
        else:
            SplitService._verify_stage_identity(path, (0, 0, None))
    assert path.read_bytes() == b"another owner's file"


def test_descriptor_identity_mismatch_is_rejected_without_deleting_stage(tmp_path):
    stage = tmp_path / "stage"
    stage.mkdir()
    unrelated = tmp_path / "unrelated-file"
    unrelated.write_bytes(b"another owner's evidence")
    status = stage.lstat()
    # An actual mismatched descriptor exercises the held-identity guard on every
    # platform, including Windows where ordinary stages do not hold directory fds.
    descriptor = os.open(unrelated, os.O_RDONLY)
    identity = (status.st_dev, status.st_ino, descriptor)
    try:
        held = os.fstat(descriptor)
        assert (held.st_dev, held.st_ino) != identity[:2]
        with pytest.raises(OSError, match="identity changed"):
            SplitService._verify_stage_identity(stage, identity)
        assert stage.is_dir()
        assert unrelated.read_bytes() == b"another owner's evidence"
    finally:
        SplitService._close_stage_identity(identity)
    with pytest.raises(OSError) as closed:
        os.fstat(descriptor)
    assert closed.value.errno == errno.EBADF


def test_closed_stage_descriptor_cleanup_is_idempotent(tmp_path):
    identity = SplitService._stage_identity(tmp_path)
    SplitService._close_stage_identity(identity)
    SplitService._close_stage_identity(identity)
    assert tmp_path.is_dir()


@pytest.mark.parametrize("platform", ["darwin", "linux"])
def test_native_publication_errors_preserve_both_paths(tmp_path, monkeypatch, platform):
    stage = tmp_path / "stage"
    destination = tmp_path / "destination"
    stage.mkdir()
    destination.mkdir()
    (stage / "slice.pkl").write_bytes(b"staged")
    (destination / "owner.txt").write_bytes(b"other owner")

    class FailedRename:
        def __call__(self, *args):
            return -1

    library = SimpleNamespace(renamex_np=FailedRename(), renameat2=FailedRename())
    monkeypatch.setattr(split_module.sys, "platform", platform)
    monkeypatch.setattr(split_module.ctypes, "CDLL", lambda *args, **kwargs: library)
    monkeypatch.setattr(split_module.ctypes, "get_errno", lambda: errno.EEXIST)
    with pytest.raises(OSError) as caught:
        SplitService._publish_directory(stage, destination)
    assert caught.value.errno == errno.EEXIST
    assert Path(caught.value.filename) == destination
    assert (stage / "slice.pkl").read_bytes() == b"staged"
    assert (destination / "owner.txt").read_bytes() == b"other owner"


@pytest.mark.parametrize("platform", ["darwin", "linux", "unsupported"])
def test_unavailable_no_replace_primitive_fails_closed(tmp_path, monkeypatch, platform):
    stage, destination = tmp_path / "stage", tmp_path / "destination"
    stage.mkdir()
    monkeypatch.setattr(split_module.sys, "platform", platform)
    monkeypatch.setattr(split_module, "os", SimpleNamespace(name="posix"))
    monkeypatch.setattr(split_module.ctypes, "CDLL", lambda *args, **kwargs: object())
    with pytest.raises(OSError) as caught:
        SplitService._preflight_publication()
    assert caught.value.errno == errno.ENOTSUP
    if platform != "darwin":
        with pytest.raises(OSError) as caught:
            SplitService._publish_directory(stage, destination)
        assert caught.value.errno == errno.ENOTSUP
    assert stage.is_dir()
    assert not destination.exists()


def test_windows_publication_uses_non_replacing_rename(tmp_path, monkeypatch):
    stage, destination = tmp_path / "stage", tmp_path / "destination"
    calls = []

    def rename(source, target):
        calls.append((source, target))
        raise FileExistsError(errno.EEXIST, "destination exists", target)

    monkeypatch.setattr(split_module.sys, "platform", "win32")
    monkeypatch.setattr(split_module, "os", SimpleNamespace(name="nt", rename=rename))
    SplitService._preflight_publication()
    with pytest.raises(FileExistsError):
        SplitService._publish_directory(stage, destination)
    assert calls == [(stage, destination)]
