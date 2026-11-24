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

"""Inspectable lifecycle workload and real-CLI fault harness for #252.

This is synthetic SQL evidence, not producer/exporter or live-capture evidence.
One dynamic lifecycle has alloc/request/complete events; only the final one stays
live. A static carry-in is repeated in every shard. Membership and expected
answers are arithmetic, independent of production reducers and other fixtures.
"""

import json
import os
import sqlite3
import subprocess
import sys
from contextlib import ExitStack, closing, contextmanager
from pathlib import Path
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[1]
ENV_NAMES = (
    "PT_SNAP_DB_PATH",
    "PT_SNAP_QUERY_TIMEOUT",
    "PT_SNAP_MAX_WORK_ROWS",
    "PT_SNAP_MAX_WORK_BYTES",
    "PT_SNAP_MAX_SCRATCH_DB_BYTES",
)
SCHEMA = """
CREATE TABLE dictionary ("table" TEXT,"column" TEXT,"key" TEXT,"value" TEXT);
CREATE TABLE trace_entry_0 (id INTEGER PRIMARY KEY, action INTEGER, address INTEGER,
 size INTEGER, stream INTEGER, allocated INTEGER, active INTEGER, reserved INTEGER, callstack TEXT);
CREATE TABLE block_0 (id INTEGER PRIMARY KEY, address INTEGER, size INTEGER,
 requestedSize INTEGER, state INTEGER, allocEventId INTEGER, freeEventId INTEGER);
"""


def lifecycle_dataset(root, lifecycles, shards=4):
    count = 3 * lifecycles - 2
    capacity = (count + shards - 1) // shards
    # Make a real allocation/completion cross a boundary rather than arranging
    # every shard at an already-completed lifetime boundary.
    if capacity % 3 == 0:
        capacity += 1
    assert (count + capacity - 1) // capacity == shards
    (root / "device_0").mkdir(parents=True)
    records = []
    for index, low in enumerate(range(0, count, capacity)):
        high = min(count, low + capacity) - 1
        file = f"device_0/slice_{index:05d}.db"
        with closing(sqlite3.connect(root / file)) as conn, conn:
            conn.executescript(SCHEMA)
            actions = (
                "segment_map",
                "segment_unmap",
                "segment_alloc",
                "segment_free",
                "alloc",
                "free_requested",
                "free_completed",
                "workspace_snapshot",
            )
            conn.executemany(
                "INSERT INTO dictionary VALUES (?,?,?,?)",
                [("trace_entry_0", "action", str(i), name) for i, name in enumerate(actions)]
                + [
                    ("block_0", "state", str(i), name)
                    for i, name in [
                        (-1, "inactive"),
                        (0, "active_pending_free"),
                        (1, "active_allocated"),
                    ]
                ],
            )
            conn.executemany(
                "INSERT INTO trace_entry_0 VALUES (?,?,?,?,?,?,?,?,?)",
                (
                    (
                        i,
                        4 + i % 3,
                        1000,
                        16,
                        0,
                        64 + 16 * (i % 3 == 0),
                        64 + 16 * (i % 3 != 2),
                        4096,
                        "allocate" if i % 3 == 0 else "free",
                    )
                    for i in range(low, high + 1)
                ),
            )
            conn.execute("INSERT INTO trace_entry_0 VALUES (-1,2,0,4096,0,999999,999999,999999,'boundary')")
            conn.execute("INSERT INTO block_0 VALUES (-1,2000,64,64,1,-1,-1)")
            conn.executemany(
                "INSERT INTO block_0 VALUES (?,?,?,?,?,?,?)",
                (
                    (a, 1000, 16, 16, int(a + 1 >= low), a, a + 2 if a + 2 < count else -1)
                    for a in range(low - low % 3, high + 1, 3)
                ),
            )
        records.append({"index": index, "startEventId": low, "endEventId": high, "file": file, "ready": True})
    (root / "manifest.json").write_text(
        json.dumps(
            {
                "schemaVersion": 1,
                "status": "complete",
                "sourceFile": "/synthetic/no-pickle",
                "cacheHash": "",
                "eventsPerSlice": capacity,
                "devices": {
                    "0": {
                        "eventCount": count,
                        "sliceCount": shards,
                        "readySlices": list(range(shards)),
                        "slices": records,
                    }
                },
            }
        )
    )
    return root


def child_environment(tmp_path):
    env = os.environ.copy()
    for key in (*ENV_NAMES, "PYTHONHOME"):
        env.pop(key, None)
    env.update(
        HOME=str(tmp_path),
        USERPROFILE=str(tmp_path),
        NO_COLOR="1",
        TERM="dumb",
        PYTHONPATH=os.pathsep.join((str(REPO / "src"), str(REPO))),
    )
    return env


def run_cli(tmp_path, args, env=None, fault=None, evidence=None):
    command = [
        sys.executable,
        "-c",
        "from pt_snap_cli.cli import _safe_call; raise SystemExit(_safe_call())",
    ]
    if fault is not None:
        command = [sys.executable, "-m", "test.dataset_failure_support", fault, str(evidence)]
    return subprocess.run(
        command + args,
        cwd=tmp_path,
        env=env or child_environment(tmp_path),
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )


@contextmanager
def fault_hooks(kind, evidence):
    """Fault real execution boundaries; never fabricate rows or query results."""
    from pt_snap_cli.core.dataset.lifecycle import dataset_lifecycle_scratch as scratch
    from pt_snap_cli.core.dataset.lifecycle import dataset_lifecycle_sql as sql
    from pt_snap_cli.core.dataset.lifecycle.dataset_lifecycle_connection import _AttachedSources

    connections, directories = [], []
    events = []
    original_enter = _AttachedSources.__enter__
    original_init = _AttachedSources.__init__
    original_execute = scratch._ScratchSources.execute
    original_directory = scratch.tempfile.TemporaryDirectory
    original_open = scratch.os.open

    def init(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        connections.append(self.connection)

    def enter(database):
        if kind == "attach":
            attempts = 0

            def authorize(action, first, second, name, trigger):
                nonlocal attempts
                if action == sqlite3.SQLITE_ATTACH:
                    attempts += 1
                    events.append(f"attach_attempt_{attempts}")
                    if attempts == 2:
                        return sqlite3.SQLITE_DENY
                return sqlite3.SQLITE_OK

            database.connection.set_authorizer(authorize)
        return original_enter(database)

    def directory(*args, **kwargs):
        result = original_directory(*args, **kwargs)
        directories.append(Path(result.name))
        events.append("scratch_created")
        return result

    def open_file(path, *args, **kwargs):
        if kind == "scratch_io" and Path(path).name == "derived.db":
            events.append("scratch_open_fault")
            raise OSError("injected scratch open failure")
        return original_open(path, *args, **kwargs)

    def execute(database, statement, values=()):
        result = original_execute(database, statement, values)
        if kind == "timeout" and statement.startswith("INSERT INTO lifecycle_state"):
            events.append("reduction_insert_completed")
            # Expire the real operation deadline after real scratch work. No
            # sleeps, mocked error object, or replacement query result is needed.
            database.sources.budget.started -= database.sources.budget.timeout_s + 1
        return result

    with ExitStack() as patches:
        for owner, name, replacement in (
            (_AttachedSources, "__init__", init),
            (_AttachedSources, "__enter__", enter),
            (scratch._ScratchSources, "execute", execute),
            (scratch.tempfile, "TemporaryDirectory", directory),
            (scratch.os, "open", open_file),
        ):
            patches.enter_context(patch.object(owner, name, replacement))
        if kind in ("timeout", "scratch_io", "scratch_space"):
            patches.enter_context(patch.object(sql, "_ATTACHED_OBSERVATION_LIMIT", 0))
        try:
            yield
        finally:
            closed = []
            for connection in connections:
                try:
                    connection.execute("SELECT 1").close()
                except sqlite3.ProgrammingError:
                    closed.append(True)
                else:
                    closed.append(False)
            evidence.update(
                events=events,
                connections_closed=closed,
                scratch_removed=[not p.exists() for p in directories],
            )


if __name__ == "__main__":
    fault, destination = sys.argv[1:3]
    sys.argv = ["pt-snap", *sys.argv[3:]]
    observation = {}
    try:
        with fault_hooks(fault, observation):
            from pt_snap_cli.cli import _safe_call

            raise SystemExit(_safe_call())
    finally:
        Path(destination).write_text(json.dumps(observation))
