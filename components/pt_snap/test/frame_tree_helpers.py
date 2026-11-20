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

"""Small explicit allocator lifetimes and structured stacks for contract tests."""

from pathlib import Path

from pt_snap_cli.snapshot.base import TraceEntry
from pt_snap_cli.snapshot.tools.adaptors.database import CallstackInterner, SnapshotDb


def create_frame_tree_db(path: Path) -> Path:
    root = {"filename": "train.py", "line": 1, "name": "train"}
    shared = {"filename": "model.py", "line": 20, "name": "forward"}
    a = {"filename": "tensor.py", "line": 30, "name": "a"}
    b = {"filename": "tensor.py", "line": 40, "name": "b"}
    other = {"filename": "other.py", "line": 1, "name": "other"}
    stacks = [
        [a, shared, root],
        [b, shared, root],
        [shared, root],
        [shared, shared, root],
        [a, other],
        [],
    ]
    db = SnapshotDb(str(path))
    interner = CallstackInterner(structured_frames=True)
    try:
        db.create_callstack_table(structured_frames=True)
        for device in (0, 1):
            db.create_trace_entry_table(device)
            db.create_block_table(device)
            for event_id, frames in enumerate(stacks, start=1):
                event = TraceEntry.from_dict({"action": "alloc", "frames": frames})
                stack_id = interner.intern(event)
                db.conn.execute(
                    f"INSERT INTO trace_entry_{device} (id, action, callstackId) VALUES (?, 4, ?)",
                    (event_id, stack_id),
                )
            db.conn.execute(f"INSERT INTO trace_entry_{device} (id, action) VALUES (8, 5)")
            db.conn.executemany(
                f"INSERT INTO block_{device} "
                "(id, size, requestedSize, allocEventId, freeEventId) VALUES (?, ?, ?, ?, ?)",
                [
                    (1, 100, 90, 1, 10),  # Pending free at 8; completed at 10.
                    (2, 200, 180, 2, -1),
                    (3, 50, 45, 3, None),  # Allocation ends at an internal node.
                    (4, 25, 20, 4, -1),  # Recursive frame, same caller identity twice.
                    (5, 75, 60, 5, -1),  # Same leaf under a different caller.
                    (6, 10, 9, 6, -1),  # Empty captured stack.
                    (7, 5, 4, 7, -1),  # Missing allocation event.
                    (8, 40, 32, -1, -1),
                    (9, 30, 24, -1, 10),
                    (10, 999, 900, 1, 8),  # Already completed at selected boundary.
                    (11, 888, 800, 9, -1),  # Future allocation.
                ],
            )
        db.get_callstack_table().insert_records(db.conn, interner.records())
        db.get_table_by_name("frame").insert_records(db.conn, interner.frame_records())
        db.get_table_by_name("callstack_frame").insert_records(db.conn, interner.stack_frame_records())
        db.get_table_by_name("callstack_frame_manifest").insert_records(db.conn, interner.stack_manifest_records())
        db.conn.commit()
    finally:
        db.conn.close()
    return path
