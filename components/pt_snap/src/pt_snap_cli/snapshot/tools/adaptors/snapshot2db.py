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

import os
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Union, cast

from pt_snap_cli._compat import unlink_missing_ok

from ...base import Block, BlockState, DeviceSnapshot, TraceEntry
from ...representation import UnsafePickleError, load_snapshot_representation, replay_snapshot
from ...simulate import AllocatorHooker, SimulateHooker
from ...util.logger import get_logger, set_global_log_file
from .database import CallstackInterner, SnapshotDb, block2record, event2record

dump_logger = get_logger("DatabaseDump")


# Import stages rows in a temporary database and only publishes it after a
# successful replay, so batches are sized for throughput rather than durability.
DEFAULT_INSERT_CACHE_SIZE = 10000


class SnapshotDbHandler:
    def __init__(
        self,
        db_path: str,
        devices: List[int],
        insert_cache_size: int = DEFAULT_INSERT_CACHE_SIZE,
        *,
        structured_frames: bool = False,
    ):
        self._closed = True
        self.db_path = db_path
        self.db = SnapshotDb(db_path)
        self._closed = False
        self._device_event_cache = {}
        self._device_block_cache = {}
        self._insert_cache_size = insert_cache_size
        try:
            self.db.create_callstack_table(structured_frames=structured_frames)
            for device in devices:
                self._device_block_cache[device] = []
                self._device_event_cache[device] = []
                self.db.create_trace_entry_table(device)
                self.db.create_block_table(device)
        except BaseException:
            self.close(commit=False)
            raise

    def insert_event(self, event_record: Dict[str, Any], device: int = 0):
        if device not in self._device_event_cache:
            self._device_event_cache[device] = []
        self._device_event_cache[device].append(event_record)
        if len(self._device_event_cache[device]) >= self._insert_cache_size:
            self._do_insert_events(device)

    def insert_block(self, block_record: Dict[str, Any], device: int = 0):
        if device not in self._device_block_cache:
            self._device_block_cache[device] = []
        self._device_block_cache[device].append(block_record)
        if len(self._device_block_cache[device]) >= self._insert_cache_size:
            self._do_insert_blocks(device)

    def flush(self, device: int = 0):
        if self._device_event_cache.get(device, None):
            self._do_insert_events(device)
        if self._device_block_cache.get(device, None):
            self._do_insert_blocks(device)

    def insert_callstacks(self, records: List[Dict[str, Any]]):
        """Write the interned callstack table once every device has replayed."""
        if not records:
            return
        self.db.get_callstack_table().insert_records(self.db.conn, records)
        self.db.conn.commit()

    def _do_insert_events(self, device: int = 0):
        if device not in self._device_event_cache:
            self._device_event_cache[device] = []
            return
        self.db.get_trace_entry_table(device).insert_records(self.db.conn, self._device_event_cache[device])
        self.db.conn.commit()
        self._device_event_cache[device].clear()

    def _do_insert_blocks(self, device: int = 0):
        if device not in self._device_block_cache:
            self._device_block_cache[device] = []
        self.db.get_block_table(device).insert_records(self.db.conn, self._device_block_cache[device])
        self.db.conn.commit()
        self._device_block_cache[device].clear()

    def close(self, *, commit: bool = True):
        if getattr(self, "_closed", True):
            return
        try:
            if commit:
                self.db.conn.commit()
            else:
                self.db.conn.rollback()
        finally:
            self.db.conn.close()
            self._closed = True

    def __del__(self):
        self.close()


class DumpEventHooker(SimulateHooker, AllocatorHooker):
    def __init__(self, db_path: str, devices: List[int], dump_cache_size: int = DEFAULT_INSERT_CACHE_SIZE):
        self.db_handler = SnapshotDbHandler(db_path, devices, insert_cache_size=dump_cache_size, structured_frames=True)
        # Standalone v3 opts in; native shard writers keep the default text contract.
        # One interner for the whole dump so devices share identical callstacks.
        self.callstacks = CallstackInterner(structured_frames=True)

    def post_undo_event(self, already_undo_event: TraceEntry, current_snapshot: DeviceSnapshot) -> bool:
        # 回放完毕，dump剩余Segment及block数据, 注意应该先插入blocks
        if not current_snapshot.trace_entries:
            for seg in current_snapshot.segments:
                for block in seg.blocks:
                    if block.state != BlockState.INACTIVE:
                        self.db_handler.insert_block(block2record(block), current_snapshot.device)
                # segment不插入block表，而是以模拟事件插入事件表，便于后续重建segment
                mock_segment_alloc_event = TraceEntry(
                    idx=None,
                    action="segment_map" if seg.is_expandable else "segment_alloc",
                    addr=seg.address,
                    frames=seg.frames,
                    _raw_frames=seg._raw_frames,
                    size=seg.total_size,
                    stream=seg.stream,
                )
                self.db_handler.insert_event(
                    event2record(
                        event=mock_segment_alloc_event,
                        allocated=current_snapshot.total_allocated,
                        active=current_snapshot.total_activated,
                        reserved=current_snapshot.total_reserved,
                        callstacks=self.callstacks,
                    ),
                    current_snapshot.device,
                )
        return True

    def pre_undo_event(self, wait4undo_event: TraceEntry, current_snapshot: DeviceSnapshot) -> bool:
        # 每个事件回放前dump一次event
        self.db_handler.insert_event(
            event2record(
                event=wait4undo_event,
                allocated=current_snapshot.total_allocated,
                active=current_snapshot.total_activated,
                reserved=current_snapshot.total_reserved,
                callstacks=self.callstacks,
            ),
            current_snapshot.device,
        )
        return True

    def post_replay_free_block(self, released_block: Block, current_snapshot: DeviceSnapshot):
        self.db_handler.insert_block(block2record(released_block), current_snapshot.device)

    def flush(self, device: int = 0):
        self.db_handler.flush(device)

    def flush_callstacks(self):
        self.db_handler.insert_callstacks(self.callstacks.records())
        db = self.db_handler.db
        db.get_table_by_name("frame").insert_records(db.conn, self.callstacks.frame_records())
        db.get_table_by_name("callstack_frame").insert_records(db.conn, self.callstacks.stack_frame_records())
        db.get_table_by_name("callstack_frame_manifest").insert_records(
            db.conn, self.callstacks.stack_manifest_records()
        )

    def close(self, *, commit: bool = True):
        self.db_handler.close(commit=commit)


def dump(pickle_file: Union[str, Path], dump_file: Union[str, Path], device: Union[int, None] = None) -> bool:
    try:
        data = load_snapshot_representation(Path(pickle_file))
    except UnsafePickleError:
        raise
    except Exception as e:
        dump_logger.error('Failed to load pickle file: %s', e)
        return False
    # Snapshot format: one list of trace dictionaries per device.
    device_traces = cast(List[List[object]], data.get("device_traces", []))
    # 当指定device为空时dump所有记录了跟踪事件的device，否则仅dump指定device
    need_dump_devices = [device for device in range(len(device_traces)) if device_traces[device]]
    dump_logger.info('Recognized have trace events devices %s.', need_dump_devices)
    if device is not None and device not in need_dump_devices:
        dump_logger.error('Specified device %s is not found or has no trace events in the snapshot.', device)
        return False
    if device is not None:
        need_dump_devices = [device]
    dump_logger.info('Recognized need to dump devices %s.', need_dump_devices)
    dump_path = Path(dump_file)
    dump_path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(prefix=f".{dump_path.name}.", suffix=".tmp", dir=dump_path.parent)
    os.close(fd)
    temporary_path = Path(temporary_name)
    temporary_path.unlink()
    hooker = DumpEventHooker(str(temporary_path), need_dump_devices)
    try:
        for dump_device in need_dump_devices:
            dump_logger.info('Start to dump the snapshot to database for device %s.', dump_device)
            _, replayed = replay_snapshot(
                data,
                dump_device,
                hooker=hooker,
                allocator_hooker=hooker,
                _raw_frames=True,
            )
            if not replayed:
                dump_logger.error('Failed to dump the snapshot to database for device %s.', dump_device)
                return False
            dump_logger.info('Finished dump the snapshot to database for device %s.', dump_device)
            hooker.flush(dump_device)
        hooker.flush_callstacks()
        dump_logger.info(
            'Successfully dump the snapshot to database for devices %s, %s distinct callstacks.',
            need_dump_devices,
            len(hooker.callstacks),
        )
        hooker.close()
        os.replace(temporary_path, dump_path)
        return True
    finally:
        try:
            hooker.close(commit=False)
        finally:
            unlink_missing_ok(temporary_path)


def run_dump_to_db(
    snapshot_file: str,
    dump_dir: str = "",
    device: Union[int, None] = None,
    log_file: str = "",
) -> bool:
    resolved_dump_dir = dump_dir or str(Path(snapshot_file).parent)
    if log_file:
        set_global_log_file(log_file)

    return dump(
        snapshot_file,
        Path(resolved_dump_dir) / f"{Path(snapshot_file).name}.db",
        device,
    )
