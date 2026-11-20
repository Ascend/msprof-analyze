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

"""Producer-only three-shard contract for msinsight #625; no GUI acceptance.

The SQL is an independent interface-facts oracle. The fixed upstream lookup's
lower-bound-only predicate is deliberately tested separately from the proposed
bounded, manifest-wide association. No upstream code is executed or copied.
"""

from __future__ import annotations

import copy
import hashlib
import json
import pickle
import sqlite3
from contextlib import closing
from pathlib import Path, PurePosixPath, PureWindowsPath

import pytest

from pt_snap_cli.core.dataset.dataset_contract import QueryScope
from pt_snap_cli.core.dataset.dataset_resolver import DatasetResolver
from test.fixtures.interop.generate_three_shard import (
    FORMATS,
    SOURCE,
    generate,
    import_source,
    write_source,
)

FIXTURE = SOURCE.parent
COMMITTED = FIXTURE / "three_shard_free_requested.pkl.msinsight"
EXPECTED_EVENTS = [
    (
        0,
        4,
        4096,
        16,
        7,
        16,
        16,
        64,
        "synthetic_entry.py:1 fixture\nsynthetic_lifecycle.py:10 alloc",
    ),
    (
        1,
        5,
        4096,
        16,
        7,
        0,
        16,
        64,
        "synthetic_entry.py:1 fixture\nsynthetic_lifecycle.py:11 free_requested",
    ),
    (
        2,
        6,
        4096,
        16,
        7,
        0,
        0,
        64,
        "synthetic_entry.py:1 fixture\nsynthetic_lifecycle.py:12 free_completed",
    ),
]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fixture_member_name(path, root):
    """Checksum manifests use forward slashes on every host OS."""
    return path.relative_to(root).as_posix()


def verify_fixture():
    """Check every shipped input/member before any SQLite open, never unpickle."""
    manifest = json.loads((FIXTURE / "checksums.json").read_text())
    expected = {SOURCE.name, "generate_three_shard.py"} | {
        fixture_member_name(path, FIXTURE) for path in COMMITTED.rglob("*") if path.is_file()
    }
    assert set(manifest) == expected
    assert not list(FIXTURE.rglob("*.pkl"))
    assert not list(FIXTURE.rglob("*.pickle"))
    for name, accepted in manifest.items():
        path = FIXTURE / name
        assert not path.is_symlink()
        assert path.stat().st_size == accepted["bytes"], name
        assert digest(path) == accepted["sha256"], name


@pytest.fixture(autouse=True)
def check_committed_fixture():
    verify_fixture()


@pytest.fixture(params=FORMATS)
def imported(tmp_path, request):
    data = json.loads(SOURCE.read_text())
    source = write_source(tmp_path, data)
    result = import_source(source, request.param, tmp_path)
    assert result["ok"] and result["slice_count"] == 3
    assert result["focus_state"] is None and not (tmp_path / ".pt-snap").exists()
    assert not (tmp_path / ".config").exists()
    return Path(result["db_path"]), request.param, source


def rows(path, sql, params=()):
    with closing(sqlite3.connect(path.as_uri() + "?mode=ro&immutable=1", uri=True)) as conn:
        return conn.execute(sql, params).fetchall()


def events(path, fmt, predicate="t.id>=0", params=()):
    stack = "t.callstack" if fmt == "msinsight" else "c.callstack"
    join = "" if fmt == "msinsight" else " JOIN callstack c ON c.id=t.callstackId"
    return rows(
        path,
        "SELECT t.id,t.action,t.address,t.size,t.stream,t.allocated,t.active,t.reserved,"
        f"{stack} FROM trace_entry_0 t{join} WHERE {predicate} ORDER BY t.id",
        params,
    )


def find_requested(dataset, fmt, *, address, alloc_id, free_id):
    """A lifecycle interval selects candidate shards, then exact bounded rows."""
    device = dataset.device(0)
    last = device.slices[-1].end_event_id
    end = free_id - 1 if free_id >= 0 else last
    if alloc_id + 1 > end:
        return (), []
    candidates = dataset.paths(QueryScope("event_range", 0, start_event_id=alloc_id + 1, end_event_id=end))
    found = [
        (path.name, event)
        for path in candidates
        for event in events(
            path,
            fmt,
            "t.action=5 AND t.address=? AND t.id>? AND t.id<=?",
            (address, alloc_id, end),
        )
    ]
    return candidates, found


def assert_three_shards(root, fmt):
    dataset = DatasetResolver().inspect(root / "manifest.json")
    assert dataset is not None and dataset.validation.real_event_count == 3
    device = dataset.device(0)
    assert len(device.slices) == 3 and device.ready_slices == (0, 1, 2)
    assert [(s.start_event_id, s.end_event_id) for s in device.slices] == [(0, 0), (1, 1), (2, 2)]
    observed = []
    hits = []
    for index, shard in enumerate(device.slices):
        path = root / shard.file
        real = events(path, fmt)
        assert real == [EXPECTED_EVENTS[index]]  # All nine physical fields and stack text.
        observed.extend(real)
        assert rows(path, "SELECT allocEventId,freeEventId FROM block_0 WHERE id=0") == [(0, 2)]
        assert rows(
            path,
            "SELECT stream,allocCallstack,freeCallstack FROM pt_snap_block_reference WHERE blockId=0",
        ) == [(7, EXPECTED_EVENTS[0][-1], EXPECTED_EVENTS[2][-1])]
        # This reproduces the fixed consumer's current-shard, lower-bound-only
        # lookup fact. Alloc and completed-free shards cannot find event 1.
        hits.append(events(path, fmt, "t.action=5 AND t.address=? AND t.id>?", (4096, 0)))
    assert observed == EXPECTED_EVENTS
    assert hits == [[], [EXPECTED_EVENTS[1]], []]
    candidates, found = find_requested(dataset, fmt, address=4096, alloc_id=0, free_id=2)
    assert [p.name for p in candidates] == ["slice_00001.db"]
    assert found == [("slice_00001.db", EXPECTED_EVENTS[1])]


def test_true_cli_import_keeps_one_event_per_owner_and_discovers_requested(imported):
    root, fmt, source = imported
    before = {p: digest(p) for p in root.rglob("*") if p.is_file()}
    assert_three_shards(root, fmt)
    manifest = json.loads((root / "manifest.json").read_text())
    if fmt == "msinsight":
        assert manifest["cacheHash"] == hashlib.sha256(b"mem_snapshot_parser_v3" + source.read_bytes()).hexdigest()
    assert {p: digest(p) for p in before} == before


def test_shipped_v1_fixture_matches_explicit_physical_oracle_without_mutation():
    before = {p: digest(p) for p in COMMITTED.rglob("*") if p.is_file()}
    assert_three_shards(COMMITTED, "msinsight")
    assert {p: digest(p) for p in before} == before


@pytest.mark.parametrize("fmt", FORMATS)
def test_reused_address_does_not_associate_later_lifetime(tmp_path, fmt):
    data = json.loads(SOURCE.read_text())
    second = copy.deepcopy(data["device_traces"][0])
    for event in second:
        event["size"] = 24
        event["frames"][0]["name"] = "reused_" + event["action"]
    data["device_traces"][0].extend(second)
    root = Path(import_source(write_source(tmp_path, data), fmt, tmp_path)["db_path"])
    dataset = DatasetResolver().inspect(root)
    assert dataset is not None and dataset.validation.real_event_count == 6
    for alloc_id, requested_id, free_id, size in [(0, 1, 2, 16), (3, 4, 5, 24)]:
        block_rows = {
            row
            for shard in dataset.device(0).slices
            for row in rows(
                root / shard.file,
                "SELECT address,allocEventId,freeEventId,size FROM block_0 WHERE id=?",
                (alloc_id,),
            )
        }
        assert block_rows == {(4096, alloc_id, free_id, size)}
        candidates, found = find_requested(dataset, fmt, address=4096, alloc_id=alloc_id, free_id=free_id)
        assert [p.name for p in candidates] == [f"slice_{requested_id:05d}.db"]
        assert len(found) == 1 and found[0][1][0] == requested_id and found[0][1][3] == size
    # Removing the completed-free upper bound would find BOTH lifetimes.
    unbounded = [
        row[0]
        for shard in dataset.device(0).slices
        for row in events(root / shard.file, fmt, "t.action=5 AND t.address=4096 AND t.id>0")
    ]
    assert unbounded == [1, 4]


@pytest.mark.parametrize("fmt", FORMATS)
@pytest.mark.parametrize("pending", [True, False])
def test_open_ended_lifetime_search_includes_device_last_event(tmp_path, fmt, pending):
    data = json.loads(SOURCE.read_text())
    data["device_traces"][0].pop()  # No completed-free event exists.
    if not pending:
        data["device_traces"][0].pop()  # Still allocated; no requested-free exists either.
    segment = data["segments"][0]
    segment["active_size"] = 16
    segment["allocated_size"] = 0 if pending else 16
    segment["blocks"] = [
        {
            "address": 4096,
            "size": 16,
            "requested_size": 16,
            "state": "active_pending_free" if pending else "active_allocated",
            "frames": [],
        },
        {"address": 4112, "size": 48, "requested_size": 0, "state": "inactive", "frames": []},
    ]
    root = Path(import_source(write_source(tmp_path, data), fmt, tmp_path)["db_path"])
    dataset = DatasetResolver().inspect(root)
    assert dataset is not None and dataset.device(0).event_count == (2 if pending else 1)
    for shard in dataset.device(0).slices:
        assert rows(root / shard.file, "SELECT allocEventId,freeEventId FROM block_0 WHERE id=0") == [(0, -1)]
    candidates, found = find_requested(dataset, fmt, address=4096, alloc_id=0, free_id=-1)
    assert [p.name for p in candidates] == (["slice_00001.db"] if pending else [])
    assert found == ([("slice_00001.db", EXPECTED_EVENTS[1])] if pending else [])


def test_generator_reproduces_semantics_and_preserves_existing_destination(tmp_path):
    output = tmp_path / "new"
    result = generate(output)
    source = Path(result["source"])
    assert source.is_file()
    # This only inspects locally serialized primitive opcodes, never executes pickle.
    import pickletools

    assert not {op.name for op, _, _ in pickletools.genops(source.read_bytes())} & {
        "GLOBAL",
        "STACK_GLOBAL",
        "REDUCE",
        "BUILD",
        "INST",
        "OBJ",
        "NEWOBJ",
        "NEWOBJ_EX",
        "PERSID",
        "BINPERSID",
        "EXT1",
        "EXT2",
        "EXT4",
    }
    assert source.read_bytes() == pickle.dumps(json.loads(SOURCE.read_text()), protocol=4)
    for fmt, exported in result["exports"].items():
        assert_three_shards(Path(exported["db_path"]), fmt)
    before = {p: digest(p) for p in output.rglob("*") if p.is_file()}
    with pytest.raises(FileExistsError):
        generate(output)
    assert {p: digest(p) for p in before} == before


@pytest.mark.parametrize("path_class", [PurePosixPath, PureWindowsPath])
def test_fixture_member_names_are_portable(path_class):
    root = path_class("fixture")
    path = root / "three_shard_free_requested.pkl.msinsight" / "device_0" / "slice_00000.db"
    assert fixture_member_name(path, root) == ("three_shard_free_requested.pkl.msinsight/device_0/slice_00000.db")
