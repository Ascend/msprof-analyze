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

"""Compatibility preflight stays per-shard and avoids a device-wide ID list."""

import sqlite3
from contextlib import closing

import pytest

from pt_snap_cli.core.dataset.dataset_contract import DatasetContractError
from pt_snap_cli.core.importing.msinsight_export import _validate_shards, convert_shards
from pt_snap_cli.core.splitting.sharded_replay_service import ShardedReplayResult
from pt_snap_cli.snapshot.tools.adaptors.sharded_replay import ReplaySlice
from test.core.test_dataset_import import hashes


def shard(
    root,
    device,
    index,
    ids,
    *,
    id_schema="id INTEGER PRIMARY KEY",
    suffix="",
    table_suffix="",
    action=7,
):
    """Construct native-layout SQL only; no replay, pickle or source session."""
    path = root / f"device_{device}" / f"slice_{index:05d}.db"
    path.parent.mkdir(parents=True, exist_ok=True)
    trace = f"trace_entry_{device}"
    with closing(sqlite3.connect(path)) as conn, conn:
        conn.execute(
            f"CREATE TABLE {trace} ({id_schema}, action INTEGER, address INTEGER, size INTEGER, "
            "stream INTEGER, allocated INTEGER, active INTEGER, reserved INTEGER, "
            f"callstackId INTEGER{suffix}) {table_suffix}"
        )
        conn.executemany(
            f"INSERT INTO {trace} VALUES (?, ?, 0, 0, ?, 0, 0, 0, 0)",
            ((value, action, position) for position, value in enumerate(ids)),
        )
        conn.execute("CREATE TABLE callstack (id INTEGER PRIMARY KEY, callstack TEXT)")
        conn.execute("INSERT INTO callstack VALUES (0, 'synthetic stack')")
        # Conversion also compacts preexisting block IDs, even in trace-only tests.
        conn.execute(f"CREATE TABLE block_{device} (id INTEGER PRIMARY KEY)")
        conn.execute('CREATE TABLE dictionary ("table" TEXT, "column" TEXT, key TEXT, value TEXT)')
    real = [value for value in ids if value is not None and value >= 0]
    return ReplaySlice(device, index, 0, len(real) - 1, min(real, default=0), max(real, default=-1), path)


def result(root, *items):
    return ShardedReplayResult(root, items, ())


def unchanged_failure(staged, error=DatasetContractError, match="event_identity"):
    before = hashes(staged.directory)
    with pytest.raises(error, match=match):
        convert_shards(staged)
    assert hashes(staged.directory) == before


@pytest.mark.parametrize(
    "ids",
    [
        ((1, 2),),  # Nonzero start.
        ((0, 2),),  # Within-shard hole.
        ((0, 1), (3, 4)),  # Cross-shard hole.
        ((0, 1), (1, 2)),  # Cross-shard overlap.
        ((2, 3), (0, 1)),  # Reversed shard order.
        ((0, 1), (3, 4), (4, 5)),  # Global COUNT/MIN/MAX hides the hole and duplicate.
        ((0, 2), (1, 3)),  # Globally continuous IDs cannot repair per-shard holes/order.
    ],
)
def test_rejects_invalid_continuity_without_converting_any_shard(tmp_path, ids):
    items = tuple(shard(tmp_path, 0, index, values) for index, values in enumerate(ids))
    unchanged_failure(result(tmp_path, *items))


@pytest.mark.parametrize("ids", [(), (-10, -1)])
def test_empty_or_boundary_only_device_still_requires_a_real_event(tmp_path, ids):
    first = shard(tmp_path, 0, 0, (0, 1))
    empty_device = shard(tmp_path, 3, 0, ids)
    unchanged_failure(result(tmp_path, first, empty_device), match="empty/static-only")


def test_boundary_and_empty_shards_do_not_advance_real_ids(tmp_path):
    items = (
        shard(tmp_path, 0, 0, (-2, -1)),
        shard(tmp_path, 0, 1, (-100, 0, 1)),
        shard(tmp_path, 0, 2, ()),
        shard(tmp_path, 0, 3, (-20, 2, 3)),
    )
    convert_shards(result(tmp_path, *items))
    for item in items:
        with closing(sqlite3.connect(item.file)) as conn:
            assert conn.execute("PRAGMA table_info(trace_entry_0)").fetchall()[-1][1] == "callstack"


def test_each_device_restarts_at_zero_even_when_shards_are_interleaved(tmp_path):
    items = (
        shard(tmp_path, 0, 0, (0, 1)),
        shard(tmp_path, 4, 0, (0,)),
        shard(tmp_path, 0, 1, (2, 3)),
        shard(tmp_path, 4, 1, (1, 2)),
    )
    convert_shards(result(tmp_path, *items))


def test_invalid_second_device_does_not_convert_first_device(tmp_path):
    items = (shard(tmp_path, 0, 0, (0, 1)), shard(tmp_path, 4, 0, (2, 3)))
    unchanged_failure(result(tmp_path, *items))


@pytest.mark.parametrize("action", [8, -1, 1.5, "unknown", None])
@pytest.mark.parametrize("boundary", [False, True])
def test_actions_are_checked_on_real_and_boundary_rows_before_conversion(tmp_path, action, boundary):
    items = (
        shard(tmp_path, 0, 0, (0, 1)),
        shard(tmp_path, 0, 1, (-1,) if boundary else (2,), action=action),
    )
    unchanged_failure(result(tmp_path, *items), ValueError, "OOM/unknown actions")


@pytest.mark.parametrize(
    ("id_schema", "suffix", "ids"),
    [
        ("id INTEGER", "", (0, 0, 2)),  # Duplicate offsets a hole in aggregate checks.
        ("id INTEGER", ", PRIMARY KEY (id, stream)", (0, 0, 2)),
        ("id INT PRIMARY KEY", "", (0, 1, 2)),
        ("id REAL PRIMARY KEY", "", (0, 1.5, 2)),
        ("id TEXT PRIMARY KEY", "", (0, 1, 2)),
        ("id INTEGER PRIMARY KEY DESC", "", (0, 1.5, 2)),
        ("id INTEGER PRIMARY KEY DESC", "", (None, 0, 1)),
    ],
)
def test_aggregate_requires_a_true_integer_primary_key(tmp_path, id_schema, suffix, ids):
    first = shard(tmp_path, 0, 0, (0, 1))
    invalid = shard(tmp_path, 4, 0, ids, id_schema=id_schema, suffix=suffix)
    unchanged_failure(result(tmp_path, first, invalid), ValueError, "INTEGER PRIMARY KEY")


@pytest.mark.parametrize("kind", ["view", "wrong-device"])
def test_rejects_non_native_trace_before_converting_prior_shards(tmp_path, kind):
    first = shard(tmp_path, 0, 0, (0, 1))
    invalid = shard(tmp_path, 4, 0, (0, 1))
    with closing(sqlite3.connect(invalid.file)) as conn, conn:
        conn.execute("ALTER TABLE trace_entry_4 RENAME TO other")
        if kind == "view":
            conn.execute("CREATE VIEW trace_entry_4 AS SELECT * FROM other")
    unchanged_failure(result(tmp_path, first, invalid), ValueError, "INTEGER PRIMARY KEY")


@pytest.mark.parametrize(
    "id_schema,suffix", [("id integer primary key", ""), ("id INTEGER", ", PRIMARY KEY (id DESC)")]
)
def test_accepts_rowid_alias_spelling_variants(tmp_path, id_schema, suffix):
    item = shard(tmp_path, 0, 0, (0, 1, 2), id_schema=id_schema, suffix=suffix)
    convert_shards(result(tmp_path, item))


def test_many_small_shards_fetch_only_one_aggregate_per_shard(tmp_path, monkeypatch):
    items = tuple(shard(tmp_path, 0, index, (-1, index)) for index in range(128))
    statements = []
    connect = sqlite3.connect

    def traced_connect(*args, **kwargs):
        conn = connect(*args, **kwargs)
        conn.set_trace_callback(statements.append)
        return conn

    monkeypatch.setattr(sqlite3, "connect", traced_connect)
    _validate_shards(result(tmp_path, *items))
    aggregates = [sql for sql in statements if "SELECT COUNT(*), MIN(id), MAX(id)" in sql]
    assert len(aggregates) == len(items)
    assert not any("ORDER BY id" in sql for sql in statements)


@pytest.mark.parametrize("without_rowid", [False, True])
def test_accepts_integer_values_with_a_non_rowid_primary_key(tmp_path, without_rowid):
    item = shard(
        tmp_path,
        0,
        0,
        (-1, 0, 1, 2),
        id_schema="id INTEGER PRIMARY KEY DESC",
        table_suffix="WITHOUT ROWID" if without_rowid else "",
    )
    convert_shards(result(tmp_path, item))


def test_without_rowid_integer_affinity_does_not_prove_integer_storage(tmp_path):
    item = shard(tmp_path, 0, 0, (0, 1.5, 2), table_suffix="WITHOUT ROWID")
    unchanged_failure(result(tmp_path, item), ValueError, "only integers")
