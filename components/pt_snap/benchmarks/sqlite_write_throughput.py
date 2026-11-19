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

"""Compare default SQLite writes with the SnapshotDb import configuration.

Run with ``PYTHONPATH=src python benchmarks/sqlite_write_throughput.py``.
"""

from __future__ import annotations

import argparse
import tempfile
import time
from contextlib import ExitStack
from pathlib import Path

from pt_snap_cli.snapshot.tools.adaptors.database.snapshot_db import SnapshotDb
from pt_snap_cli.snapshot.util.sqlite_meta import SqliteDB


def measure(db: SqliteDB, rows: int, batch_size: int) -> float:
    db.conn.execute("CREATE TABLE benchmark (id INTEGER, payload TEXT)")
    started = time.perf_counter()
    for offset in range(0, rows, batch_size):
        batch_end = min(offset + batch_size, rows)
        db.conn.executemany(
            "INSERT INTO benchmark VALUES (?, ?)",
            ((index, "x" * 256) for index in range(offset, batch_end)),
        )
        db.conn.commit()
    return time.perf_counter() - started


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rows", type=int, default=100_000)
    parser.add_argument("--batch-size", type=int, default=1_000)
    args = parser.parse_args()

    with tempfile.TemporaryDirectory() as tmp_dir, ExitStack() as stack:
        root = Path(tmp_dir)
        baseline = SqliteDB(str(root / "baseline.db"))
        stack.callback(baseline.conn.close)
        optimized = SnapshotDb(str(root / "optimized.db"))
        stack.callback(optimized.conn.close)
        baseline_seconds = measure(baseline, args.rows, args.batch_size)
        optimized_seconds = measure(optimized, args.rows, args.batch_size)

    print(f"default:   {baseline_seconds:.3f}s")
    print(f"optimized: {optimized_seconds:.3f}s")
    print(f"speedup:   {baseline_seconds / optimized_seconds:.2f}x")


if __name__ == "__main__":
    main()
