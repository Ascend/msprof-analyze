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

"""Real query-stage barriers shared by thread, spawned-process and signal tests.

Hooks observe a completed SQLite read/insert, then block on explicit IPC. They
never replace query results, install signal handlers, or perform product cleanup.
"""

import os
import sys
import threading
import traceback
from contextlib import ExitStack, contextmanager, redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from pt_snap_cli.api import QueryLimits, SnapshotAnalyzer
from pt_snap_cli.core.dataset.lifecycle import dataset_lifecycle_scratch as scratch
from pt_snap_cli.core.dataset.lifecycle import dataset_lifecycle_sql as sql
from pt_snap_cli.core.dataset.lifecycle.dataset_lifecycle_connection import _AttachedSources

WAIT_SECONDS = 30
QUERY_PARAMS = {"order_by": "id", "order_dir": "ASC", "limit": -1}
ISOLATED_ENV = (
    "PT_SNAP_DB_PATH",
    "PT_SNAP_DATASET_CACHE",
    "PT_SNAP_QUERY_TIMEOUT",
    "PT_SNAP_MAX_WORK_ROWS",
    "PT_SNAP_MAX_WORK_BYTES",
    "PT_SNAP_MAX_SCRATCH_DB_BYTES",
)


@contextmanager
def lifecycle_stage(route, scratch_parent, reached):
    original_read = _AttachedSources.read
    original_execute = scratch._ScratchSources.execute
    original_directory = scratch.tempfile.TemporaryDirectory

    def observe(database):
        if getattr(database, "_test_stage_reached", False):
            return
        database._test_stage_reached = True
        evidence = {"pid": os.getpid(), "thread": threading.get_ident(), "route": route}
        if route == "scratch":
            # These are actual product-created bytes, not a synthetic ready file.
            cursor = database.connection.execute("PRAGMA database_list")
            try:
                evidence["database"] = next(row[2] for row in cursor if row[1] == "main")
            finally:
                cursor.close()
            cursor = database.connection.execute("SELECT COUNT(*) FROM lifecycle_state")
            try:
                evidence["inserted_rows"] = cursor.fetchone()[0]
            finally:
                cursor.close()
        reached(evidence)

    def read(database, statement, values=None):
        result = original_read(database, statement, values)
        if route == "attach" and statement.startswith("WITH observations AS"):
            observe(database)
        return result

    def execute(database, statement, values=()):
        result = original_execute(database, statement, values)
        if route == "scratch" and statement.startswith("INSERT INTO lifecycle_state"):
            observe(database)
        return result

    def directory(*args, **kwargs):
        return original_directory(*args, dir=scratch_parent, **kwargs)

    with ExitStack() as stack:
        stack.enter_context(patch.object(_AttachedSources, "read", read))
        stack.enter_context(patch.object(scratch._ScratchSources, "execute", execute))
        stack.enter_context(patch.object(scratch.tempfile, "TemporaryDirectory", directory))
        if route == "scratch":
            stack.enter_context(patch.object(sql, "_ATTACHED_OBSERVATION_LIMIT", 0))
        yield


def read_query(root, route):
    with SnapshotAnalyzer(root) as analyzer:
        return analyzer.execute_query(
            "block",
            QUERY_PARAMS,
            exact_total=True,
            query_limits=QueryLimits(max_scratch_db_bytes=0 if route == "attach" else 512 * 1024**2),
        )


def query_worker(root, route, output):
    try:
        output.put(("result", read_query(root, route)))
    except BaseException:
        output.put(("error", traceback.format_exc()))


def process_reader(root, route, scratch_parent, ready, release, output):
    def reached(evidence):
        output.put(("stage", evidence))
        ready.wait(WAIT_SECONDS)
        if not release.wait(WAIT_SECONDS):
            raise TimeoutError("Parent did not release the query-stage barrier")

    with lifecycle_stage(route, scratch_parent, reached):
        query_worker(root, route, output)


def cli_at_scratch_stage(root, scratch_parent, channel, stdout_path, stderr_path):
    """Call the real console entry point with Python's original signal behavior."""
    from pt_snap_cli.cli import _safe_call

    def reached(evidence):
        channel.send(evidence)
        # Parent either permits completion or sends an actual operating-system
        # signal. No test-created handler turns SIGTERM into a Python exception.
        if not channel.poll(WAIT_SECONDS):
            raise TimeoutError("Parent did not release or signal the CLI")
        assert channel.recv() == "continue"

    sys.argv = [
        "pt-snap",
        "query",
        str(root),
        "--template-use",
        "block",
        "--params",
        '{"limit":5}',
        "--json",
    ]
    with (
        Path(stdout_path).open("w") as stdout,
        Path(stderr_path).open("w") as stderr,
        redirect_stdout(stdout),
        redirect_stderr(stderr),
        lifecycle_stage("scratch", scratch_parent, reached),
    ):
        try:
            raise SystemExit(_safe_call())
        finally:
            channel.close()
