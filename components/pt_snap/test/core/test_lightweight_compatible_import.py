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

"""Compatible cache reuse only checks identity, inventory and schema."""

import dataclasses
import json
import sqlite3
from contextlib import closing
from pathlib import Path

import pytest
from typer.testing import CliRunner

from pt_snap_cli.cli import app
from pt_snap_cli.core.common.errors import ImportExecutionError
from pt_snap_cli.core.dataset import dataset_resolver
from pt_snap_cli.core.importing import import_service
from pt_snap_cli.core.importing.import_service import ImportService
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
    pytest.fail("default compatible reuse must not scan or hash member contents")


@pytest.mark.parametrize("external", [False, True])
@pytest.mark.parametrize("focus", [False, True])
def test_repeat_import_skips_all_content_scans(tmp_path, monkeypatch, external, focus):
    request = options(tmp_path, focus=focus)
    monkeypatch.setattr(import_service, "save_receipt", unexpected)
    monkeypatch.setattr(dataset_resolver, "save_receipt", unexpected)
    monkeypatch.setattr(dataset_resolver, "validate_dataset", unexpected)
    first = ImportService().import_snapshot(request)
    assert not dataset_resolver._VALIDATED
    if external:
        path = first.db_path / "manifest.json"
        manifest = json.loads(path.read_bytes())
        del manifest["ptSnap"]
        path.write_text(json.dumps(manifest), encoding="utf-8")
    dataset_resolver._VALIDATED.clear()
    monkeypatch.setattr(dataset_resolver, "validate_dataset", unexpected)
    hash_file = dataset_resolver._hash_file

    def no_member_hash(path, **kwargs):
        if path.suffix == ".db" or path.name.endswith("-wal"):
            unexpected()
        return hash_file(path, **kwargs)

    monkeypatch.setattr(dataset_resolver, "_hash_file", no_member_hash)
    repeated = ImportService().import_snapshot(request)
    assert repeated.reused
    assert repeated.devices == first.devices
    assert repeated.slice_count == first.slice_count
    assert repeated.metadata == (None if external else first.metadata)
    assert not dataset_resolver._VALIDATED  # Never promote structural checks to query admission.
    if focus:
        assert repeated.focus_state.available_devices == first.focus_state.available_devices


def test_content_edits_do_not_trigger_cache_replay(tmp_path):
    request = options(tmp_path, focus=False)
    first = ImportService().import_snapshot(request)
    member = next(first.db_path.glob("device_*/*.db"))
    with closing(sqlite3.connect(member)) as conn, conn:
        conn.execute("UPDATE block_0 SET size=size+1")
    assert ImportService().import_snapshot(request).reused


@pytest.mark.parametrize("cache_mode", ["disabled", "immutable"])
def test_cache_configuration_does_not_enable_content_checks(tmp_path, monkeypatch, cache_mode):
    request = options(tmp_path, focus=True)
    ImportService().import_snapshot(request)
    monkeypatch.setenv("PT_SNAP_DATASET_CACHE", cache_mode)
    monkeypatch.setattr(dataset_resolver, "validate_dataset", unexpected)
    assert ImportService().import_snapshot(request).reused


def test_import_help_has_no_strict_cache_option():
    result = CliRunner().invoke(app, ["import", "--help"], color=False)
    assert result.exit_code == 0, result.output
    assert "--verify-cache-content" not in result.stdout


@pytest.mark.parametrize("damage", ["missing", "table", "manifest"])
def test_default_import_still_rejects_incomplete_artifacts(tmp_path, damage):
    request = options(tmp_path, focus=False)
    first = ImportService().import_snapshot(request)
    member = next(first.db_path.glob("device_*/*.db"))
    if damage == "missing":
        member.unlink()
    elif damage == "table":
        with closing(sqlite3.connect(member)) as conn, conn:
            conn.execute("DROP TABLE block_0")
    else:
        manifest_path = first.db_path / "manifest.json"
        manifest = json.loads(manifest_path.read_bytes())
        manifest["status"] = "building"
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ImportExecutionError):
        ImportService().import_snapshot(dataclasses.replace(request, force=True))
    if damage == "missing":
        assert not member.exists()
