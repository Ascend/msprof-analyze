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

from __future__ import annotations

import copy
import sqlite3
from contextlib import closing

import pytest

from pt_snap_cli.core.splitting.sharded_replay_service import ShardedReplayService
from pt_snap_cli.snapshot.base import Block, BlockState
from pt_snap_cli.snapshot.representation import save_snapshot_representation
from pt_snap_cli.snapshot.simulate import SimulateDeviceSnapshot
from pt_snap_cli.snapshot.tools.adaptors import sharded_replay, snapshot2db
from pt_snap_cli.snapshot.tools.adaptors.database.snapshot_db import SnapshotDb

from .helpers import FIXTURE_DIR
from .test_simulate import Hooker, make_torch_npu_workspace_snapshot


def event(action, addr=1000, size=16, stream=0):
    return {
        "action": action,
        "addr": addr,
        "size": size,
        "stream": stream,
        "frames": [{"filename": "source.py", "line": 4, "name": action}],
    }


def block(addr, size, requested):
    return {
        "address": addr,
        "size": size,
        "requested_size": requested,
        "state": "active_allocated",
        "frames": [],
    }


def segment(stream, total, blocks):
    return {
        "address": 1000,
        "total_size": total,
        "stream": stream,
        "segment_type": "small",
        "allocated_size": sum(item["size"] for item in blocks),
        "active_size": sum(item["size"] for item in blocks),
        "device": 0,
        "is_expandable": False,
        "frames": [],
        "blocks": blocks,
    }


def lifecycle_data():
    return {
        "segments": [
            segment(0, 64, [block(1000, 16, 14), block(1040, 8, 6)]),
            segment(1, 32, [block(1000, 8, 5)]),
        ],
        "device_traces": [
            [
                event("alloc"),
                event("alloc", size=8, stream=1),
                event("oom"),
                event("free_requested"),
                event("oom"),
                event("free_completed"),
                event("alloc"),
                event("oom"),
                event("oom"),
            ]
        ],
    }


def write_source(tmp_path, data):
    path = tmp_path / "input.pkl"
    save_snapshot_representation(data, path, "pickle")
    return path


def rows(path, sql):
    with closing(sqlite3.connect(path)) as conn:
        return conn.execute(sql).fetchall()


@pytest.mark.parametrize("capacity", [1, 2, 3, 100])
def test_shards_equal_single_db_events_blocks_boundaries_and_references(tmp_path, capacity):
    data = lifecycle_data()
    original = copy.deepcopy(data)
    source = write_source(tmp_path, data)
    full = tmp_path / "full.db"
    assert snapshot2db.dump(source, full)
    result = ShardedReplayService().stage(source, tmp_path / "stage", events_per_slice=capacity)
    full_events = rows(
        full,
        "SELECT t.id,t.action,t.address,t.size,t.stream,t.allocated,t.active,t.reserved,c.callstack FROM trace_entry_0 t JOIN callstack c ON c.id=t.callstackId WHERE t.id>=0 ORDER BY t.id",
    )
    collected = []
    identities = {}
    for item in result.slices:
        collected += rows(
            item.file,
            "SELECT t.id,t.action,t.address,t.size,t.stream,t.allocated,t.active,t.reserved,c.callstack FROM trace_entry_0 t JOIN callstack c ON c.id=t.callstackId WHERE t.id>=0 ORDER BY t.id",
        )
        assert len(rows(item.file, "SELECT id FROM trace_entry_0 WHERE id>=0")) <= capacity
        references = {row[0]: row[1:] for row in rows(item.file, "SELECT * FROM pt_snap_block_reference")}
        shard_blocks = rows(item.file, "SELECT * FROM block_0")
        for record in shard_blocks:
            signature = record[1:4] + record[5:]
            assert record[0] not in identities or identities[record[0]] == signature
            identities[record[0]] = signature
            if record[5] >= 0:
                assert record[0] == record[5]
                assert references[record[0]][1] == "source.py:4 alloc"
            else:
                assert record[0] < 0 and references[record[0]][1] is None
            if record[6] >= 0:
                assert record[6] == 5  # Never free_requested=3.
                assert references[record[0]][2] == "source.py:4 free_completed"
        # Replay the full simulator to the identical left boundary as an oracle.
        oracle = SimulateDeviceSnapshot(data, 0)
        assert oracle.replay_until(item.start_position)
        state = oracle.device_snapshot
        expected_blocks = sorted(
            (seg.stream, b.address, b.size, b.requested_size, b.state) for seg in state.segments for b in seg.blocks
        )
        observed_blocks = sorted(
            (
                references[r[0]][0],
                r[1],
                r[2],
                r[3],
                {-1: "inactive", 0: "active_pending_free", 1: "active_allocated"}[r[4]],
            )
            for r in shard_blocks
            if (r[5] == -1 or r[5] < item.start_event_id) and (r[6] == -1 or r[6] >= item.start_event_id)
        )
        assert observed_blocks == expected_blocks
        boundaries = rows(
            item.file,
            "SELECT action,address,size,stream,allocated,active,reserved FROM trace_entry_0 WHERE id<0",
        )
        assert sorted(row[1:4] for row in boundaries) == sorted(
            (seg.address, seg.total_size, seg.stream) for seg in state.segments
        )
        assert all(
            row[4:] == (state.total_allocated, state.total_activated, state.total_reserved) for row in boundaries
        )
        # Active geometry at EVERY real event, not just shard edges.
        for position in range(item.start_position, item.end_position + 1):
            current = SimulateDeviceSnapshot(data, 0)
            assert current.replay_until(position + 1)
            expected = sorted(
                (seg.stream, b.address, b.size, b.requested_size)
                for seg in current.device_snapshot.segments
                for b in seg.blocks
            )
            active = sorted(
                (references[r[0]][0], r[1], r[2], r[3])
                for r in shard_blocks
                if (r[5] == -1 or r[5] <= position) and (r[6] == -1 or r[6] > position)
            )
            assert active == expected
    assert collected == full_events
    expected_signatures = {row[1:4] + row[5:] for row in rows(full, "SELECT * FROM block_0")}
    assert set(identities.values()) == expected_signatures
    assert {key for key in identities if key >= 0} == {0, 1, 6}
    assert data == original
    assert not (result.directory / "manifest.json").exists()


def test_pending_free_left_boundary_has_state_zero(tmp_path):
    result = ShardedReplayService().stage(
        write_source(tmp_path, lifecycle_data()), tmp_path / "stage", events_per_slice=2
    )
    assert rows(result.slices[2].file, "SELECT id,state,freeEventId FROM block_0 WHERE id=0") == [(0, 0, 5)]


@pytest.mark.parametrize(
    "fixture",
    [
        "snapshot_expandable.pkl",
        "snapshot_with_empty_cache_expandable.pkl",
        "snapshot_with_multi_devices.pkl",
    ],
)
def test_reviewed_fixtures_real_events_match_single_db(tmp_path, fixture):
    source = FIXTURE_DIR / fixture
    full = tmp_path / "full.db"
    assert snapshot2db.dump(source, full)
    result = ShardedReplayService().stage(source, tmp_path / "stage", events_per_slice=1000)
    for device in {item.device for item in result.slices}:
        observed = []
        for item in result.slices:
            if item.device == device:
                observed += rows(
                    item.file,
                    f"SELECT id,action,address,size,stream,allocated,active,reserved FROM trace_entry_{device} WHERE id>=0 ORDER BY id",
                )
        assert observed == rows(
            full,
            f"SELECT id,action,address,size,stream,allocated,active,reserved FROM trace_entry_{device} WHERE id>=0 ORDER BY id",
        )


def test_workspace_oom_and_sparse_native_ids_are_not_relabelled(tmp_path):
    data = make_torch_npu_workspace_snapshot()
    data["device_traces"][0].append({"action": "oom", "size": 2048, "device_free": 512, "frames": []})
    for index, entry in enumerate(data["device_traces"][0]):
        entry["id"] = 10 + index * 2
    source = write_source(tmp_path, data)
    result = ShardedReplayService().stage(source, tmp_path / "stage", events_per_slice=1)
    actions = [
        rows(item.file, "SELECT id,action,allocated,active,reserved FROM trace_entry_0 WHERE id>=0")[0]
        for item in result.slices
    ]
    assert [row[:2] for row in actions] == [(10, 7), (12, 2), (14, 4), (16, 8)]
    assert actions[-1][2:] == (4096, 4096, 4096)
    assert rows(result.slices[-1].file, "SELECT id,allocEventId FROM block_0") == [(14, 14)]


def test_pause_resume_matches_full_hooks_and_state():
    data = lifecycle_data()
    complete = SimulateDeviceSnapshot(data, 0)
    paused = SimulateDeviceSnapshot(data, 0)
    hooks = [Hooker(), Hooker()]
    complete.register_hooker(hooks[0])
    paused.register_hooker(hooks[1])
    assert complete.replay()
    for endpoint in [9, 7, 7, 5, 2, 0, 0]:
        assert paused.replay_until(endpoint)
    assert hooks[0].calls == hooks[1].calls
    assert complete.device_snapshot.to_dict() == paused.device_snapshot.to_dict()


@pytest.mark.parametrize("endpoint", [-1, True, 1.5, 10])
def test_invalid_pause_endpoint_preserves_state(endpoint):
    simulator = SimulateDeviceSnapshot(lifecycle_data(), 0)
    before = simulator.device_snapshot.to_dict()
    with pytest.raises(ValueError, match="remaining_events"):
        simulator.replay_until(endpoint)
    assert simulator.device_snapshot.to_dict() == before


@pytest.mark.parametrize("phase", ["pre", "post", "allocator"])
def test_pause_failure_semantics_remain_original(phase, monkeypatch):
    simulator = SimulateDeviceSnapshot(lifecycle_data(), 0)
    hook = Hooker(pre=phase != "pre", post=phase != "post")
    simulator.register_hooker(hook)
    if phase == "allocator":
        monkeypatch.setattr(simulator.replay_executor, "execute", lambda _: False)
    assert not simulator.replay_until(8)
    assert len(simulator.device_snapshot.trace_entries) == (8 if phase == "post" else 9)


@pytest.mark.parametrize("failure", ["replay", "boundary", "flush", "backfill", "validation", "constructor"])
def test_failures_close_every_writer_and_return_no_ready_result(tmp_path, monkeypatch, failure):
    connections = []
    original = SnapshotDb.__init__

    def track(self, *args, **kwargs):
        original(self, *args, **kwargs)
        connections.append(self.conn)

    monkeypatch.setattr(SnapshotDb, "__init__", track)

    def fail(*args, **kwargs):
        raise RuntimeError("injected failure")

    if failure == "replay":
        monkeypatch.setattr(SimulateDeviceSnapshot, "replay_until", lambda *_: False)
    elif failure == "boundary":
        monkeypatch.setattr(sharded_replay._SliceHook, "dump_left_boundary", fail)
    elif failure == "flush":
        monkeypatch.setattr(snapshot2db.SnapshotDbHandler, "flush", fail)
    elif failure == "constructor":
        monkeypatch.setattr(SnapshotDb, "create_block_table", fail)
    elif failure == "backfill":
        monkeypatch.setattr(sharded_replay.BlockRegistry, "finalize", fail)
    else:
        monkeypatch.setattr(sharded_replay.BlockRegistry, "validate", fail)
    with pytest.raises(RuntimeError):
        ShardedReplayService().stage(write_source(tmp_path, lifecycle_data()), tmp_path / "stage", events_per_slice=2)
    assert connections
    for conn in connections:
        with pytest.raises(sqlite3.ProgrammingError, match="closed"):
            conn.execute("SELECT 1")
    assert not (tmp_path / "stage" / "manifest.json").exists()


def test_registry_does_not_merge_distinct_same_address_objects():
    registry = sharded_replay.BlockRegistry()
    a = Block(address=1, size=2, requested_size=1, state=BlockState.ACTIVE_ALLOCATED)
    b = copy.copy(a)
    assert registry.observe(a, 0).token != registry.observe(b, 0).token
    assert registry.observe(a, 0).token == -1
    with pytest.raises(RuntimeError, match="stream"):
        registry.observe(a, 1)


def test_finalization_sql_failure_closes_rw_connection(tmp_path, monkeypatch):
    original = sharded_replay.BlockRegistry.finalize
    captured = []

    def broken(self):
        path = next(iter(self.members))
        with closing(sqlite3.connect(path)) as conn, conn:
            conn.execute("DELETE FROM block_0")
        real_connect = sqlite3.connect

        def connect(*args, **kwargs):
            conn = real_connect(*args, **kwargs)
            captured.append(conn)
            return conn

        monkeypatch.setattr(sharded_replay.sqlite3, "connect", connect)
        return original(self)

    monkeypatch.setattr(sharded_replay.BlockRegistry, "finalize", broken)
    with pytest.raises(RuntimeError, match="Missing provisional"):
        ShardedReplayService().stage(write_source(tmp_path, lifecycle_data()), tmp_path / "stage", events_per_slice=2)
    assert captured
    for conn in captured:
        with pytest.raises(sqlite3.ProgrammingError):
            conn.execute("SELECT 1")


def test_snapshot_db_constructor_failure_closes_connection(tmp_path, monkeypatch):
    captured = []

    def fail(self):
        captured.append(self.conn)
        raise RuntimeError("constructor failure")

    monkeypatch.setattr(SnapshotDb, "_clear_old_tables", fail)
    with pytest.raises(RuntimeError):
        SnapshotDb(str(tmp_path / "failure.db"))
    with pytest.raises(sqlite3.ProgrammingError):
        captured[0].execute("SELECT 1")


def test_writer_commit_failure_closes_connection(tmp_path):
    handler = snapshot2db.SnapshotDbHandler(str(tmp_path / "db"), [0])
    conn = handler.db.conn

    class BrokenCommit:
        def commit(self):
            raise RuntimeError("commit failure")

        def close(self):
            conn.close()

    handler.db.conn = BrokenCommit()
    with pytest.raises(RuntimeError):
        handler.close()
    handler.close()
    with pytest.raises(sqlite3.ProgrammingError):
        conn.execute("SELECT 1")


def test_actual_sql_backfill_abort_rolls_back_and_closes(tmp_path, monkeypatch):
    original = sharded_replay.BlockRegistry.finalize
    real_connect = sqlite3.connect
    captured, paths = [], []

    def rejected(self):
        path = next(iter(self.members))
        paths.append(path)
        with closing(real_connect(path)) as conn, conn:
            conn.execute(
                "CREATE TRIGGER reject_patch BEFORE UPDATE ON block_0 "
                "BEGIN SELECT RAISE(ABORT, 'backfill rejected'); END"
            )

        def connect(*args, **kwargs):
            conn = real_connect(*args, **kwargs)
            captured.append(conn)
            return conn

        monkeypatch.setattr(sharded_replay.sqlite3, "connect", connect)
        original(self)

    monkeypatch.setattr(sharded_replay.BlockRegistry, "finalize", rejected)
    with pytest.raises(sqlite3.IntegrityError, match="backfill rejected"):
        ShardedReplayService().stage(write_source(tmp_path, lifecycle_data()), tmp_path / "stage", events_per_slice=2)
    for conn in captured:
        with pytest.raises(sqlite3.ProgrammingError, match="closed"):
            conn.execute("SELECT 1")
    with closing(real_connect(paths[0])) as conn:
        assert all(row[0] < 0 for row in conn.execute("SELECT id FROM block_0"))
        assert not conn.execute("SELECT name FROM sqlite_master WHERE name='pt_snap_block_reference'").fetchall()


@pytest.mark.parametrize(
    ("sql", "message"),
    [
        ("DELETE FROM trace_entry_0 WHERE id>=0", "lost or changed real events"),
        ("UPDATE block_0 SET requestedSize=0", "identity/lifetime"),
        ("DELETE FROM pt_snap_block_reference", "callstack references"),
    ],
)
def test_final_validation_rejects_corrupt_finalized_shard(tmp_path, monkeypatch, sql, message):
    original = sharded_replay.BlockRegistry.finalize

    def corrupt(self):
        original(self)
        path = next(iter(self.members))
        with closing(sqlite3.connect(path)) as conn, conn:
            conn.execute(sql)

    monkeypatch.setattr(sharded_replay.BlockRegistry, "finalize", corrupt)
    with pytest.raises(RuntimeError, match=message):
        ShardedReplayService().stage(write_source(tmp_path, lifecycle_data()), tmp_path / "stage", events_per_slice=2)
    assert not (tmp_path / "stage" / "manifest.json").exists()
