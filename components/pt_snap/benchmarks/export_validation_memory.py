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

"""Measure only msinsight export preflight in fresh subprocesses (#241/#253).

Build synthetic finalized SQLite shards first, then invoke ``measure`` in a NEW
process for each metric. No pickle load, replay, shard construction, conversion
or publication is included in the measurement. tracemalloc is Python allocator
peak only. Linux RSS uses /proc/self/status VmHWM for the current address space,
with VmRSS snapshots alongside it. ru_maxrss can retain pre-exec parent history,
so it is reported separately and never used for the bound. The VmHWM increment
is relative to the post-import baseline, not a sampled instantaneous phase peak.

Example (from the repository root, with PYTHONPATH=src):
  python benchmarks/export_validation_memory.py build /tmp/export-check --events 1000000
  python benchmarks/export_validation_memory.py measure /tmp/export-check --metric python
  python benchmarks/export_validation_memory.py measure /tmp/export-check --metric rss
"""

from __future__ import annotations

import argparse
import gc
import json
import platform
import sqlite3
import sys
import time
import tracemalloc
from contextlib import closing
from pathlib import Path

from pt_snap_cli.core.importing.msinsight_export import DEFAULT_CAPACITY, _validate_shards
from pt_snap_cli.core.splitting.sharded_replay_service import ShardedReplayResult
from pt_snap_cli.snapshot.tools.adaptors.sharded_replay import ReplaySlice


def build(root: Path, events: int) -> dict:
    """Stream synthetic rows; do not retain an event-sized list during setup."""
    root.mkdir()
    (root / "device_0").mkdir()
    slices = []
    for index, low in enumerate(range(0, events, DEFAULT_CAPACITY)):
        high = min(events, low + DEFAULT_CAPACITY) - 1
        path = root / f"device_0/slice_{index:05d}.db"
        # pylint: disable-next=confusing-with-statement  # closing() owns lifetime; the SQLite context owns the transaction.
        with closing(sqlite3.connect(path)) as conn, conn:
            conn.execute(
                "CREATE TABLE trace_entry_0 (id INTEGER PRIMARY KEY, action INTEGER, "
                "address INTEGER, size INTEGER, stream INTEGER, allocated INTEGER, "
                "active INTEGER, reserved INTEGER, callstackId INTEGER)"
            )
            conn.executemany(
                "INSERT INTO trace_entry_0 VALUES (?,7,0,0,0,0,0,0,0)",
                ((event,) for event in range(low, high + 1)),
            )
            conn.execute("INSERT INTO trace_entry_0 VALUES (-1,2,0,0,0,0,0,0,0)")
            count = conn.execute("SELECT COUNT(*) FROM trace_entry_0 WHERE id>=0").fetchone()[0]
            assert count == high - low + 1  # nosec B101 # Benchmark/acceptance assertion, not an input security check.
        slices.append({"index": index, "low": low, "high": high, "file": str(path.relative_to(root))})
    result = {"events": events, "capacity": DEFAULT_CAPACITY, "slices": slices}
    (root / "probe.json").write_text(json.dumps(result), encoding="utf-8")
    return result


def _parse_linux_rss(status: str) -> dict[str, int]:
    """Read Linux's current-address-space RSS/high-water values, in bytes."""
    values = {}
    for line in status.splitlines():
        fields = line.split()
        if fields and fields[0] in ("VmRSS:", "VmHWM:"):
            if len(fields) != 3 or fields[2] != "kB" or not fields[1].isdigit():
                raise RuntimeError(f"Unsupported /proc RSS record: {line!r}")
            key = fields[0].removesuffix(":")
            if key in values:
                raise RuntimeError(f"Duplicate /proc RSS record: {key}")
            values[key] = int(fields[1]) * 1024
    if set(values) != {"VmRSS", "VmHWM"}:
        raise RuntimeError("RSS probe requires Linux /proc/self/status VmRSS and VmHWM")
    return values


def _linux_rss_snapshot() -> dict[str, int]:
    if not sys.platform.startswith("linux"):
        raise RuntimeError("RSS probe requires Linux /proc; scheduled acceptance uses Ubuntu")
    return _parse_linux_rss(Path("/proc/self/status").read_text(encoding="utf-8"))


def measure(root: Path, metric: str) -> dict:
    specification = json.loads((root / "probe.json").read_text())
    items = tuple(
        ReplaySlice(0, row["index"], row["low"], row["high"], row["low"], row["high"], root / row["file"])
        for row in specification["slices"]
    )
    staged = ShardedReplayResult(root, items, ())
    # Import and setup high-water are separate from the measured validation.
    gc.collect()
    evidence = {
        "phase": "msinsight_export._validate_shards",
        "events": specification["events"],
        "shards": len(items),
        "events_per_slice": specification["capacity"],
        "metric": metric,
        "python": platform.python_version(),
        "platform": platform.platform(),
        "tracemalloc_enabled": metric == "python",
    }
    if metric == "python":
        tracemalloc.start()
        started = time.perf_counter()
        _validate_shards(staged)
        evidence["validation_seconds"] = time.perf_counter() - started
        evidence["python_current_bytes"], evidence["python_peak_bytes"] = tracemalloc.get_traced_memory()
        tracemalloc.stop()
    else:
        before = _linux_rss_snapshot()
        import resource

        historical_before = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024
        started = time.perf_counter()
        _validate_shards(staged)
        evidence["validation_seconds"] = time.perf_counter() - started
        after = _linux_rss_snapshot()
        historical_after = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024
        evidence.update(
            rss_source="Linux /proc/self/status: current-address-space VmHWM and VmRSS",
            rss_current_before_bytes=before["VmRSS"],
            rss_current_after_bytes=after["VmRSS"],
            rss_high_water_before_bytes=before["VmHWM"],
            rss_high_water_after_bytes=after["VmHWM"],
            rss_high_water_increase_bytes=max(0, after["VmHWM"] - before["VmHWM"]),
            ru_maxrss_before_bytes=historical_before,
            ru_maxrss_after_bytes=historical_after,
            ru_maxrss_scope="diagnostic only; may retain pre-exec parent high-water history",
        )
    return evidence


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("build", "measure"))
    parser.add_argument("directory", type=Path)
    parser.add_argument("--events", type=int, default=1_000_000)
    parser.add_argument("--metric", choices=("python", "rss"), default="python")
    args = parser.parse_args()
    if args.events < 1:
        parser.error("--events must be positive")
    root = args.directory.resolve()
    evidence = build(root, args.events) if args.operation == "build" else measure(root, args.metric)
    print(json.dumps(evidence, sort_keys=True))


if __name__ == "__main__":
    main()
