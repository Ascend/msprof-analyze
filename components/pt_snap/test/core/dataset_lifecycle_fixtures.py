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

"""Deterministic synthetic v1/native-v2 fixtures with replay-faithful window membership.

These fixtures exercise SQL/query contracts, not the snapshot producer/exporter.
The independent model retains full lifecycle IDs across windows, includes only
carry-in/new allocations, and drops lifetimes completed before a window starts.
"""

import hashlib
import json
import random
import sqlite3
from contextlib import closing

from pt_snap_cli.core.dataset.dataset_contract import ACTION_NAMES, BLOCK_STATES, validate_dataset
from pt_snap_cli.core.dataset.dataset_resolver import DatasetResolver
from pt_snap_cli.core.dataset.native_dataset_contract import NATIVE_FORMAT, cache_identity

EVENT_COUNT = 80
CAPACITY = 10
SCHEMA = """CREATE TABLE dictionary ("table" TEXT,"column" TEXT,"key" TEXT,"value" TEXT);
CREATE TABLE trace_entry_0 (id INTEGER PRIMARY KEY, action INTEGER,address INTEGER,size INTEGER,stream INTEGER,allocated INTEGER,active INTEGER,reserved INTEGER,callstack TEXT);
CREATE TABLE block_0 (id INTEGER PRIMARY KEY,address INTEGER,size INTEGER,requestedSize INTEGER,state INTEGER,allocEventId INTEGER,freeEventId INTEGER);"""


def timeline(seed):
    rng = random.Random(seed)
    blocks = {
        -2: {
            "id": -2,
            "address": 900,
            "size": 48,
            "requestedSize": 40,
            "alloc": -1,
            "free": -1,
            "request": -1,
            "stack": None,
        },
        -1: {
            "id": -1,
            "address": 800,
            "size": 96,
            "requestedSize": 80,
            "alloc": -1,
            "free": -1,
            "request": -1,
            "stack": None,
        },
    }
    trace = []
    # Slots exceed the largest block, so live address intervals cannot overlap.
    nextaddr = 5000
    fixed = {
        0: ("a", 1000, "shared"),
        1: ("a", 1512, None),
        2: ("a", 2024, ""),
        3: ("a", 2536, "[missing callstack]"),
        4: ("a", 3048, " \n"),
        17: ("r", -1),
        18: ("f", -1),
        22: ("r", 0),
        23: ("f", 0),
        24: ("a", 1000, "reuse"),
        60: ("r", 24),
        61: ("f", 24),
    }
    protected = {-2, -1, 0, 1, 2, 3, 4, 24}
    for event in range(EVENT_COUNT):
        if event in fixed:
            op = fixed[event]
        else:
            live = [b["id"] for b in blocks.values() if b["free"] == -1 and b["id"] not in protected]
            pending = [i for i in live if blocks[i]["request"] >= 0]
            ready = [i for i in live if blocks[i]["request"] == -1]
            coin = rng.random()
            if coin < 0.23 and pending:
                op = ("f", rng.choice(pending))
            elif coin < 0.48 and ready:
                op = ("r", rng.choice(ready))
            elif coin < 0.87:
                available = [
                    b["address"]
                    for b in blocks.values()
                    if b["free"] >= 0
                    and b["address"] >= 5000
                    and all(c["address"] != b["address"] or c["free"] >= 0 for c in blocks.values())
                ]
                address = rng.choice(available) if available and rng.random() < 0.6 else nextaddr
                if address == nextaddr:
                    nextaddr += 512
                op = (
                    "a",
                    address,
                    rng.choice(
                        [
                            "shared",
                            "stack-A",
                            "stack-B",
                            None,
                            "",
                            "[missing callstack]",
                            " \n",
                            "长栈",
                        ]
                    ),
                )
            else:
                op = ("w",)
        kind = op[0]
        if kind == "a":
            size = rng.choice([16, 32, 64, 128, 256])
            req = size - rng.randrange(0, size // 4 + 1)
            blocks[event] = {
                "id": event,
                "address": op[1],
                "size": size,
                "requestedSize": req,
                "alloc": event,
                "free": -1,
                "request": -1,
                "stack": op[2],
            }
            action, address, stack = 4, op[1], op[2]
        elif kind in ("r", "f"):
            b = blocks[op[1]]
            size, address = b["size"], b["address"]
            stack = rng.choice(["free-A", "free-B", None, ""])
            if kind == "r":
                b["request"] = event
                action = 5
            else:
                b["free"] = event
                action = 6
        else:
            action, address, size, stack = 7, 0, 0, rng.choice(["workspace", None, ""])
        alive = [b for b in blocks.values() if b["free"] == -1]
        active = sum(b["size"] for b in alive)
        allocated = sum(b["size"] for b in alive if b["request"] == -1)
        reserved = ((active + 255) // 256) * 256 + 1024
        trace.append((event, action, address, size, rng.choice([0, 1]), allocated, active, reserved, stack))
    return trace, list(blocks.values())


def member(b, lo, hi):
    return (b["alloc"] == -1 or b["alloc"] <= hi) and (b["free"] == -1 or b["free"] >= lo)


def state_at_left(b, lo):
    return 0 if b["request"] >= 0 and b["request"] < lo else 1


def row(b, state):
    return (b["id"], b["address"], b["size"], b["requestedSize"], state, b["alloc"], b["free"])


def db(path, trace, rows, boundary=True):
    with closing(sqlite3.connect(path)) as c, c:
        c.executescript(SCHEMA)
        c.executemany(
            "INSERT INTO dictionary VALUES (?,?,?,?)",
            [("trace_entry_0", "action", str(i), n) for i, n in enumerate(ACTION_NAMES)]
            + [("block_0", "state", str(i), n) for i, n in BLOCK_STATES],
        )
        c.executemany("INSERT INTO trace_entry_0 VALUES (?,?,?,?,?,?,?,?,?)", trace)
        if boundary:
            c.execute("INSERT INTO trace_entry_0 VALUES (-1,2,0,1048576,0,999999,999999,999999,'boundary-excluded')")
        c.executemany("INSERT INTO block_0 VALUES (?,?,?,?,?,?,?)", rows)


def build(out, seed, *, layout="v1", capacity=CAPACITY):
    if layout not in ("v1", "v2"):
        raise ValueError(f"unsupported fixture layout: {layout}")
    if not 1 <= capacity <= EVENT_COUNT:
        raise ValueError(f"invalid fixture capacity: {capacity}")
    root = out / f"seed-{seed:04d}-{layout}"
    root.mkdir()
    dataset = root / "dataset"
    (dataset / "device_0").mkdir(parents=True)
    trace, blocks = timeline(seed)
    slices = []
    windows = []
    for i, lo in enumerate(range(0, EVENT_COUNT, capacity)):
        hi = min(lo + capacity, EVENT_COUNT) - 1
        rows = [row(b, state_at_left(b, lo)) for b in blocks if member(b, lo, hi)]
        assert all(b[5] == -1 or b[5] <= hi for b in rows)
        assert all(b[6] == -1 or b[6] >= lo for b in rows)
        file = f"device_0/slice_{i:05d}.db"
        db(dataset / file, trace[lo : hi + 1], rows)
        slices.append({"index": i, "startEventId": lo, "endEventId": hi, "file": file, "ready": True})
        windows.append({"slice": i, "lo": lo, "hi": hi, "block_ids": [r[0] for r in rows]})
    manifest = {
        "schemaVersion": 1,
        "status": "complete",
        "sourceFile": "/synthetic/no-pickle",
        "cacheHash": "",
        "eventsPerSlice": capacity,
        "devices": {
            "0": {
                "eventCount": EVENT_COUNT,
                "sliceCount": len(slices),
                "readySlices": list(range(len(slices))),
                "slices": slices,
            }
        },
    }
    (dataset / "manifest.json").write_text(json.dumps(manifest))
    single = root / "single.db"
    # Global block uses latest containing observation, matching its documented state_scope;
    # point-event comparisons exclude stored state, which is not state at requested E.
    finalrows = [
        row(
            b,
            state_at_left(
                b,
                max(window["lo"] for window in windows if member(b, window["lo"], window["hi"])),
            ),
        )
        for b in blocks
    ]
    db(single, trace, finalrows)
    (root / "timeline.json").write_text(
        json.dumps(
            {
                "seed": seed,
                "format": layout,
                "capacity": capacity,
                "trace": trace,
                "blocks": blocks,
                "layout": windows,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    if layout == "v2":
        native_dataset(dataset, single, trace, blocks, manifest, seed, capacity)
        assert DatasetResolver().inspect(dataset).callstack_layout == "v2"
    else:
        validate_dataset(dataset)
    return root, dataset, single, trace, blocks


def shapes(seed):
    event = random.Random(seed + 10000).choice(
        [0, 9, 10, 17, 18, 19, 20, 22, 23, 24, 29, 30, 39, 40, 59, 60, 61, 69, 70, 79]
    )
    return [
        ("memory_peak", {}),
        ("memory_peak", {"start_id": 10, "end_id": 61}),
        ("allocator_gap", {}),
        ("allocator_gap", {"start_id": 10, "end_id": 61}),
        ("allocation", {"min_id": 0}),
        (
            "allocation",
            {
                "min_id": 10,
                "max_id": 61,
                "order_by": "active",
                "order_dir": "DESC",
                "limit": 7,
                "offset": 2,
            },
        ),
        ("event", {"min_id": 0}),
        (
            "event",
            {"min_id": 0, "order_by": "callstack", "order_dir": "ASC", "limit": 9, "offset": 2},
        ),
        ("event", {"min_id": 0, "action": 4}),
        ("event", {"id": event}),
        ("block", {}),
        ("block", {"address": 1000}),
        ("block", {"min_size": 32, "order_by": "id", "order_dir": "ASC", "limit": 6, "offset": 2}),
        ("leak_detection", {}),
        ("freed_block_lifetime", {}),
        ("callstack_analysis", {"min_count": 1}),
        ("preexisting_live", {"event_id": event}),
        ("active_blocks_at_event", {"event_id": event}),
        ("active_memory_callstack_at_event", {"event_id": event, "top_n": -1}),
        (
            "active_memory_callstack_at_event",
            {"event_id": event, "top_n": 1, "include_static": False, "min_size": 16},
        ),
    ]


def native_dataset(dataset, single, trace, blocks, manifest, seed, capacity):
    """Write independently modeled native tables, not a relabeled v1 manifest.

    All trace references, including NULL-text stacks, have real local stack IDs.
    Their assignment rotates per shard so local IDs are never global identities.
    This exercises the reader; it deliberately does not claim exporter coverage.
    """
    source = json.dumps({"trace": trace, "blocks": blocks}, sort_keys=True).encode()
    digest = hashlib.sha256(source).hexdigest()
    metadata = {
        "metadata_schema_version": 1,
        "import_format_version": 2,
        "source_sha256": digest,
        "source_size": len(source),
        "source_name": f"synthetic-seed-{seed}.json",
        "requested_device": None,
        "importer_name": "synthetic-differential-fixture",
        "importer_version": "1",
        "completed_at": "2026-01-01T00:00:00+00:00",
    }
    slices = manifest["devices"]["0"]["slices"]
    for index, path in enumerate([*(dataset / s["file"] for s in slices), single]):
        with closing(sqlite3.connect(path)) as connection, connection:
            events = connection.execute("SELECT * FROM trace_entry_0 ORDER BY id").fetchall()
            texts = list(dict.fromkeys(event[-1] for event in events))
            random.Random(seed + index).shuffle(texts)
            stack_ids = {text: i for i, text in enumerate(texts)}
            connection.executescript(
                "ALTER TABLE trace_entry_0 RENAME TO inline_trace;"
                "CREATE TABLE trace_entry_0 (id INTEGER PRIMARY KEY,action INTEGER,"
                "address INTEGER,size INTEGER,stream INTEGER,allocated INTEGER,"
                "active INTEGER,reserved INTEGER,callstackId INTEGER);"
                "CREATE TABLE callstack (id INTEGER PRIMARY KEY,callstack TEXT);"
                "CREATE TABLE pt_snap_block_reference (blockId INTEGER PRIMARY KEY,"
                "stream INTEGER,allocCallstack TEXT,freeCallstack TEXT);"
                "CREATE TABLE pt_snap_metadata (id INTEGER PRIMARY KEY,"
                "metadata_schema_version INTEGER,import_format_version INTEGER,"
                "source_sha256 TEXT,source_size INTEGER,source_name TEXT,"
                "requested_device INTEGER,importer_name TEXT,importer_version TEXT,"
                "completed_at TEXT);"
            )
            connection.executemany("INSERT INTO callstack VALUES (?,?)", enumerate(texts))
            connection.executemany(
                "INSERT INTO trace_entry_0 VALUES (?,?,?,?,?,?,?,?,?)",
                [(*event[:-1], stack_ids[event[-1]]) for event in events],
            )
            connection.execute("DROP TABLE inline_trace")
            connection.execute("INSERT INTO dictionary VALUES ('trace_entry_0','action','8','oom')")
            contained = {row[0] for row in connection.execute("SELECT id FROM block_0")}
            connection.executemany(
                "INSERT INTO pt_snap_block_reference VALUES (?,?,?,?)",
                [
                    (
                        b["id"],
                        trace[b["alloc"]][4] if b["alloc"] >= 0 else 0,
                        b["stack"],
                        trace[b["free"]][-1] if b["free"] >= 0 else None,
                    )
                    for b in blocks
                    if b["id"] in contained
                ],
            )
            connection.execute(
                "INSERT INTO pt_snap_metadata VALUES (1,?,?,?,?,?,?,?,?,?)",
                list(metadata.values()),
            )
        if index < len(slices):
            item = slices[index]
            item.update(
                startPosition=item["startEventId"],
                endPosition=item["endEventId"],
                sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
            )
    native = {
        "format": NATIVE_FORMAT,
        "schemaVersion": 1,
        "status": "complete",
        "sourceFile": metadata["source_name"],
        "identity": cache_identity(digest, None, capacity),
        "metadata": metadata,
        "omittedDevices": [],
        "devices": manifest["devices"],
    }
    (dataset / "manifest.json").write_text(json.dumps(native))
