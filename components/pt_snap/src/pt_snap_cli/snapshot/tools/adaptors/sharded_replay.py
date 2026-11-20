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

"""Internal native-v2 shard construction; no compatibility export or publication.

All writers close before finalization. Only a successful return makes identities
stable. Partial files in the caller's private staging directory are NOT ready.
"""

from __future__ import annotations

import sqlite3
from contextlib import closing
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Tuple, Union

from ...base import Block, BlockState, DeviceSnapshot, TraceEntry
from ...simulate import AllocatorHooker, SimulateDeviceSnapshot, SimulateHooker
from .database import CallstackInterner, event2record
from .ordered_frames import OrderedFrameWriter
from .snapshot2db import SnapshotDbHandler


@dataclass(frozen=True)
class ReplaySlice:
    device: int
    index: int
    start_position: int
    end_position: int
    start_event_id: int
    end_event_id: int
    file: Path


@dataclass
class _Lifetime:
    # Retain the ORIGINAL object: copied allocator hook payloads and address reuse
    # cannot alias it, and Python cannot recycle its object identity during replay.
    block: Block
    token: int
    stream: int
    alloc_stack: Union[str, None] = None
    free_stack: Union[str, None] = None

    @property
    def final_id(self) -> int:
        return self.token if self.block.alloc_event_idx is None else self.block.alloc_event_idx

    def signature(self) -> Tuple[int, int, int, int, int]:
        block = self.block
        return (
            block.address,
            block.size,
            block.requested_size,
            -1 if block.alloc_event_idx is None else block.alloc_event_idx,
            -1 if block.free_event_idx is None else block.free_event_idx,
        )


@dataclass
class BlockRegistry:
    """One snapshot/device-local registry; provisional IDs never escape staging."""

    lifetimes: Dict[int, _Lifetime] = field(default_factory=dict)
    members: Dict[Path, Dict[int, _Lifetime]] = field(default_factory=dict)

    def observe(self, block: Block, stream: int) -> _Lifetime:
        key = id(block)
        lifetime = self.lifetimes.get(key)
        if lifetime is None:
            lifetime = _Lifetime(block, -len(self.lifetimes) - 1, stream)
            self.lifetimes[key] = lifetime
        elif lifetime.stream != stream:
            raise RuntimeError("Block changed stream during its lifetime")
        return lifetime

    def record(self, path: Path, block: Block, stream: int) -> Union[Dict[str, Any], None]:
        lifetime = self.observe(block, stream)
        members = self.members.setdefault(path, {})
        if lifetime.token in members:
            return None
        members[lifetime.token] = lifetime
        return {
            "id": lifetime.token,
            "address": block.address,
            "size": block.size,
            "requestedSize": block.requested_size,
            "state": block.state,
            "allocEventId": -1,
            "freeEventId": -1 if block.free_event_idx is None else block.free_event_idx,
        }

    def finalize(self) -> None:
        """Batch patches by closed DB, including free_completed and stack sources.

        Unknown/preexisting allocations keep their unique negative token; no
        compaction is necessary or allowed to merge unrelated objects.
        """
        for path, members in self.members.items():
            parent_name = path.parent.name
            device = int(parent_name[len("device_") :] if parent_name.startswith("device_") else parent_name)
            # pylint: disable-next=confusing-with-statement  # closing() owns lifetime; SQLite owns the transaction.
            with closing(sqlite3.connect(path.as_uri() + "?mode=rw", uri=True)) as conn, conn:
                changes = conn.total_changes
                conn.executemany(
                    f'UPDATE "block_{device}" SET id=?, allocEventId=?, freeEventId=? WHERE id=?',  # nosec B608 # SQL structure uses validated integer IDs and fixed/allowlisted schema fragments; values are bound.
                    [(item.final_id, *item.signature()[-2:], token) for token, item in members.items()],
                )
                if conn.total_changes - changes != len(members):
                    raise RuntimeError("Missing provisional block during finalization")
                conn.execute(
                    "CREATE TABLE pt_snap_block_reference (blockId INTEGER PRIMARY KEY, "
                    "stream INTEGER NOT NULL, allocCallstack TEXT, freeCallstack TEXT)"
                )
                conn.executemany(
                    "INSERT INTO pt_snap_block_reference VALUES (?, ?, ?, ?)",
                    [(item.final_id, item.stream, item.alloc_stack, item.free_stack) for item in members.values()],
                )

    def validate(self, item: ReplaySlice, expected_ids: List[int]) -> None:
        with closing(sqlite3.connect(item.file.as_uri() + "?mode=ro", uri=True)) as conn:
            if conn.execute("PRAGMA quick_check").fetchall() != [("ok",)]:
                raise RuntimeError("Invalid finalized SQLite shard")
            ids = [row[0] for row in conn.execute(f"SELECT id FROM trace_entry_{item.device} WHERE id>=0 ORDER BY id")]  # nosec B608 # SQL structure uses validated integer IDs and fixed/allowlisted schema fragments; values are bound.
            if ids != expected_ids:
                raise RuntimeError("Shard lost or changed real events")
            rows = conn.execute(
                f"SELECT id,address,size,requestedSize,allocEventId,freeEventId FROM block_{item.device}"  # nosec B608 # SQL structure uses validated integer IDs and fixed/allowlisted schema fragments; values are bound.
            ).fetchall()
            expected = {(lifetime.final_id, *lifetime.signature()) for lifetime in self.members[item.file].values()}
            if len(rows) != len(expected) or set(rows) != expected:
                raise RuntimeError("Incomplete block identity/lifetime finalization")
            references = conn.execute("SELECT * FROM pt_snap_block_reference").fetchall()
            if set(references) != {
                (lifetime.final_id, lifetime.stream, lifetime.alloc_stack, lifetime.free_stack)
                for lifetime in self.members[item.file].values()
            }:
                raise RuntimeError("Incomplete cross-slice callstack references")


class _SliceHook(SimulateHooker, AllocatorHooker):
    def __init__(self, item: ReplaySlice, registry: BlockRegistry):
        self.item = item
        self.registry = registry
        self.writer = SnapshotDbHandler(str(item.file), [item.device])
        self.stacks = CallstackInterner()
        self.frames = OrderedFrameWriter(self.writer.db.conn)
        self.current_event: Union[TraceEntry, None] = None

    def pre_undo_event(self, wait4undo_event: TraceEntry, current_snapshot: DeviceSnapshot) -> bool:
        event, snapshot = wait4undo_event, current_snapshot
        self.current_event = event
        self.frames.insert(event)
        self.writer.insert_event(
            event2record(
                event,
                snapshot.total_allocated,
                snapshot.total_activated,
                snapshot.total_reserved,
                callstacks=self.stacks,
            ),
            snapshot.device,
        )
        return True

    def post_undo_event(self, already_undo_event: TraceEntry, current_snapshot: DeviceSnapshot) -> bool:
        return True

    def post_replay_alloc_block(self, allocated_block: Block, current_snapshot: DeviceSnapshot):
        assert self.current_event is not None  # nosec B101 # Internal invariant after validation; not an input security check.
        lifetime = self.registry.observe(allocated_block, self.current_event.stream)
        lifetime.free_stack = self.current_event.get_callstack()

    def pre_replay_free_block(self, wait4free_block: Block, current_snapshot: DeviceSnapshot):
        # This hook receives the original block before detach; the post hook is
        # a shallow copy and MUST NOT be used as an object-identity registry key.
        assert self.current_event is not None  # nosec B101 # Internal invariant after validation; not an input security check.
        lifetime = self.registry.observe(wait4free_block, self.current_event.stream)
        lifetime.alloc_stack = self.current_event.get_callstack()
        self._write_block(wait4free_block, lifetime.stream, current_snapshot.device)

    def _write_block(self, block: Block, stream: int, device: int):
        record = self.registry.record(self.item.file, block, stream)
        if record is not None:
            self.writer.insert_block(record, device)

    def dump_left_boundary(self, snapshot: DeviceSnapshot):
        # Called AFTER undoing the first event in this window. Segment rows and
        # block states describe the instant BEFORE that first event, not after.
        for index, segment in enumerate(snapshot.segments, start=1):
            for block in segment.blocks:
                if block.state != BlockState.INACTIVE:
                    self._write_block(block, segment.stream, snapshot.device)
            boundary = TraceEntry(
                idx=-index,
                action="segment_map" if segment.is_expandable else "segment_alloc",
                addr=segment.address,
                size=segment.total_size,
                stream=segment.stream,
                frames=segment.frames,
                _raw_frames=segment._raw_frames,
            )
            self.writer.insert_event(
                event2record(
                    boundary,
                    snapshot.total_allocated,
                    snapshot.total_activated,
                    snapshot.total_reserved,
                    callstacks=self.stacks,
                ),
                snapshot.device,
            )


def build_shards(
    data: Dict[str, Any], directory: Path, events_per_slice: int, devices: Tuple[int, ...]
) -> Tuple[ReplaySlice, ...]:
    """Build inside a caller-owned private EMPTY directory; never publish readiness.

    Core validates options and owns staging. Native v2 preserves OOM/workspace;
    this is NOT the compatibility-v1 dataset validated by dataset_contract.
    """
    results: List[ReplaySlice] = []
    for device in devices:
        simulator = SimulateDeviceSnapshot(data, device, _raw_frames=True)
        events = simulator.device_snapshot.trace_entries
        event_ids = [event.idx for event in events]
        # pylint: disable-next=unidiomatic-typecheck  # Exact integer IDs reject bool and subclasses.
        if any(type(value) is not int or value < 0 for value in event_ids):
            raise ValueError("Real event IDs must be nonnegative integers")
        ids = [int(value) for value in event_ids if value is not None]
        if ids != sorted(set(ids)):
            raise ValueError("Real event IDs must be unique and chronological")
        registry = BlockRegistry()
        device_dir = directory / f"device_{device}"
        device_dir.mkdir()
        slices: List[ReplaySlice] = []
        for index in reversed(range((len(events) + events_per_slice - 1) // events_per_slice)):
            start = index * events_per_slice
            end = min(start + events_per_slice, len(ids)) - 1
            item = ReplaySlice(
                device,
                index,
                start,
                end,
                ids[start],
                ids[end],
                device_dir / f"slice_{index:05d}.db",
            )
            registry.members[item.file] = {}
            hook = _SliceHook(item, registry)
            hook_id = simulator.register_hooker(hook)
            allocator_id = simulator.register_allocator_hooker(hook)
            try:
                if not simulator.replay_until(start):
                    raise RuntimeError(f"Replay failed for device {device}, slice {index}")
                hook.dump_left_boundary(simulator.device_snapshot)
                hook.writer.flush(device)
                hook.writer.insert_callstacks(hook.stacks.records())
                hook.writer.close()
            finally:
                simulator.unregister_hooker(hook_id)
                simulator.unregister_allocator_hooker(allocator_id)
                hook.writer.close(commit=False)
            slices.append(item)
        registry.finalize()
        for item in slices:
            registry.validate(item, ids[item.start_position : item.end_position + 1])
        results.extend(reversed(slices))
    return tuple(results)
