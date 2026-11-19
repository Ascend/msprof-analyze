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

"""Reject malformed cache contracts without repairing or publishing any artifacts."""

import copy
import errno
import json
import os
import sqlite3
from contextlib import closing
from pathlib import Path

import pytest

from pt_snap_cli.core.cache import snapshot_cache
from pt_snap_cli.core.cache.snapshot_cache import (
    parser_members,
    seal_manifest,
    source_hashes,
    validate_cache,
)


@pytest.fixture
def cache_artifact(tmp_path: Path) -> tuple[Path, dict, str]:
    source = tmp_path / "source.pkl"
    # Validation hashes but never deserializes this test-owned source.
    source.write_bytes(b"test-owned source, deliberately not a pickle")
    cache_hash = source_hashes(source)[1]
    with closing(sqlite3.connect(tmp_path / "slice.db")) as conn, conn:
        conn.executescript(
            "CREATE TABLE trace_entry_0(id INTEGER PRIMARY KEY, action INTEGER, "
            "address INTEGER, size INTEGER, stream INTEGER, allocated INTEGER, "
            "active INTEGER, reserved INTEGER, callstack TEXT);"
            "CREATE TABLE block_0(id INTEGER PRIMARY KEY, address INTEGER, size INTEGER, "
            "requestedSize INTEGER, state INTEGER, allocEventId INTEGER, freeEventId INTEGER);"
            'CREATE TABLE dictionary("table" TEXT, "column" TEXT, "key" TEXT, "value" TEXT);'
            "INSERT INTO trace_entry_0 VALUES(0,4,4096,16,0,16,16,64,'test frame');"
            "INSERT INTO block_0 VALUES(0,4096,16,16,1,0,-1);"
            "INSERT INTO dictionary VALUES('trace_entry_0','action','4','alloc');"
            "INSERT INTO dictionary VALUES('block_0','state','1','active_allocated');"
        )
    manifest = {
        "schemaVersion": 1,
        "status": "complete",
        "sourceFile": str(source),
        "cacheHash": cache_hash,
        "eventsPerSlice": 1,
        "devices": {
            "0": {
                "eventCount": 1,
                "sliceCount": 1,
                "readySlices": [0],
                "slices": [
                    {
                        "index": 0,
                        "startEventId": 0,
                        "endEventId": 0,
                        "file": "slice.db",
                        "ready": True,
                    }
                ],
            }
        },
    }
    seal_manifest(tmp_path, manifest)
    return tmp_path, manifest, cache_hash


def _tree_state(directory: Path) -> dict[str, object]:
    return {
        str(path.relative_to(directory)): (
            ("symlink", str(path.readlink()))
            if path.is_symlink()
            else ("file", path.read_bytes())
            if path.is_file()
            else ("directory",)
        )
        for path in directory.rglob("*")
    }


def _assert_rejected(artifact: tuple[Path, dict, str], message: str) -> None:
    directory, manifest, cache_hash = artifact
    (directory / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    before = _tree_state(directory)
    with pytest.raises(ValueError, match=message):
        validate_cache(directory, cache_hash)
    assert _tree_state(directory) == before


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("schemaVersion", 2, "Unsupported snapshot manifest version"),
        ("sourceFile", "", "Snapshot is incomplete"),
        ("sourceFile", 7, "Snapshot is incomplete"),
        ("eventsPerSlice", 0, "Invalid nonnegative integer"),
        ("eventsPerSlice", 2**63, "Invalid nonnegative integer"),
        ("devices", {}, "Missing snapshot devices"),
        ("devices", [], "Missing snapshot devices"),
        ("devices", {"01": {}}, "Invalid device ID"),
        ("devices", {"0": []}, "Invalid device inventory"),
        ("ptSnap", [], "Invalid snapshot extension"),
        ("ptSnap", {"identity": []}, "Invalid producer identity"),
        ("ptSnap", {"memberHashKind": "future-v2"}, "Unsupported member hash contract"),
        ("ptSnap", {"members": []}, "Invalid legacy snapshot member inventory"),
        ("ptSnap", {"members": {}}, "Invalid legacy snapshot member inventory"),
        ("parserCache", {"version": 2}, "Snapshot parser data changed"),
    ],
)
def test_invalid_manifest_contract_preserves_artifacts(cache_artifact, field, value, message):
    cache_artifact[1][field] = value
    _assert_rejected(cache_artifact, message)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("sliceCount", 2, "Incomplete snapshot slice inventory"),
        ("slices", [], "Incomplete snapshot slice inventory"),
        ("slices", [None], r"slices\[0\]: expected object"),
        ("readySlices", [0, 0], "Snapshot slices are not ready"),
        ("eventCount", True, "Invalid nonnegative integer"),
    ],
)
def test_invalid_device_inventory_preserves_artifacts(cache_artifact, field, value, message):
    cache_artifact[1]["devices"]["0"][field] = value
    _assert_rejected(cache_artifact, message)


@pytest.mark.parametrize(
    ("field", "value"),
    [("index", 1), ("startEventId", 1), ("endEventId", 1), ("ready", 1)],
)
def test_invalid_slice_range_preserves_artifacts(cache_artifact, field, value):
    cache_artifact[1]["devices"]["0"]["slices"][0][field] = value
    _assert_rejected(cache_artifact, "Invalid snapshot slice range")


def test_duplicate_member_between_devices_preserves_artifacts(cache_artifact):
    devices = cache_artifact[1]["devices"]
    devices["1"] = copy.deepcopy(devices["0"])
    _assert_rejected(cache_artifact, "Duplicate snapshot member")


@pytest.mark.parametrize(
    ("relative", "message"),
    [
        (None, "Invalid snapshot member path"),
        ("", "Invalid snapshot member path"),
        ("slice\\db", "Invalid snapshot member path"),
        ("./slice.db", "Snapshot member escapes artifact directory"),
        ("missing.db", "Missing or aliased snapshot member"),
    ],
)
def test_invalid_member_paths_preserve_artifacts(cache_artifact, relative, message):
    cache_artifact[1]["devices"]["0"]["slices"][0]["file"] = relative
    _assert_rejected(cache_artifact, message)


def test_absolute_member_path_is_rejected(cache_artifact):
    # A drive-qualified POSIX spelling is also absolute under Windows pathlib.
    absolute = (cache_artifact[0] / "outside.db").as_posix()
    cache_artifact[1]["devices"]["0"]["slices"][0]["file"] = absolute
    _assert_rejected(cache_artifact, "Snapshot member escapes artifact directory")


def test_symlink_member_is_rejected_without_touching_target(cache_artifact):
    directory, manifest, _ = cache_artifact
    (directory / "alias.db").symlink_to(directory / "slice.db")
    manifest["devices"]["0"]["slices"][0]["file"] = "alias.db"
    _assert_rejected(cache_artifact, "Missing or aliased snapshot member")


@pytest.mark.parametrize("suffix", ["-wal", "-shm", "-journal"])
def test_symlink_sidecar_is_rejected_without_touching_target(cache_artifact, suffix):
    directory = cache_artifact[0]
    target = directory / "consumer-data"
    target.write_bytes(b"must not open or recover this sidecar target")
    (directory / f"slice.db{suffix}").symlink_to(target)
    _assert_rejected(cache_artifact, "Snapshot has an aliased sidecar")


@pytest.mark.parametrize(
    ("sql", "message"),
    [
        ("DROP TABLE block_0", "Missing parser table: block_0"),
        (
            "ALTER TABLE block_0 RENAME TO stored_blocks;CREATE VIEW block_0 AS SELECT * FROM stored_blocks",
            "Missing parser table: block_0",
        ),
        (
            "ALTER TABLE trace_entry_0 RENAME COLUMN callstack TO consumer_stack",
            r"Invalid parser column: trace_entry_0\.callstack",
        ),
        (
            "DROP TABLE block_0;"
            "CREATE TABLE block_0(id INTEGER PRIMARY KEY, address INTEGER, size TEXT, "
            "requestedSize INTEGER, state INTEGER, allocEventId INTEGER, freeEventId INTEGER)",
            r"Invalid parser column: block_0\.size",
        ),
        (
            "DROP TABLE block_0;"
            "CREATE TABLE block_0(id INTEGER, address INTEGER, size INTEGER, "
            "requestedSize INTEGER, state INTEGER, allocEventId INTEGER, freeEventId INTEGER)",
            r"Missing parser primary key: block_0\.id",
        ),
        (
            "DROP TABLE block_0;"
            "CREATE TABLE block_0(id INTEGER, address INTEGER, size INTEGER, "
            "requestedSize INTEGER, state INTEGER, allocEventId INTEGER, freeEventId INTEGER, "
            "PRIMARY KEY(id, address))",
            r"Missing parser primary key: block_0\.id",
        ),
    ],
)
def test_invalid_parser_schema_is_not_repaired(cache_artifact, sql, message):
    with closing(sqlite3.connect(cache_artifact[0] / "slice.db")) as conn, conn:
        conn.executescript(sql)
    _assert_rejected(cache_artifact, message)


def test_matching_producer_and_parser_identities_validate_read_only(cache_artifact):
    directory, manifest, cache_hash = cache_artifact
    manifest["parserCache"]["requestedDevice"] = 0
    manifest["ptSnap"] = {
        "identity": {"requestedDevice": 0},
        "memberHashKind": "parser-v1",
        "members": dict(manifest["parserCache"]["members"]),
    }
    (directory / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    before = _tree_state(directory)
    assert validate_cache(directory, cache_hash, device=0) == manifest
    assert _tree_state(directory) == before


@pytest.mark.parametrize("device", ["01", "0; DROP TABLE block_0"])
def test_member_inventory_rejects_invalid_device_before_database_access(cache_artifact, device, monkeypatch):
    directory, manifest, _ = cache_artifact
    manifest["devices"][device] = manifest["devices"].pop("0")

    def unexpected_database_access(*args, **kwargs):
        pytest.fail("Invalid device IDs must be rejected before opening a database")

    monkeypatch.setattr(snapshot_cache, "validate_member_structure", unexpected_database_access)
    before = _tree_state(directory)
    with pytest.raises(ValueError, match="Invalid device ID"):
        parser_members(directory, manifest)
    assert _tree_state(directory) == before


@pytest.mark.parametrize("replace_path", [False, True])
def test_source_change_during_hashing_is_rejected_and_descriptor_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, replace_path: bool
):
    source = tmp_path / "source.pkl"
    source.write_bytes(b"original test-owned source")
    replacement = b"replacement bytes from the concurrent producer"
    original_fstat = os.fstat
    original_stat = Path.stat
    descriptors: list[int] = []

    def producer_change_at_stat(descriptor: int) -> os.stat_result:
        result = original_fstat(descriptor)
        descriptors.append(descriptor)
        if not replace_path and len(descriptors) == 1:
            # Change the open file between the before/after descriptor signatures.
            source.write_bytes(replacement)
        return result

    def producer_replace_before_path_stat(path: Path, *args, **kwargs) -> os.stat_result:
        if path == source:
            # Replace after the hashing handle closes, as required on Windows.
            # Both descriptor signatures match; only the final path check detects it.
            new_source = tmp_path / "replacement.pkl"
            new_source.write_bytes(replacement)
            new_source.replace(source)
        return original_stat(path, *args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(snapshot_cache.os, "fstat", producer_change_at_stat)
        if replace_path:
            patch.setattr(Path, "stat", producer_replace_before_path_stat)
        with pytest.raises(ValueError, match="Snapshot source changed while hashing"):
            source_hashes(source)

    assert len(descriptors) == 2
    assert descriptors[0] == descriptors[1]
    with pytest.raises(OSError) as closed:
        original_fstat(descriptors[0])
    assert closed.value.errno == errno.EBADF
    assert source.read_bytes() == replacement
    assert list(tmp_path.iterdir()) == [source]
