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

"""Synthetic P0 contract tests; no executable snapshot fixtures or upstream code."""

import json
import sqlite3
from contextlib import closing
from copy import deepcopy

import pytest

from pt_snap_cli.context import Context
from pt_snap_cli.core.dataset.dataset_contract import (
    ACTION_NAMES,
    BLOCK_STATES,
    DatasetContractError,
    QueryScope,
    parse_manifest,
    validate_dataset,
    validate_event_ids,
)


def manifest_data():
    return {
        "schemaVersion": 1,
        "status": "complete",
        "sourceFile": "/capture/snapshot.pkl",
        "cacheHash": "producer-specific-opaque-identity",
        "eventsPerSlice": 2,
        "devices": {
            "0": {
                "eventCount": 4,
                "sliceCount": 2,
                "readySlices": [0, 1],
                "slices": [
                    {
                        "index": 0,
                        "startEventId": 0,
                        "endEventId": 1,
                        "file": "device_0/slice_00000.db",
                        "ready": True,
                    },
                    {
                        "index": 1,
                        "startEventId": 2,
                        "endEventId": 3,
                        "file": "device_0/slice_00001.db",
                        "ready": True,
                    },
                ],
            }
        },
    }


def make_dataset(root):
    root.mkdir()
    data = manifest_data()
    (root / "manifest.json").write_text(json.dumps(data), encoding="utf-8")
    (root / "device_0").mkdir()
    for index in range(2):
        path = root / f"device_0/slice_{index:05d}.db"
        with closing(sqlite3.connect(path)) as conn, conn:
            # Independent fixed DDL catches changes to the validator's constants.
            conn.executescript(
                'CREATE TABLE dictionary ("table" TEXT, "column" TEXT, "key" TEXT, "value" TEXT);'
                "CREATE TABLE trace_entry_0 (id INTEGER PRIMARY KEY, action INTEGER, "
                "address INTEGER, size INTEGER, stream INTEGER, allocated INTEGER, "
                "active INTEGER, reserved INTEGER, callstack TEXT);"
                "CREATE TABLE block_0 (id INTEGER PRIMARY KEY, address INTEGER, size INTEGER, "
                "requestedSize INTEGER, state INTEGER, allocEventId INTEGER, freeEventId INTEGER);"
            )
            conn.executemany(
                "INSERT INTO dictionary VALUES (?, ?, ?, ?)",
                [("trace_entry_0", "action", str(key), value) for key, value in enumerate(ACTION_NAMES)]
                + [("block_0", "state", str(key), value) for key, value in BLOCK_STATES],
            )
            for event_id in range(index * 2, index * 2 + 2):
                conn.execute(
                    "INSERT INTO trace_entry_0 VALUES (?,4,100,8,0,8,8,16,'file.py:1 fn')",
                    (event_id,),
                )
            # Artificial boundary metrics exceed the real peak; they are not real events.
            conn.execute("INSERT INTO trace_entry_0 VALUES (-1,2,100,16,0,999,999,999,'boundary')")
            conn.executemany(
                "INSERT INTO block_0 VALUES (?,?,?,?,?,?,?)",
                [
                    (0, 100, 8, 8, 1, 0, -1),
                    (-1, 200, 8, 4, 1, -1, -1),  # Static/preexisting, unknown lifetime.
                ],
            )
    return root


def mutate_db(root, sql):
    with closing(sqlite3.connect(root / "device_0/slice_00001.db")) as conn, conn:
        conn.executescript(sql)


def test_valid_external_dataset_boundary_and_unknown_extensions(tmp_path):
    root = make_dataset(tmp_path / "snapshot.pkl.msinsight")
    data = manifest_data()
    data["extensions"] = {"future.vendor": {"version": 999, "frames": "claimed"}}
    (root / "manifest.json").write_text(json.dumps(data), encoding="utf-8")
    mutate_db(
        root,
        "CREATE TABLE pt_snap_future (opaque TEXT); INSERT INTO pt_snap_future VALUES ('ignored');",
    )
    before = {p: p.read_bytes() for p in root.rglob("*") if p.is_file()}
    result = validate_dataset(root)
    assert result.real_event_count == 4
    assert result.boundary_event_count == 2
    assert result.text_callstacks is True
    assert result.structured_frames is False
    assert result.query_execution is False
    assert before == {p: p.read_bytes() for p in before}
    assert not list(root.rglob("*-journal"))
    context = Context(root / "device_0/slice_00000.db")
    try:
        assert context.callstack_layout == "v1"
    finally:
        context.close()


def test_address_reuse_is_not_identity_and_state_is_slice_local(tmp_path):
    root = make_dataset(tmp_path / "dataset")
    mutate_db(
        root,
        "INSERT INTO block_0 VALUES (2,100,8,8,1,2,-1); "
        "INSERT INTO block_0 VALUES (-2,200,8,4,1,-1,-1); "
        "UPDATE block_0 SET state=0 WHERE id=0;",
    )
    assert validate_dataset(root).real_event_count == 4


@pytest.mark.parametrize("ids", [[1, 2], [0, 2], [0, 0], [0, -1], [], [True], [0, 1.0]])
def test_producer_rejects_nonzero_sparse_empty_or_invalid_real_ids(ids):
    with pytest.raises(DatasetContractError):
        validate_event_ids(ids)


def test_real_ids_use_actual_positions_not_maximum():
    assert validate_event_ids(iter([0, 1, 2])) == 3


@pytest.mark.parametrize(
    "field,value,code",
    [
        ("schemaVersion", 2, "version"),
        ("schemaVersion", True, "type"),
        ("schemaVersion", 2**31, "range"),
        ("eventsPerSlice", 0, "range"),
        ("eventsPerSlice", 2**63, "range"),
        ("eventsPerSlice", 2.0, "type"),
        ("sourceFile", "", "range"),
        ("cacheHash", None, "type"),
        ("status", "failed", "status"),
        ("devices", {}, "empty"),
        ("devices", [], "type"),
    ],
)
def test_manifest_top_level_errors(field, value, code):
    data = manifest_data()
    data[field] = value
    with pytest.raises(DatasetContractError) as exc:
        parse_manifest(data)
    assert exc.value.code == code
    assert exc.value.location == field


@pytest.mark.parametrize(
    "field,value",
    [
        ("eventCount", 0),
        ("eventCount", 5),
        ("eventCount", True),
        ("sliceCount", 1),
        ("sliceCount", 0),
        ("readySlices", [0, 0]),
        ("readySlices", [0]),
        ("readySlices", [0, 2]),
        ("readySlices", [True, 1]),
    ],
)
def test_device_counts_readiness_and_empty_device_rejected(field, value):
    data = manifest_data()
    data["devices"]["0"][field] = value
    with pytest.raises(DatasetContractError, match="devices.0"):
        parse_manifest(data)


@pytest.mark.parametrize("device", ["01", "-1", "device_0", "1/../0", str(2**31)])
def test_invalid_device_identity(device):
    data = manifest_data()
    data["devices"][device] = data["devices"].pop("0")
    with pytest.raises(DatasetContractError):
        parse_manifest(data)


@pytest.mark.parametrize(
    "field,value",
    [
        ("startEventId", 1),
        ("startEventId", 3),
        ("endEventId", 4),
        ("endEventId", 1),
        ("index", 0),
        ("index", True),
        ("ready", "true"),
        ("file", "../other.db"),
        ("file", "/other.db"),
        ("file", "C:\\other.db"),
        ("file", "device_1/slice_00001.db"),
        ("file", "device_0/slice_00000.db"),
        ("file", "device_0/./slice_00001.db"),
        ("file", "device_0/slice_00001.db\0"),
    ],
)
def test_slice_overlap_gaps_capacity_paths_and_types(field, value):
    data = manifest_data()
    data["devices"]["0"]["slices"][1][field] = value
    with pytest.raises(DatasetContractError, match=r"devices.0.slices\[1\]"):
        parse_manifest(data)


def test_building_inspection_is_distinct_from_complete_analysis():
    data = manifest_data()
    data["status"] = "building"
    data["devices"]["0"]["readySlices"] = [1]
    data["devices"]["0"]["slices"][0]["ready"] = False
    inspection = parse_manifest(data, require_complete=False)
    with pytest.raises(DatasetContractError, match="building"):
        inspection.require_complete()
    with pytest.raises(DatasetContractError, match="building"):
        parse_manifest(data)
    data["status"] = "complete"
    with pytest.raises(DatasetContractError, match="not_ready"):
        parse_manifest(data, require_complete=False)


def test_opaque_empty_hash_is_not_a_verified_content_digest():
    data = manifest_data()
    data["cacheHash"] = ""
    assert parse_manifest(data).cache_hash == ""


def test_multiple_devices_and_short_slices_are_legal():
    data = manifest_data()
    data["devices"]["7"] = deepcopy(data["devices"]["0"])
    for index, item in enumerate(data["devices"]["7"]["slices"]):
        item["file"] = f"device_7/slice_{index:05d}.db"
    data["eventsPerSlice"] = 3
    assert len(parse_manifest(data).devices) == 2


@pytest.mark.parametrize(
    "sql,code",
    [
        ("DELETE FROM trace_entry_0 WHERE id=2;", "event_identity"),
        ("UPDATE trace_entry_0 SET id=4 WHERE id=3;", "event_identity"),
        ("UPDATE trace_entry_0 SET action=8 WHERE id=2;", "event_action"),
        ("UPDATE trace_entry_0 SET action=4 WHERE id=-1;", "event_action"),
        ("UPDATE trace_entry_0 SET action=NULL WHERE id=2;", "event_action"),
        ("UPDATE trace_entry_0 SET active='bad' WHERE id=2;", "event_values"),
        ("UPDATE trace_entry_0 SET reserved=-1 WHERE id=2;", "event_values"),
        ("UPDATE trace_entry_0 SET callstack=x'00' WHERE id=2;", "event_values"),
        ("CREATE TABLE CALLSTACK (id INTEGER, callstack TEXT);", "layout"),
        ("CREATE TABLE TRACE_ENTRY_1 (id INTEGER);", "device_tables"),
        (
            "ALTER TABLE block_0 RENAME TO saved; "
            "CREATE TABLE block_0 (id INTEGER, address INTEGER, size INTEGER, "
            "requestedSize INTEGER, state INTEGER, allocEventId INTEGER, freeEventId INTEGER, "
            "PRIMARY KEY (id,address)); INSERT INTO block_0 SELECT * FROM saved;",
            "primary_key",
        ),
        ("UPDATE dictionary SET \"value\"='wrong' WHERE \"column\"='state';", "dictionary"),
        ("CREATE TABLE trace_entry_1 (id INTEGER);", "device_tables"),
        ("ALTER TABLE block_0 RENAME TO block_1;", "device_tables"),
        ("CREATE TABLE callstack (id INTEGER, callstack TEXT);", "layout"),
        ("ALTER TABLE trace_entry_0 RENAME COLUMN callstack TO callstackId;", "columns"),
        (
            "ALTER TABLE trace_entry_0 RENAME TO saved; CREATE VIEW trace_entry_0 AS SELECT * FROM saved;",
            "table",
        ),
        ("UPDATE block_0 SET id=7 WHERE id=0;", "block_identity"),
        ("UPDATE block_0 SET allocEventId=-2 WHERE id=-1;", "block_identity"),
        ("UPDATE block_0 SET freeEventId=-2 WHERE id=0;", "lifecycle"),
        ("INSERT INTO block_0 VALUES (2,300,8,8,1,2,1);", "lifecycle"),
        ("UPDATE block_0 SET address=300 WHERE id=0;", "block_identity"),
        ("UPDATE block_0 SET freeEventId=3 WHERE id=0;", "block_identity"),
        ("UPDATE block_0 SET requestedSize=9 WHERE id=0;", "block"),
        ("UPDATE block_0 SET state=99 WHERE id=0;", "block"),
    ],
)
def test_invalid_sqlite_artifacts_are_locatable(tmp_path, sql, code):
    root = make_dataset(tmp_path / "dataset")
    mutate_db(root, sql)
    with pytest.raises(DatasetContractError) as exc:
        validate_dataset(root)
    assert exc.value.code == code
    assert exc.value.location.startswith("device_0/slice_00001.db")


def test_missing_slice_does_not_create_database(tmp_path):
    root = make_dataset(tmp_path / "dataset")
    path = root / "device_0/slice_00001.db"
    path.unlink()
    with pytest.raises(DatasetContractError, match="missing"):
        validate_dataset(root)
    assert not path.exists()


def test_compatibility_appended_columns_do_not_relax_native_schema(tmp_path):
    from pt_snap_cli.core.dataset.dataset_contract import TRACE_COLUMNS, _schema

    root = make_dataset(tmp_path / "dataset")
    mutate_db(root, "ALTER TABLE trace_entry_0 ADD COLUMN consumer_note TEXT")
    assert validate_dataset(root).real_event_count == 4
    with closing(sqlite3.connect(root / "device_0/slice_00001.db")) as conn:
        with pytest.raises(DatasetContractError, match="columns"):
            _schema(conn, "trace_entry_0", TRACE_COLUMNS, "native-member")


def test_unsealed_index_corruption_is_rejected_before_query(tmp_path):
    from pt_snap_cli.core.common.errors import DatabaseSchemaError
    from pt_snap_cli.core.dataset.dataset_resolver import DatasetResolver

    root = make_dataset(tmp_path / "dataset")
    member = root / "device_0/slice_00001.db"
    with closing(sqlite3.connect(member)) as conn:
        conn.execute("CREATE INDEX consumer_index ON block_0(address)")
        page_size = conn.execute("PRAGMA page_size").fetchone()[0]
        page = conn.execute("SELECT rootpage FROM sqlite_master WHERE name='consumer_index'").fetchone()[0]
    with member.open("r+b") as source:
        source.seek((page - 1) * page_size)
        source.write(b"\xff" * page_size)
    with pytest.raises(DatasetContractError, match="integrity|sqlite"):
        validate_dataset(root)
    with pytest.raises(DatabaseSchemaError, match="integrity|sqlite"):
        DatasetResolver().inspect(root)


@pytest.mark.parametrize("resolver", [False, True])
def test_deep_manifest_uses_domain_diagnostic(tmp_path, resolver):
    from pt_snap_cli.core.common.errors import DatabaseSchemaError
    from pt_snap_cli.core.dataset.dataset_resolver import DatasetResolver

    root = make_dataset(tmp_path / "dataset")
    (root / "manifest.json").write_text("[" * 200000 + "0" + "]" * 200000)
    with pytest.raises(
        DatabaseSchemaError if resolver else DatasetContractError,
        match="manifest nesting is too deep",
    ):
        DatasetResolver().inspect(root) if resolver else validate_dataset(root)


def test_symlink_artifact_member_rejected(tmp_path):
    root = make_dataset(tmp_path / "dataset")
    path = root / "device_0/slice_00001.db"
    path.unlink()
    path.symlink_to(root / "device_0/slice_00000.db")
    with pytest.raises(DatasetContractError, match="symlink"):
        validate_dataset(root)


def test_invalid_json_duplicate_members_and_sqlite_fail_closed(tmp_path):
    root = make_dataset(tmp_path / "dataset")
    path = root / "manifest.json"
    original = path.read_text(encoding="utf-8")
    for content in (
        "{",
        original.replace('"schemaVersion": 1', '"schemaVersion": 1, "schemaVersion": 1'),
    ):
        path.write_text(content, encoding="utf-8")
        with pytest.raises(DatasetContractError):
            validate_dataset(root)
    path.write_text(original, encoding="utf-8")
    (root / "device_0/slice_00001.db").write_bytes(b"not a database")
    with pytest.raises(DatasetContractError, match="sqlite"):
        validate_dataset(root)


@pytest.mark.parametrize(
    "scope",
    [
        QueryScope("dataset"),
        QueryScope("device", 0),
        QueryScope("slice", 0, 1),
        QueryScope("event_range", 0, None, 1, 3),
    ],
)
def test_scope_contract_not_execution(scope):
    scope.validate(parse_manifest(manifest_data()))


@pytest.mark.parametrize(
    "scope",
    [
        QueryScope("dataset", 0),
        QueryScope("device", 1),
        QueryScope("device", 0, 1),
        QueryScope("slice", 0, 2),
        QueryScope("event_range", 0, None, -1, 3),
        QueryScope("event_range", 0, None, 3, 1),
        QueryScope("event_range", 0, None, 0, 4),
    ],
)
def test_invalid_scope(scope):
    with pytest.raises(DatasetContractError):
        scope.validate(parse_manifest(manifest_data()))


def test_pinned_msinsight_enum_facts():
    # Fixed-revision snapshot_db.py, not native v2's additional oom=8 enum.
    assert ACTION_NAMES == (
        "segment_map",
        "segment_unmap",
        "segment_alloc",
        "segment_free",
        "alloc",
        "free_requested",
        "free_completed",
        "workspace_snapshot",
    )
    assert BLOCK_STATES == ((-1, "inactive"), (0, "active_pending_free"), (1, "active_allocated"))


def test_missing_manifest_and_symlink_directory_fail_closed(tmp_path):
    with pytest.raises(DatasetContractError, match="missing"):
        validate_dataset(tmp_path / "absent")
    root = make_dataset(tmp_path / "dataset")
    alias = tmp_path / "alias"
    alias.symlink_to(root, target_is_directory=True)
    with pytest.raises(DatasetContractError, match="path"):
        validate_dataset(alias)


@pytest.mark.parametrize("value", [None, [], "manifest"])
def test_invalid_manifest_object(value):
    with pytest.raises(DatasetContractError, match="type"):
        parse_manifest(value)
