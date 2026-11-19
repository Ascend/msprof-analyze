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

import pickle
import sqlite3
from contextlib import closing
from pathlib import Path

import pytest

from pt_snap_cli.snapshot.tools.adaptors import snapshot2db
from pt_snap_cli.snapshot.tools.adaptors.database import (
    BLOCK_STATE_VALUE_MAP as RUNTIME_BLOCK_STATE_VALUE_MAP,
)
from pt_snap_cli.snapshot.tools.adaptors.database import (
    TRACE_ENTRY_ACTION_VALUE_MAP as RUNTIME_ACTION_VALUE_MAP,
)
from pt_snap_cli.snapshot.tools.adaptors.database import entity2record
from pt_snap_cli.snapshot.util.logger import restore_logs, suppress_logs

from .golden_observations import (
    ACTION_VALUE_MAP,
    BLOCK_SCHEMA,
    BLOCK_STATE_VALUE_MAP,
    CALLSTACK_SCHEMA,
    DATABASE_GOLDEN,
    TRACE_SCHEMA,
)
from .helpers import FIXTURE_DIR


@pytest.fixture(scope="module")
def dump_database(tmp_path_factory):
    output_dir = tmp_path_factory.mktemp("snapshot-runtime-db")
    cache = {}

    def dump(fixture_name, device=None):
        key = (fixture_name, device)
        if key not in cache:
            suffix = "all" if device is None else str(device)
            output = output_dir / f"{fixture_name}.{suffix}.db"
            suppress_logs()
            try:
                result = snapshot2db.dump(FIXTURE_DIR / fixture_name, output, device)
            finally:
                restore_logs()
            cache[key] = (result, output)
        return cache[key]

    return dump


def test_snapshot2db(dump_database):
    result, database = dump_database("snapshot_with_empty_cache.pkl", 0)

    assert result is True
    assert database.exists()
    with closing(sqlite3.connect(database)) as connection, connection:
        assert connection.execute("SELECT COUNT(*) FROM trace_entry_0").fetchone()[0] == 8189
        assert connection.execute("SELECT COUNT(*) FROM block_0").fetchone()[0] == 3219


def test_snapshot2db_uses_shared_load_and_replay_entrypoints(monkeypatch, tmp_path):
    database = tmp_path / "shared-entrypoints.db"
    original_load = snapshot2db.load_snapshot_representation
    original_replay = snapshot2db.replay_snapshot
    calls = {"load": 0, "replay": 0, "raw_frames": False}

    def load(snapshot_file):
        calls["load"] += 1
        return original_load(snapshot_file)

    def replay(representation, device, **kwargs):
        calls["replay"] += 1
        calls["raw_frames"] = kwargs.get("_raw_frames", False)
        return original_replay(representation, device, **kwargs)

    monkeypatch.setattr(snapshot2db, "load_snapshot_representation", load)
    monkeypatch.setattr(snapshot2db, "replay_snapshot", replay)

    assert snapshot2db.dump(FIXTURE_DIR / "snapshot_with_empty_cache.pkl", database, 0)
    assert calls == {"load": 1, "replay": 1, "raw_frames": True}


def test_dump_persists_original_frame_fields_and_positions(tmp_path):
    frames = [
        {"filename": "训练:模型.py", "line": 17, "name": "内部\n分配"},
        {"filename": "outer.py", "line": 20, "name": "outer"},
    ]
    representation = {
        "segments": [],
        "device_traces": [
            [
                {
                    "id": 17,
                    "action": "segment_free",
                    "addr": 0x1000,
                    "size": 64,
                    "stream": 0,
                    "frames": frames,
                }
            ]
        ],
    }
    snapshot = tmp_path / "structured.pkl"
    database = tmp_path / "structured.db"
    with snapshot.open("wb") as stream:
        pickle.dump(representation, stream)
    assert snapshot2db.dump(snapshot, database)
    with closing(sqlite3.connect(database)) as conn:
        rows = conn.execute(
            "SELECT f.filename, f.line, f.name FROM trace_entry_0 t "
            "JOIN callstack_frame cf ON cf.callstackId=t.callstackId "
            "JOIN frame f ON f.id=cf.frameId WHERE t.id=17 ORDER BY cf.position"
        ).fetchall()
        assert [dict(zip(("filename", "line", "name"), row, strict=True)) for row in rows] == frames
        assert conn.execute(
            "SELECT m.frameCount FROM trace_entry_0 t "
            "JOIN callstack_frame_manifest m ON m.callstackId=t.callstackId WHERE t.id=17"
        ).fetchone() == (2,)


def test_fast_frame_import_matches_eager_database_exactly(monkeypatch, tmp_path):
    representation = {
        "segments": [],
        "device_traces": [
            [
                {
                    "action": "segment_free",
                    "addr": 0x1000,
                    "size": 64,
                    "stream": 3,
                    "id": 17,
                    "frames": [
                        {"filename": "inner.py", "line": 10, "name": "inner"},
                        {"filename": "outer.py", "line": 20, "name": "outer"},
                    ],
                },
                {
                    "action": "segment_free",
                    "addr": 0x2000,
                    "size": 32,
                    "stream": 3,
                    "frames": [],
                },
            ]
        ],
    }
    snapshot = tmp_path / "frames.pkl"
    with snapshot.open("wb") as stream:
        pickle.dump(representation, stream)

    original_replay = snapshot2db.replay_snapshot

    def dump_rows(database, *, eager):
        entity2record.next_default_event_id = entity2record.make_default_id_counter()
        entity2record.next_default_block_id = entity2record.make_default_id_counter()
        if eager:
            monkeypatch.setattr(
                snapshot2db,
                "replay_snapshot",
                lambda data, device, **kwargs: original_replay(
                    data,
                    device,
                    hooker=kwargs["hooker"],
                    allocator_hooker=kwargs["allocator_hooker"],
                ),
            )
        else:
            monkeypatch.setattr(snapshot2db, "replay_snapshot", original_replay)
        assert snapshot2db.dump(snapshot, database, 0)
        with closing(sqlite3.connect(database)) as connection, connection:
            return connection.execute(
                "SELECT t.id, t.action, t.address, t.size, t.stream, "
                "t.allocated, t.active, t.reserved, c.callstack "
                "FROM trace_entry_0 t JOIN callstack c ON c.id = t.callstackId "
                "ORDER BY t.id"
            ).fetchall()

    eager_rows = dump_rows(tmp_path / "eager.db", eager=True)
    fast_rows = dump_rows(tmp_path / "fast.db", eager=False)

    assert fast_rows == eager_rows
    explicit = next(row for row in fast_rows if row[0] == 17)
    assert explicit[1:5] == (3, 0x1000, 64, 3)
    assert explicit[-1] == "outer.py:20 outer\ninner.py:10 inner"
    assert any(row[0] == 1 and row[2] == 0x2000 for row in fast_rows)
    assert sum(row[-1] == "" for row in fast_rows) == 2
    synthetic = [row for row in fast_rows if row[0] < 0]
    assert len(synthetic) == 2
    assert any(row[-1] == "outer.py:20 outer\ninner.py:10 inner" for row in synthetic)


def test_fast_frame_import_rejects_malformed_frames_before_replay(monkeypatch, tmp_path):
    representation = {
        "segments": [],
        "device_traces": [
            [
                {
                    "action": "segment_free",
                    "addr": 0x1000,
                    "size": 64,
                    "stream": 0,
                    "frames": [],
                },
                {
                    "action": "segment_free",
                    "addr": 0x2000,
                    "size": 32,
                    "stream": 0,
                    "frames": [{"filename": "broken.py", "line": 3}],
                },
            ]
        ],
    }
    snapshot = tmp_path / "malformed.pkl"
    database = tmp_path / "malformed.db"
    with snapshot.open("wb") as stream:
        pickle.dump(representation, stream)

    replayed_events = 0
    original_pre_undo_event = snapshot2db.DumpEventHooker.pre_undo_event

    def pre_undo_event(self, event, current_snapshot):
        nonlocal replayed_events
        replayed_events += 1
        return original_pre_undo_event(self, event, current_snapshot)

    monkeypatch.setattr(snapshot2db.DumpEventHooker, "pre_undo_event", pre_undo_event)

    with pytest.raises(KeyError, match="name"):
        snapshot2db.dump(snapshot, database, 0)

    assert replayed_events == 0
    assert not database.exists()


def test_dump_all_removes_committed_devices_when_later_device_is_malformed(tmp_path):
    representation = {
        "segments": [],
        "device_traces": [
            [
                {
                    "action": "segment_free",
                    "addr": 0x1000,
                    "size": 64,
                    "stream": 0,
                    "frames": [],
                }
            ],
            [
                {
                    "action": "segment_free",
                    "addr": 0x2000,
                    "size": 32,
                    "stream": 0,
                    "frames": [{"filename": "broken.py", "line": 3}],
                }
            ],
        ],
    }
    snapshot = tmp_path / "malformed-multi.pkl"
    database = tmp_path / "malformed-multi.db"
    with snapshot.open("wb") as stream:
        pickle.dump(representation, stream)

    with pytest.raises(KeyError, match="name"):
        snapshot2db.dump(snapshot, database)

    assert not database.exists()


def test_failed_dump_preserves_existing_database(tmp_path):
    representation = {
        "segments": [],
        "device_traces": [
            [
                {
                    "action": "segment_free",
                    "addr": 0x1000,
                    "size": 64,
                    "stream": 0,
                    "frames": [{"filename": "broken.py", "line": 3}],
                }
            ]
        ],
    }
    snapshot = tmp_path / "malformed-existing.pkl"
    database = tmp_path / "existing.db"
    with snapshot.open("wb") as stream:
        pickle.dump(representation, stream)
    with closing(sqlite3.connect(database)) as connection, connection:
        connection.execute("CREATE TABLE marker (value TEXT)")
        connection.execute("INSERT INTO marker VALUES ('preserved')")
        connection.commit()

    with pytest.raises(KeyError, match="name"):
        snapshot2db.dump(snapshot, database, 0)

    with closing(sqlite3.connect(database)) as connection, connection:
        assert connection.execute("SELECT value FROM marker").fetchone() == ("preserved",)


def test_dump_creates_missing_destination_directories(tmp_path):
    database = tmp_path / "missing" / "nested" / "snapshot.db"

    assert snapshot2db.dump(FIXTURE_DIR / "snapshot_with_empty_cache.pkl", database, 0)
    assert database.is_file()


def test_expandable_snapshot2db(dump_database):
    result, database = dump_database("snapshot_with_empty_cache_expandable.pkl", 0)

    assert result is True
    assert database.exists()
    with closing(sqlite3.connect(database)) as connection, connection:
        assert connection.execute("SELECT COUNT(*) FROM trace_entry_0").fetchone()[0] == 8134
        assert connection.execute("SELECT COUNT(*) FROM block_0").fetchone()[0] == 3219


def test_empty_device_snapshot(tmp_path: Path):
    database = tmp_path / "empty.db"

    assert snapshot2db.dump(FIXTURE_DIR / "snapshot_with_empty_cache.pkl", database, 1) is False
    assert not database.exists()


def test_snapshot2db_dumps_oom_event_without_addr(tmp_path: Path):
    snapshot_file = tmp_path / "oom.pkl"
    snapshot_file.write_bytes(
        pickle.dumps(
            {
                "segments": [],
                "device_traces": [[{"action": "oom", "size": 1024, "device_free": 2048, "frames": []}]],
            }
        )
    )
    database = tmp_path / "oom.db"
    suppress_logs()
    try:
        result = snapshot2db.dump(snapshot_file, database, 0)
    finally:
        restore_logs()

    assert result is True
    with closing(sqlite3.connect(database)) as connection, connection:
        action, address, size = connection.execute("SELECT action, address, size FROM trace_entry_0").fetchone()

    assert action == RUNTIME_ACTION_VALUE_MAP["oom"]
    assert address == -1
    assert size == 1024


def test_dump_all_multiple_device_snapshot(dump_database):
    result, database = dump_database("snapshot_with_multi_devices.pkl")

    assert result is True
    assert database.exists()
    with closing(sqlite3.connect(database)) as connection, connection:
        tables = {
            row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
        }
    assert tables == {
        "callstack",
        "frame",
        "callstack_frame",
        "callstack_frame_manifest",
        "dictionary",
        "trace_entry_0",
        "block_0",
        "trace_entry_1",
        "block_1",
    }


def negative_id_observation(connection, table):
    count, minimum, maximum = connection.execute(
        f"SELECT COUNT(*), MIN(id), MAX(id) FROM {table} WHERE id < 0"
    ).fetchone()
    contiguous = count == 0 or maximum - minimum + 1 == count
    return count, contiguous


@pytest.mark.parametrize(("fixture_name", "device"), DATABASE_GOLDEN)
def test_database_matches_pre_relocation_golden(dump_database, fixture_name, device):
    requested_device = None if fixture_name == "snapshot_with_multi_devices.pkl" else device
    result, database = dump_database(fixture_name, requested_device)
    golden = DATABASE_GOLDEN[(fixture_name, device)]
    trace_table = f"trace_entry_{device}"
    block_table = f"block_{device}"

    assert result is True
    with closing(sqlite3.connect(database)) as connection, connection:
        rows = (
            connection.execute(f"SELECT COUNT(*) FROM {trace_table}").fetchone()[0],
            connection.execute(f"SELECT COUNT(*) FROM {block_table}").fetchone()[0],
        )
        actions = dict(
            connection.execute(f"SELECT action, COUNT(*) FROM {trace_table} GROUP BY action ORDER BY action").fetchall()
        )
        first_totals = connection.execute(
            f"SELECT allocated, active, reserved FROM {trace_table} ORDER BY id LIMIT 1"
        ).fetchone()
        last_positive_totals = connection.execute(
            f"SELECT allocated, active, reserved FROM {trace_table} WHERE id >= 0 ORDER BY id DESC LIMIT 1"
        ).fetchone()
        callstacks = connection.execute(
            f"SELECT COUNT(*) FROM {trace_table} t JOIN callstack c ON c.id = t.callstackId WHERE c.callstack != ''"
        ).fetchone()[0]

        assert rows == golden["rows"]
        assert actions == golden["actions"]
        assert negative_id_observation(connection, trace_table) == (
            golden["synthetic"][0],
            True,
        )
        assert negative_id_observation(connection, block_table) == (
            golden["synthetic"][1],
            True,
        )
        assert first_totals == golden["first_totals"]
        assert last_positive_totals == golden["last_positive_totals"]
        assert callstacks == golden["nonempty_callstacks"]


def test_database_schema_and_action_state_mapping_are_exact(dump_database):
    _, database = dump_database("snapshot_with_multi_devices.pkl")

    assert RUNTIME_ACTION_VALUE_MAP == ACTION_VALUE_MAP
    assert RUNTIME_BLOCK_STATE_VALUE_MAP == BLOCK_STATE_VALUE_MAP
    with closing(sqlite3.connect(database)) as connection, connection:
        assert connection.execute("PRAGMA table_info(callstack)").fetchall() == CALLSTACK_SCHEMA
        for device in (0, 1):
            assert connection.execute(f"PRAGMA table_info(trace_entry_{device})").fetchall() == TRACE_SCHEMA
            assert connection.execute(f"PRAGMA table_info(block_{device})").fetchall() == BLOCK_SCHEMA
            dictionary = connection.execute(
                "SELECT `table`, `column`, `key`, `value` FROM dictionary "
                "WHERE `table` IN (?, ?) ORDER BY `table`, `column`, CAST(`key` AS INTEGER)",
                (f"block_{device}", f"trace_entry_{device}"),
            ).fetchall()
            assert dictionary == [
                (f"block_{device}", "state", "-1", "inactive"),
                (f"block_{device}", "state", "0", "active_pending_free"),
                (f"block_{device}", "state", "1", "active_allocated"),
                *[
                    (f"trace_entry_{device}", "action", str(value), action)
                    for action, value in ACTION_VALUE_MAP.items()
                ],
            ]


def test_multi_device_database_rows_are_isolated(dump_database):
    _, database = dump_database("snapshot_with_multi_devices.pkl")
    with closing(sqlite3.connect(database)) as connection, connection:
        device_zero = connection.execute("SELECT COUNT(*), SUM(size), MAX(reserved) FROM trace_entry_0").fetchone()
        device_one = connection.execute("SELECT COUNT(*), SUM(size), MAX(reserved) FROM trace_entry_1").fetchone()

    assert device_zero != device_one
    assert device_zero[0] == DATABASE_GOLDEN[("snapshot_with_multi_devices.pkl", 0)]["rows"][0]
    assert device_one[0] == DATABASE_GOLDEN[("snapshot_with_multi_devices.pkl", 1)]["rows"][0]


def test_callstack_serialization_preserves_frame_order(dump_database):
    _, database = dump_database("snapshot_1768383987920985470.pkl", 0)
    with closing(sqlite3.connect(database)) as connection, connection:
        callstack = connection.execute(
            "SELECT c.callstack FROM trace_entry_0 t "
            "JOIN callstack c ON c.id = t.callstackId "
            "WHERE c.callstack LIKE '%\n%' LIMIT 1"
        ).fetchone()[0]

    lines = callstack.splitlines()
    assert len(lines) >= 2
    assert all(":" in line and " " in line for line in lines)


def test_callstack_table_is_deduplicated_and_covers_every_event(dump_database):
    _, database = dump_database("snapshot_1768383987920985470.pkl", 0)
    with closing(sqlite3.connect(database)) as connection, connection:
        rows, distinct_ids, distinct_texts = connection.execute(
            "SELECT COUNT(*), COUNT(DISTINCT id), COUNT(DISTINCT callstack) FROM callstack"
        ).fetchone()
        events, resolved = connection.execute(
            "SELECT COUNT(*), COUNT(c.id) FROM trace_entry_0 t LEFT JOIN callstack c ON c.id = t.callstackId"
        ).fetchone()

    # One row per distinct text keeps grouping by id equivalent to grouping by text.
    assert rows == distinct_ids == distinct_texts
    # Every event resolves to a callstack row, and interning actually collapses rows.
    assert resolved == events
    assert rows < events
