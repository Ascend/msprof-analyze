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

"""Subprocess instrumentation around the real console entry point, never CliRunner.

Count bytes returned by hash reads (logical I/O, not physical disk traffic).
The unmodified resolver, report composition, hash implementation and Typer CLI
still run. Audit events observe shard opens even outside Path.open.
"""

import json
import os
import sqlite3
import sys
from contextlib import closing
from pathlib import Path, PurePath

from pt_snap_cli.cli import _safe_call
from pt_snap_cli.core.analysis import query_service as queries
from pt_snap_cli.core.dataset import dataset_files, dataset_resolver, native_dataset_contract


def relative_evidence_path(path: PurePath, root: PurePath) -> str:
    """Serialize relative evidence identities with platform-independent separators."""
    return path.relative_to(root).as_posix()


def main():
    evidence_path, dataset, mutate_stage, *arguments = sys.argv[1:]
    root = Path(dataset)
    phase = ["cli"]
    active = []
    pinned = []
    evidence = {"hash_reads": [], "guards": 0, "sqlite_opens": 0, "member_opens": 0}
    real_hash, real_open = dataset_files.hash_file, Path.open
    inspect = dataset_resolver.DatasetResolver.inspect
    guard = dataset_resolver.ResolvedDataset.require_unchanged

    def audit(event, args):
        if event == "sqlite3.connect":
            evidence["sqlite_opens"] += 1
        if event == "open" and isinstance(args[0], (str, bytes)):
            path = Path(os.fsdecode(args[0]))
            if path.suffix == ".db" and path.is_relative_to(root):
                evidence["member_opens"] += 1

    class Reader:
        def __init__(self, source, record):
            self.source, self.record = source, record

        def __enter__(self):
            self.source.__enter__()
            return self

        def __exit__(self, *args):
            return self.source.__exit__(*args)

        def read(self, size):
            data = self.source.read(size)
            self.record["bytes_read"] += len(data)
            return data

    def opened(path, *args, **kwargs):
        source = real_open(path, *args, **kwargs)
        if active and path == active[-1][0]:
            return Reader(source, active[-1][1])
        return source

    def hashed(path, **kwargs):
        record = {
            "path": relative_evidence_path(path, root),
            "phase": phase[-1],
            "bytes_read": 0,
            "completed": False,
        }
        evidence["hash_reads"].append(record)
        active.append((path, record))
        try:
            value = real_hash(path, **kwargs)
            record["completed"] = True
            return value
        finally:
            active.pop()

    def inspected(self, *args, **kwargs):
        phase.append("inspect")
        try:
            resolved = inspect(self, *args, **kwargs)
            pinned.append(resolved)
            return resolved
        finally:
            phase.pop()

    def guarded(self, *args, **kwargs):
        evidence["guards"] += 1
        phase.append(f"guard{evidence['guards']}")
        try:
            return guard(self, *args, **kwargs)
        finally:
            phase.pop()

    if mutate_stage != "none":
        name = "global_query" if mutate_stage == "peak" else "event_attribution"
        original_query = getattr(queries, name)

        def changed(*args, **kwargs):
            result = original_query(*args, **kwargs)
            # Alter an unselected device after a real successful query. Hide all
            # generation tokens so only the retained strong content guard helps.
            target = root / "device_1/slice_00000.db"
            before = target.stat()
            with closing(sqlite3.connect(target)) as conn, conn:
                conn.execute("UPDATE trace_entry_1 SET reserved=reserved+1 WHERE id>=0")
            os.utime(target, ns=(before.st_atime_ns, before.st_mtime_ns))
            assert target.stat().st_size == before.st_size
            dataset_resolver._generation = lambda *a: pinned[-1].generation
            evidence["mutated"] = relative_evidence_path(target, root)
            return result

        setattr(queries, name, changed)

    Path.open = opened
    dataset_files.hash_file = hashed
    dataset_resolver._hash_file = hashed
    native_dataset_contract._hash_file = hashed
    dataset_resolver.DatasetResolver.inspect = inspected
    dataset_resolver.ResolvedDataset.require_unchanged = guarded
    sys.addaudithook(audit)
    sys.argv = ["pt-snap", *arguments]
    try:
        return _safe_call()
    finally:
        Path(evidence_path).write_text(json.dumps(evidence), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
