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

"""Synthetic text-attribution capacity/differential gate; no pickle or producer.

Default: 1.5M events, three 500k-event shards, 200k active blocks. Uses private
TemporaryDirectory storage and deletes it on success/failure. Both published v1
and native-v2 schemas are supported. Timing includes normal validation/hashing;
work bytes measure serialized fetched/output values, not process RSS.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import tempfile
import time
from contextlib import closing
from dataclasses import asdict
from pathlib import Path

from pt_snap_cli.core.dataset.dataset_contract import ACTION_NAMES, BLOCK_STATES
from pt_snap_cli.core.dataset.dataset_sources import QueryBudget
from pt_snap_cli.core.common.errors import QueryExecutionError
from pt_snap_cli.core.common.models import ImportMetadata
from pt_snap_cli.core.dataset.native_dataset_contract import NATIVE_FORMAT, cache_identity
from pt_snap_cli.core.analysis.query_service import QueryService

SCHEMA = """CREATE TABLE dictionary ("table" TEXT,"column" TEXT,"key" TEXT,"value" TEXT);
CREATE TABLE trace_entry_0 (id INTEGER PRIMARY KEY,action INTEGER,address INTEGER,
size INTEGER,stream INTEGER,allocated INTEGER,active INTEGER,reserved INTEGER,callstack TEXT);
CREATE TABLE block_0 (id INTEGER PRIMARY KEY,address INTEGER,size INTEGER,
requestedSize INTEGER,state INTEGER,allocEventId INTEGER,freeEventId INTEGER);"""


def digest(path):
    with path.open("rb") as file:
        value = hashlib.sha256()
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def inventory(root):
    return {str(path.relative_to(root)): digest(path) for path in root.rglob("*") if path.is_file()}


def build_case(root: Path, capacity=500_000, active=200_000, groups=32, layout="v1"):
    """Build a bounded deterministic dataset plus full-text standalone reference.

    Half the allocations are in each of the first two owners. Completed frees
    are in the third, after the target. Native local stack IDs deliberately name
    different texts in different shards; global grouping must use their full text.
    """
    if not (2 <= active <= capacity <= 500_000 and active % 2 == 0 and 1 <= groups <= active):
        raise ValueError("Require even 2<=active<=capacity<=500000 and 1<=groups<=active")
    root.mkdir()
    dataset = root / "dataset"
    (dataset / "device_0").mkdir(parents=True)
    half = active // 2

    def occupied(count):
        return 8 * (6 * (count // 3) + (count % 3) * (count % 3 + 1) // 2)

    metadata = asdict(
        ImportMetadata(
            1,
            2,
            "0" * 64,
            0,
            "synthetic.sql",
            None,
            "synthetic-capacity-benchmark",
            "1",
            "2026-10-11T00:00:00+00:00",
        )
    )
    records = []
    for index in range(3):
        lo, hi = index * capacity, (index + 1) * capacity - 1
        file = f"device_0/slice_{index:05d}.db"
        path = dataset / file
        # pylint: disable-next=confusing-with-statement  # closing() owns lifetime; the SQLite context owns the transaction.
        with closing(sqlite3.connect(path)) as conn, conn:
            conn.executescript(SCHEMA if layout == "v1" else SCHEMA.replace("callstack TEXT", "callstackId INTEGER"))
            conn.executemany(
                "INSERT INTO dictionary VALUES (?,?,?,?)",
                [
                    ("trace_entry_0", "action", str(i), name)
                    for i, name in enumerate(ACTION_NAMES if layout == "v1" else (*ACTION_NAMES, "oom"))
                ]
                + [("block_0", "state", str(i), name) for i, name in BLOCK_STATES],
            )
            if layout == "v2":
                conn.execute("CREATE TABLE callstack (id INTEGER PRIMARY KEY,callstack TEXT)")
                conn.executemany(
                    "INSERT INTO callstack VALUES (?,?)",
                    ((i + 1, f"stack-{(i + index) % groups:06d}") for i in range(groups)),
                )
                conn.execute(
                    "CREATE TABLE pt_snap_block_reference (blockId INTEGER PRIMARY KEY,stream INTEGER,allocCallstack TEXT,freeCallstack TEXT)"
                )
                columns = ",".join(
                    f'"{key}" {"INTEGER" if isinstance(value, int) or key == "requested_device" else "TEXT"}'
                    for key, value in metadata.items()
                )
                conn.execute(f"CREATE TABLE pt_snap_metadata (id INTEGER PRIMARY KEY,{columns})")
                conn.execute(
                    "INSERT INTO pt_snap_metadata VALUES (" + ",".join("?" for _ in range(len(metadata) + 1)) + ")",  # nosec B608 # Only placeholder count varies; data values are bound separately.
                    [1, *metadata.values()],
                )

            def trace(lo=lo, hi=hi, index=index):
                for event in range(lo, hi + 1):
                    position = event - lo
                    ordinal = position + (half if index == 1 else 0)
                    action = 4 if index < 2 and position < half else 6 if index == 2 and position < active else 7
                    stack = ordinal % groups
                    live = (
                        occupied(index * half + min(position + 1, half))
                        if index < 2
                        else occupied(active) - occupied(min(position + 1, active))
                    )
                    yield (
                        event,
                        action,
                        ordinal * 32,
                        8 * (1 + ordinal % 3),
                        0,
                        live,
                        live,
                        occupied(active),
                        f"stack-{stack:06d}" if layout == "v1" else (stack - index) % groups + 1,
                    )

            conn.executemany("INSERT INTO trace_entry_0 VALUES (?,?,?,?,?,?,?,?,?)", trace())
            count = half if index == 0 else active
            conn.executemany(
                "INSERT INTO block_0 VALUES (?,?,?,?,?,?,?)",
                (
                    (
                        ordinal if ordinal < half else capacity + ordinal - half,
                        ordinal * 32,
                        8 * (1 + ordinal % 3),
                        8,
                        1,
                        ordinal if ordinal < half else capacity + ordinal - half,
                        2 * capacity + ordinal,
                    )
                    for ordinal in range(count)
                ),
            )
            if layout == "v2":
                conn.execute("INSERT INTO pt_snap_block_reference SELECT id,0,NULL,NULL FROM block_0")
        record = {"index": index, "startEventId": lo, "endEventId": hi, "file": file, "ready": True}
        if layout == "v2":
            record.update(startPosition=lo, endPosition=hi, sha256=digest(path))
        records.append(record)
    manifest = {
        "schemaVersion": 1,
        "status": "complete",
        "sourceFile": "synthetic.sql",
        "devices": {
            "0": {
                "eventCount": capacity * 3,
                "sliceCount": 3,
                "readySlices": [0, 1, 2],
                "slices": records,
            }
        },
    }
    if layout == "v2":
        manifest.update(
            format=NATIVE_FORMAT,
            identity=cache_identity("0" * 64, None, capacity),
            metadata=metadata,
            omittedDevices=[],
        )
    else:
        manifest.update(eventsPerSlice=capacity, cacheHash="")
    (dataset / "manifest.json").write_text(json.dumps(manifest))
    single = root / "standalone.db"
    with closing(sqlite3.connect(single, uri=True)) as conn:
        conn.executescript(SCHEMA)
        for record in records:
            conn.execute("ATTACH DATABASE ? AS src", [(dataset / record["file"]).as_uri() + "?mode=ro"])
            if record["index"] == 0:
                conn.execute("INSERT INTO dictionary SELECT * FROM src.dictionary")
            if layout == "v1":
                conn.execute("INSERT INTO trace_entry_0 SELECT * FROM src.trace_entry_0")
            else:
                conn.execute(
                    "INSERT INTO trace_entry_0 SELECT t.id,t.action,t.address,t.size,t.stream,t.allocated,t.active,t.reserved,c.callstack FROM src.trace_entry_0 t LEFT JOIN src.callstack c ON c.id=t.callstackId"
                )
            conn.execute("INSERT OR REPLACE INTO block_0 SELECT * FROM src.block_0")
            conn.commit()
            conn.execute("DETACH DATABASE src")
    return dataset, single


def run_case(root, capacity, active, groups, layout, timeout):
    dataset, single = build_case(root, capacity, active, groups, layout)
    before = inventory(root)
    results = []
    with closing(QueryService()) as service:
        for template, params in (
            ("active_blocks_at_event", {"limit": 20}),
            ("active_memory_callstack_at_event", {"top_n": 20}),
        ):
            params["event_id"] = 2 * capacity - 1
            budget = QueryBudget(timeout, time.monotonic())
            started = time.monotonic()
            result = service.execute_query(template, params, db_path=dataset, exact_total=True, _budget=budget)
            elapsed = time.monotonic() - started
            expected = service.execute_query(template, params, db_path=single, exact_total=True, timeout_s=timeout)
            fields = set(expected.rows[0]) if expected.rows else set()
            assert [{key: row[key] for key in fields} for row in result.rows] == expected.rows  # nosec B101 # Benchmark/acceptance assertion, not an input security check.
            assert result.total == expected.total == (active if template == "active_blocks_at_event" else groups)  # nosec B101 # Benchmark/acceptance assertion, not an input security check.
            coverage = result.scope["source_coverage"]
            assert (
                coverage["active_blocks"]
                == coverage["allocation_events_resolved"]
                == coverage["free_events_resolved"]
                == active
            )  # nosec B101 # Benchmark/acceptance assertion, not an input security check.
            assert budget.work_rows < 150  # nosec B101 # Benchmark/acceptance assertion, not an input security check.
            results.append(
                {
                    "template": template,
                    "elapsed_s": elapsed,
                    "work_rows": budget.work_rows,
                    "work_bytes": budget.work_bytes,
                    "total": result.total,
                    "returned": result.returned,
                }
            )
        rejected = False
        try:
            service.execute_query(
                "active_blocks_at_event",
                {"event_id": 2 * capacity - 1, "limit": -1},
                db_path=dataset,
                timeout_s=timeout,
            )
        except QueryExecutionError as error:
            if "work budget" not in str(error):
                raise
            rejected = True
        if active > 100_000:
            assert rejected  # nosec B101 # Benchmark/acceptance assertion, not an input security check.
    assert inventory(root) == before  # nosec B101 # Benchmark/acceptance assertion, not an input security check.
    return {
        "layout": layout,
        "events": 3 * capacity,
        "active": active,
        "queries": results,
        "unbounded_output_rejected": rejected,
        "standalone_differential": "passed",
        "source_unchanged": True,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capacity", type=int, default=500_000)
    parser.add_argument("--active", type=int, default=200_000)
    parser.add_argument("--groups", type=int, default=32)
    parser.add_argument("--layout", choices=("v1", "v2"), default="v1")
    parser.add_argument("--timeout", type=float, default=120)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="pt-snap-active-capacity-") as temporary:
        print(
            json.dumps(
                run_case(
                    Path(temporary) / "case",
                    args.capacity,
                    args.active,
                    args.groups,
                    args.layout,
                    args.timeout,
                ),
                indent=2,
            )
        )


if __name__ == "__main__":
    main()
