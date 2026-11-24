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

"""Read the version-2 normalized frame extension without reconstructing text."""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Tuple, Union, cast

from typing_extensions import Protocol

from pt_snap_cli.core.common.frame_json import _bounded_depth, _finite_float, _invalid_constant
from pt_snap_cli.core.dataset.dataset_contract import _unique_object


class FrameBudget(Protocol):
    def remaining(self) -> Union[float, None]:
        pass


class FrameResolver(Protocol):
    _frame_schemas: Dict[Path, bool]

    @property
    def budget(self) -> FrameBudget:
        pass

    def read(self, path: Path, sql: str, values: Union[List[object], None] = None) -> List[Dict[str, object]]:
        pass


SCHEMA = {
    "pt_snap_frame_value": [("id", "INTEGER", 1), ("frameJson", "TEXT", 0)],
    "pt_snap_stack": [("stackId", "INTEGER", 1), ("frameCount", "INTEGER", 0)],
    "pt_snap_stack_frame": [
        ("stackId", "INTEGER", 1),
        ("frameIndex", "INTEGER", 2),
        ("frameId", "INTEGER", 0),
    ],
    "pt_snap_event_stack": [("eventId", "INTEGER", 1), ("stackId", "INTEGER", 0)],
}


def attach_frames(
    resolver: FrameResolver, path: Path, ids: List[int]
) -> Dict[int, Tuple[List[Dict[str, object]], str]]:
    result: Dict[int, Tuple[List[Dict[str, object]], str]] = {}
    batch_size = 256

    if path not in resolver._frame_schemas:
        valid = True
        for table, columns in SCHEMA.items():
            kind = resolver.read(path, "SELECT type FROM sqlite_master WHERE name=?", [table])
            schema = resolver.read(path, f'PRAGMA table_info("{table}")')
            if kind != [{"type": "table"}] or [(r["name"], r["type"], r["pk"]) for r in schema] != columns:
                valid = False
                break
        resolver._frame_schemas[path] = valid
    if not resolver._frame_schemas[path]:
        return result
    for start in range(0, len(ids), batch_size):
        batch = ids[start : start + batch_size]
        marks = ",".join("?" for _ in batch)
        coverage = resolver.read(
            path,
            "SELECT e.eventId,e.stackId,s.frameCount FROM pt_snap_event_stack e "
            f"LEFT JOIN pt_snap_stack s ON s.stackId=e.stackId WHERE e.eventId IN ({marks})",  # nosec B608 # Only placeholder count varies; data values are bound separately.
            list(batch),
        )
        entries = resolver.read(
            path,
            "SELECT sf.stackId,sf.frameIndex,sf.frameId,f.frameJson FROM pt_snap_stack_frame sf "
            "LEFT JOIN pt_snap_frame_value f ON f.id=sf.frameId "
            f"WHERE sf.stackId IN (SELECT stackId FROM pt_snap_event_stack WHERE eventId IN ({marks})) "
            "ORDER BY sf.stackId,sf.frameIndex",  # nosec B608 # Only placeholder count varies; data values are bound separately.
            list(batch),
        )
        grouped: Dict[int, List[Dict[str, object]]] = defaultdict(list)
        for row in entries:
            grouped[cast(int, row["stackId"])].append(row)
        decoded_stacks: Dict[int, Union[Tuple[List[Dict[str, object]], str], None]] = {}
        for row in coverage:
            resolver.budget.remaining()
            event, stack, count = row["eventId"], row["stackId"], row["frameCount"]
            # The SQL IN clause already restricts eventId to this batch. Do not
            # scan the full shard's allocation list for each returned event.
            # pylint: disable-next=unidiomatic-typecheck  # Reject bool/subclasses: the contract requires exact scalar types.
            if type(stack) is not int or type(count) is not int or count < 0:
                continue
            stack = cast(int, stack)
            if stack not in decoded_stacks:
                decoded_stacks[stack] = None
                frames = grouped[stack]
                if len(frames) != count or any(
                    # pylint: disable-next=unidiomatic-typecheck  # Reject bool/subclasses: the contract requires exact scalar types.
                    type(frame["frameIndex"]) is not int
                    or frame["frameIndex"] != index
                    # pylint: disable-next=unidiomatic-typecheck  # Reject bool/subclasses: the contract requires exact scalar types.
                    or type(frame["frameId"]) is not int
                    or not isinstance(frame["frameJson"], str)
                    for index, frame in enumerate(frames)
                ):
                    continue
                try:
                    decoded = [
                        json.loads(
                            cast(str, frame["frameJson"]),
                            object_pairs_hook=_unique_object,
                            parse_constant=_invalid_constant,
                            parse_float=_finite_float,
                        )
                        for frame in frames
                    ]
                    if not all(isinstance(frame, dict) for frame in decoded) or not _bounded_depth(decoded):
                        continue
                    canonical = json.dumps(
                        decoded,
                        sort_keys=True,
                        ensure_ascii=True,
                        separators=(",", ":"),
                        allow_nan=False,
                    )
                    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
                except (ValueError, TypeError, RecursionError, OverflowError):
                    continue
                decoded_stacks[stack] = (decoded, digest)
            value = decoded_stacks[stack]
            if value is not None:
                decoded, digest = value
                result[cast(int, event)] = (decoded, digest)
    return result
