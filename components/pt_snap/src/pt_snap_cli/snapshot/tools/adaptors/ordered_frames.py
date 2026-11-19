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

"""Deduplicated, optional frame evidence independent of native text stack IDs."""

import json
import sqlite3
from typing import Dict, Tuple

from ...base import Frame, TraceEntry
from ...util.frame_json import _bounded_depth


class OrderedFrameWriter:
    def __init__(self, connection: sqlite3.Connection):
        self.connection = connection
        connection.executescript(
            "CREATE TABLE pt_snap_frame_value (id INTEGER PRIMARY KEY, frameJson TEXT);"
            "CREATE TABLE pt_snap_stack (stackId INTEGER PRIMARY KEY, frameCount INTEGER);"
            "CREATE TABLE pt_snap_stack_frame (stackId INTEGER, frameIndex INTEGER, frameId INTEGER,"
            " PRIMARY KEY(stackId,frameIndex));"
            "CREATE TABLE pt_snap_event_stack (eventId INTEGER PRIMARY KEY, stackId INTEGER);"
        )
        self.frames: Dict[str, int] = {}
        self.stacks: Dict[Tuple[int, ...], int] = {}
        self.containers: Dict[Tuple[int, ...], Tuple[object, int]] = {}

    def insert(self, event: TraceEntry) -> None:
        if event.idx is None or event.idx < 0:
            return
        frames = event.callstack_frames()
        key = tuple(map(id, frames))
        cached = self.containers.get(key)
        if cached is not None:
            stack_id = cached[1]
        else:
            try:
                encoded = [
                    json.dumps(
                        frame.to_dict() if isinstance(frame, Frame) else frame,
                        sort_keys=True,
                        ensure_ascii=True,
                        separators=(",", ":"),
                        allow_nan=False,
                    )
                    for frame in frames
                ]
                # Check the JSON shape readers see, including tuple-to-list
                # normalization, before writing any part of this optional stack.
                if not _bounded_depth([json.loads(value) for value in encoded]):
                    return
            except (ValueError, TypeError, RecursionError, OverflowError):
                # Optional evidence must not change acceptance of native text inputs.
                return
            ids = []
            for value in encoded:
                if value not in self.frames:
                    frame_id = len(self.frames)
                    self.frames[value] = frame_id
                    self.connection.execute("INSERT INTO pt_snap_frame_value VALUES (?,?)", (frame_id, value))
                ids.append(self.frames[value])
            stack = tuple(ids)
            if stack not in self.stacks:
                stack_id = len(self.stacks)
                self.stacks[stack] = stack_id
                self.connection.execute("INSERT INTO pt_snap_stack VALUES (?,?)", (stack_id, len(stack)))
                self.connection.executemany(
                    "INSERT INTO pt_snap_stack_frame VALUES (?,?,?)",
                    [(stack_id, index, frame_id) for index, frame_id in enumerate(stack)],
                )
            stack_id = self.stacks[stack]
            self.containers[key] = (frames, stack_id)
        self.connection.execute("INSERT INTO pt_snap_event_stack VALUES (?,?)", (event.idx, stack_id))
