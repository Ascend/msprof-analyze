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

import copy
import json
import math
import os
from pathlib import Path
from typing import List, Union

from typing_extensions import Literal

from ...base import DeviceSnapshot, Segment, TraceEntry
from ...simulate import SimulateHooker
from ...util import get_logger
from ...util.file_util import save_dict_to_pickle

dump_logger = get_logger("DUMP")


class SliceDumpHooker(SimulateHooker):
    """Split snapshots by event count while reconstructing boundary state."""

    def __init__(
        self,
        dump_dir: str,
        num_of_slices: int = 4,
        max_entries: int = 15000,
        dump_type: Literal["json", "pkl"] = "pkl",
        dump_progress_point=None,
    ):
        if dump_progress_point is None:
            dump_progress_point = [0.75, 0.5, 0.25]
        if num_of_slices <= 0:
            raise ValueError("The number of slices must be a positive integer and cannot be non-positive, at least 1.")
        if (not os.path.exists(dump_dir)) or not os.path.isdir(dump_dir) or not os.access(dump_dir, os.W_OK):
            raise ValueError(f"The dump dir {dump_dir} does not exist, is not a directory, or is not writable.")
        self.num_of_slices = num_of_slices
        self.max_entries = max_entries
        self.num_of_events = -1
        self.events_buffer = []
        self.prev_segments: Union[List[Segment], None] = None
        self.dump_dir = dump_dir
        self.dump_count = 0
        self.dump_type = dump_type
        self.dump_progress_point = dump_progress_point
        self.dump_progress_point.sort()

    def pre_undo_event(self, wait4undo_event: TraceEntry, current_snapshot: DeviceSnapshot) -> bool:
        if self.num_of_events == -1:
            self.num_of_events = len(current_snapshot.trace_entries)
            self._init_splitting_strategy()
            self.prev_segments = copy.deepcopy(current_snapshot.segments)
        current_num_of_events = len(current_snapshot.trace_entries)
        if self.dump_progress_point and current_num_of_events <= self.dump_progress_point[-1] * self.num_of_events:
            done_point = self.dump_progress_point.pop()
            dump_logger.info('Progressing: %s%%', (1 - done_point) * 100)
        return True

    def _init_splitting_strategy(self):
        if self.num_of_events == -1:
            raise RuntimeError("Cannot init splitting strategy before init total entries")
        if math.ceil(self.num_of_events / self.num_of_slices) > self.max_entries:
            dump_logger.warning(
                "The expected number of slices may leads the single snapshot file exceeds the "
                "max_entries limit.Splitting will be performed based on max_entries, or you may try "
                "increasing the max_entries value."
            )
        self.max_entries = min(math.ceil(self.num_of_events / self.num_of_slices), self.max_entries)
        self.num_of_slices = max(self.num_of_slices, math.ceil(self.num_of_events / self.max_entries))

    def post_undo_event(self, already_undo_event: TraceEntry, current_snapshot: DeviceSnapshot):
        self.events_buffer.append(already_undo_event)
        if self._is_need_dump(current_snapshot):
            self.dump(current_snapshot.device)
            self.prev_segments = copy.deepcopy(current_snapshot.segments)
            self.events_buffer.clear()
        return True

    def _is_need_dump(self, current_snapshot: DeviceSnapshot) -> bool:
        if len(self.events_buffer) >= self.max_entries:
            return True
        if self.events_buffer and not current_snapshot.trace_entries:
            return True
        return False

    def dump(self, device: int):
        slice_snapshot_name = self._get_dump_filename()
        prev_segments = self.prev_segments
        if prev_segments is None:
            raise RuntimeError("Cannot dump slice before capturing previous segments")
        slice_snapshot = DeviceSnapshot()
        slice_snapshot.device = device
        slice_snapshot.segments = prev_segments
        slice_snapshot.trace_entries = list(reversed(self.events_buffer))
        slice_snapshot_dict = slice_snapshot.to_dict(include_trace_ids=True)
        dump_logger.info('Start to dump snapshot slice: %s', slice_snapshot_name)
        if self.dump_type == "pkl":
            save_dict_to_pickle(slice_snapshot_dict, slice_snapshot_name, protocol=4)
        else:
            with open(slice_snapshot_name, "w", encoding="utf-8") as stream:
                json.dump(slice_snapshot_dict, stream)
        del self.prev_segments
        self.events_buffer.clear()
        self.dump_count += 1
        dump_logger.info('Successfully saved slice to file: %s', slice_snapshot_name)

    def _get_dump_filename(self) -> Path:
        slice_num = self.num_of_slices - self.dump_count
        entry_idx_start = max(self.num_of_events - (self.dump_count + 1) * self.max_entries + 1, 0)
        entry_idx_end = self.num_of_events - self.dump_count * self.max_entries
        return Path(
            os.path.join(
                self.dump_dir,
                f"slice_{slice_num}_entry_{entry_idx_start}_{entry_idx_end}.{self.dump_type}",
            )
        )
