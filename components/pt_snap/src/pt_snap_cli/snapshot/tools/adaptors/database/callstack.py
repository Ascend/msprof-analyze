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

from typing import Any, Dict, List, Mapping, Sequence, Tuple, Union

from ....base import Frame, TraceEntry
from .defs import CallstackFieldDefs


class CallstackInterner:
    """Intern callstacks by text, or opt into standalone structured identity.

    Native writers retain one id per distinct rendered text. Standalone v3
    writers explicitly use original frame fields and order instead, since text
    can contain delimiters that make different frame sequences look identical.
    Identity fast paths retain frame containers to prevent object-id reuse.
    """

    def __init__(self, *, structured_frames: bool = False) -> None:
        self._structured_frames: bool = structured_frames
        self._by_frames: Dict[Tuple[int, ...], Tuple[object, int]] = {}
        self._by_text: Dict[str, int] = {}
        self._by_stack: Dict[Tuple[int, ...], int] = {}
        self._by_frame: Dict[Tuple[str, int, str], int] = {}
        self._frames: List[Dict[str, object]] = []
        self._stacks: List[Tuple[int, ...]] = []
        self._texts: List[str] = []

    def intern(self, event: TraceEntry) -> int:
        """Return the callstack id for ``event``, rendering text only on a miss."""
        frames = event.callstack_frames()
        frame_key = tuple(map(id, frames))
        by_frames = self._by_frames.get(frame_key)
        if by_frames is not None:
            return by_frames[1]
        if self._structured_frames:
            callstack_id = self._intern_structured(event, frames)
        else:
            text = event.get_callstack()
            existing = self._by_text.get(text)
            if existing is None:
                callstack_id = len(self._texts)
                self._texts.append(text)
                self._by_text[text] = callstack_id
            else:
                callstack_id = existing
        self._by_frames[frame_key] = (frames, callstack_id)
        return callstack_id

    @staticmethod
    def _frame_key(frame: Union[Frame, Mapping[str, object]]) -> Tuple[str, int, str]:
        filename, line, name = (
            (frame.filename, frame.line, frame.name)
            if isinstance(frame, Frame)
            else (frame["filename"], frame["line"], frame["name"])
        )
        # SQLite INTEGER affinity coerces bool/float/string values. Reject those
        # here rather than lose their types or conflate True, 1 and 1.0 as keys.
        # Keep this stricter standalone-v3 contract out of native text imports.
        # pylint: disable-next=unidiomatic-typecheck  # Exact integer IDs reject bool and subclasses.
        if not isinstance(filename, str) or type(line) is not int or not isinstance(name, str):
            raise ValueError("Structured frames require string filename/name and integer line (not bool).")
        return filename, line, name

    def _intern_structured(self, event: TraceEntry, frames: Sequence[Union[Frame, Mapping[str, object]]]) -> int:
        keys = [self._frame_key(frame) for frame in frames]
        frame_ids: List[int] = []
        for key in keys:
            frame_id = self._by_frame.get(key)
            if frame_id is None:
                frame_id = len(self._frames)
                self._by_frame[key] = frame_id
                self._frames.append({"id": frame_id, "filename": key[0], "line": key[1], "name": key[2]})
            frame_ids.append(frame_id)
        stack = tuple(frame_ids)
        existing = self._by_stack.get(stack)
        if existing is not None:
            return existing
        callstack_id = len(self._texts)
        self._texts.append(event.get_callstack())
        self._stacks.append(stack)
        self._by_stack[stack] = callstack_id
        return callstack_id

    def records(self) -> List[Dict[str, Any]]:
        """Return one record per distinct callstack, ordered by id."""
        return [
            {CallstackFieldDefs.ID: callstack_id, CallstackFieldDefs.CALLSTACK: text}
            for callstack_id, text in enumerate(self._texts)
        ]

    def __len__(self) -> int:
        return len(self._texts)

    def frame_records(self) -> List[Dict[str, object]]:
        """Return deduplicated original frame fields for a structured interner."""
        return self._frames.copy()

    def stack_frame_records(self) -> List[Dict[str, int]]:
        """Return original-order references, including repeated recursive frames."""
        return [
            {"callstackId": stack_id, "position": position, "frameId": frame_id}
            for stack_id, stack in enumerate(self._stacks)
            for position, frame_id in enumerate(stack)
        ]

    def stack_manifest_records(self) -> List[Dict[str, int]]:
        """Attest every captured stack's size, including genuinely empty stacks."""
        return [{"callstackId": stack_id, "frameCount": len(stack)} for stack_id, stack in enumerate(self._stacks)]
