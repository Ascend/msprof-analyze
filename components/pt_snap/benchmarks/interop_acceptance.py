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

"""Bounded offline physical oracle; never downloads, loads pickle or runs a producer/GUI.

The explicit receipt is caller-reviewed evidence, not a proof of producer authenticity.
The small reference materializes rows in memory: it is NOT a product RSS contract.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
import subprocess  # nosec B404 # Developer validation runner uses argument lists, never a shell.
import sys
from collections import Counter, defaultdict
from contextlib import closing
from pathlib import Path

REVISION = "101f65b877a267ffd5f66ea3834706057ba243e5"
TRACE = (
    "id",
    "action",
    "address",
    "size",
    "stream",
    "allocated",
    "active",
    "reserved",
    "callstack",
)
BLOCK = ("id", "address", "size", "requestedSize", "state", "allocEventId", "freeEventId")
INVARIANT = tuple(k for k in BLOCK if k != "state")
METRICS = ("allocated", "active", "reserved")


def canonical(path: Path) -> Path:
    path = path.absolute()
    if ".." in path.parts:
        raise ValueError("Traversal is not a canonical path")
    for current in (path, *path.parents):
        if current.is_symlink() or (current.exists() and current.resolve() != current):
            raise ValueError(f"Noncanonical/symlink input: {current}")
    return path


def hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_json(path: Path) -> dict:
    path = canonical(path)
    if not path.is_file() or path.stat().st_size > 1024 * 1024:
        raise ValueError("Require a regular JSON file of at most 1 MiB")

    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("Duplicate JSON key")
            result[key] = value
        return result

    def invalid(value):
        raise ValueError(f"Nonfinite JSON value: {value}")

    with path.open("rb") as file:
        raw = file.read(1024 * 1024 + 1)
    if len(raw) > 1024 * 1024:
        raise ValueError("JSON grew beyond the 1 MiB bound")
    result = json.loads(raw, object_pairs_hook=unique, parse_constant=invalid)
    if not isinstance(result, dict):
        raise ValueError("Require a JSON object")
    return result


def disjoint_output(root: Path, output: Path) -> None:
    if output == root or root in output.parents or output in root.parents:
        raise ValueError("Acceptance output must not overlap an input artifact")


def inventory(root: Path) -> dict[str, str]:
    """Inspect all members, including unexpected/dangling sidecars, before SQLite."""
    root = canonical(root)
    if not root.is_dir():
        raise ValueError("Artifact must be an existing directory")
    result = {}
    total = 0
    for index, path in enumerate(root.rglob("*")):
        if index >= 256:
            raise ValueError("Reference exceeds the 256-entry inventory bound")
        canonical(path)
        if path.is_dir():
            continue
        if not path.is_file() or path.name.endswith(("-wal", "-shm", "-journal")):
            raise ValueError(f"Unexpected member/sidecar: {path}")
        total += path.stat().st_size
        if total > 32 * 1024 * 1024:
            raise ValueError("Reference exceeds this small oracle's 32 MiB input bound")
        result[path.relative_to(root).as_posix()] = hash_file(path)
    return result


def verify_receipt(root: Path, receipt: dict, source: Path | None = None) -> dict[str, str]:
    if receipt.get("revision") != REVISION:
        raise ValueError("Require the exact reviewed upstream revision")
    actual = inventory(root)
    if actual != receipt.get("artifactHashes"):
        raise ValueError("Artifact member set or checksum differs from reviewed receipt")
    if source is not None:
        source = canonical(source)
        if not source.is_file() or source.stat().st_size > 2 * 1024 * 1024:
            raise ValueError("Source exceeds the reviewed small hash-only input bound")
        if hash_file(source) != receipt.get("fixtureSHA256"):
            raise ValueError("Source checksum differs from reviewed receipt")
        if source.stat().st_size != receipt.get("fixtureBytes"):
            raise ValueError("Source size differs from reviewed receipt")
    return actual


def physical_oracle(root: Path, device: int) -> dict:
    """Independent immutable SQL + primitive comparisons; no pt-snap imports here."""
    before = inventory(root)
    manifest = read_json(root / "manifest.json")
    if manifest.get("schemaVersion") != 1 or manifest.get("format", "compatibility-v1") not in (
        "compatibility-v1",
        "pt-snap-native-v2",
    ):
        raise ValueError("Unknown artifact version/format")
    # pylint: disable-next=unidiomatic-typecheck  # Reject bool/subclasses: the contract requires exact scalar types.
    if manifest["status"] != "complete" or type(device) is not int or device < 0:
        raise ValueError("Require a complete artifact and explicit nonnegative device")
    slices = manifest["devices"][str(device)]["slices"]
    if not isinstance(slices, list) or not 0 < len(slices) <= 64:
        raise ValueError("Require between 1 and 64 physical slices")
    events, lifecycles, observations, dictionaries, schemas = {}, {}, [], [], []
    boundaries = 0
    trace_rows = 0
    raw_blocks = 0
    for item in slices:
        path = canonical(root / item["file"])
        if path.relative_to(root).as_posix() not in before or not item["ready"]:
            raise ValueError("Unreviewed/unready shard")
        with closing(sqlite3.connect(path.as_uri() + "?mode=ro&immutable=1", uri=True)) as conn:
            conn.row_factory = sqlite3.Row
            columns = [r[1] for r in conn.execute(f"PRAGMA table_info(trace_entry_{device})")]
            sql = (
                f"SELECT t.*,c.callstack FROM trace_entry_{device} t LEFT JOIN callstack c ON t.callstackId=c.id"  # nosec B608 # Table suffix is the integer device ID; row values use bound parameters.
                if "callstackId" in columns
                else f"SELECT * FROM trace_entry_{device}"  # nosec B608 # Table suffix is the integer device ID; row values use bound parameters.
            )
            real = []
            for record in conn.execute(sql + " LIMIT 20001"):
                trace_rows += 1
                if trace_rows > 20_000:
                    raise ValueError("Reference exceeds 20000 physical trace rows, including boundaries")
                row = {k: record[k] for k in TRACE}
                if row["id"] < 0:
                    boundaries += 1
                else:
                    if row["id"] in events:
                        raise ValueError("Duplicate real ID across physical shards")
                    events[row["id"]] = row
                    real.append(row["id"])
            if len(events) > 20_000:
                raise ValueError("Reference exceeds the 20000 real-event oracle bound")
            if not real or min(real) != item["startEventId"] or max(real) != item["endEventId"]:
                raise ValueError("Physical real range does not match manifest")
            blocks = []
            for record in conn.execute(f"SELECT * FROM block_{device} LIMIT 20001"):  # nosec B608 # Table suffix is the integer device ID; row values use bound parameters.
                raw_blocks += 1
                if raw_blocks > 20_000:
                    raise ValueError("Reference exceeds the 20000 physical-block oracle bound")
                blocks.append(dict(record))
            observations.append({r["id"]: r for r in blocks})
            for row in blocks:
                old = lifecycles.get(row["id"])
                if old is not None and any(old[k] != row[k] for k in INVARIANT):
                    raise ValueError("Ambiguous physical lifetime identity; do not deduplicate by address")
                lifecycles[row["id"]] = row  # latest shard observation, not state at E
            dictionary = []
            for record in conn.execute("SELECT * FROM dictionary LIMIT 257"):
                if len(dictionary) >= 256:
                    raise ValueError("Reference dictionary exceeds 256 rows per shard")
                dictionary.append(tuple(record))
            dictionaries.append(sorted(dictionary))
            schema = {}
            for name in (f"trace_entry_{device}", f"block_{device}", "dictionary"):
                columns = []
                for record in conn.execute(f"PRAGMA table_info({name})"):
                    if len(columns) >= 64:
                        raise ValueError("Reference schema exceeds 64 columns per table")
                    columns.append(tuple(record))
                schema[name] = columns
            schemas.append(schema)
    if len(events) != manifest["devices"][str(device)]["eventCount"]:
        raise ValueError("Physical event count does not match manifest")
    if inventory(root) != before:
        raise ValueError("Artifact changed during physical reference read")
    return {
        "events": events,
        "blocks": lifecycles,
        "observations": observations,
        "slices": slices,
        "boundaries": boundaries,
        "raw_blocks": raw_blocks,
        "dictionaries": dictionaries,
        "schemas": schemas,
    }


def canonical_database(oracle: dict, target: Path, device: int) -> None:
    """Create only a NEW standalone reference from physical rows, not a pickle replay."""
    target = canonical(target)
    with target.open("xb"):
        pass
    # pylint: disable-next=confusing-with-statement  # closing() owns lifetime; the SQLite context owns the transaction.
    with closing(sqlite3.connect(target)) as conn, conn:
        conn.executescript(
            'CREATE TABLE dictionary ("table" TEXT,"column" TEXT,"key" TEXT,"value" TEXT);'
            f"CREATE TABLE trace_entry_{device} (id INTEGER PRIMARY KEY,action INTEGER,address INTEGER,size INTEGER,stream INTEGER,allocated INTEGER,active INTEGER,reserved INTEGER,callstack TEXT);"
            f"CREATE TABLE block_{device} (id INTEGER PRIMARY KEY,address INTEGER,size INTEGER,requestedSize INTEGER,state INTEGER,allocEventId INTEGER,freeEventId INTEGER);"
        )
        conn.executemany(
            f"INSERT INTO trace_entry_{device} VALUES (?,?,?,?,?,?,?,?,?)",  # nosec B608 # Table suffix is the integer device ID; row values use bound parameters.
            [tuple(r[k] for k in TRACE) for r in oracle["events"].values()],
        )
        conn.executemany(
            f"INSERT INTO block_{device} VALUES (?,?,?,?,?,?,?)",  # nosec B608 # Table suffix is the integer device ID; row values use bound parameters.
            [tuple(r[k] for k in BLOCK) for r in oracle["blocks"].values()],
        )
        conn.executemany("INSERT INTO dictionary VALUES (?,?,?,?)", oracle["dictionaries"][0])


def require(condition: bool, name: str) -> None:
    if not condition:
        raise AssertionError(f"Differential failed: {name}")


def compare_artifact(root: Path, device: int, reference: Path) -> dict:
    from pt_snap_cli.api import SnapshotAnalyzer
    from pt_snap_cli.core.analysis.report_service import ReportService

    root = canonical(root)
    reference = canonical(reference)
    disjoint_output(root, reference)
    before = inventory(root)
    oracle = physical_oracle(root, device)
    canonical_database(oracle, reference, device)
    events, blocks = oracle["events"], oracle["blocks"]
    records = []
    points = sorted(
        {
            min(events),
            max(events),
            *(i[k] for i in oracle["slices"] for k in ("startEventId", "endEventId")),
            *(min(events, key=lambda n, m=m: (-events[n][m], n)) for m in METRICS),
        }
    )
    with SnapshotAnalyzer(root) as actual, SnapshotAnalyzer(reference) as single:

        def query(name, params=None, **kwargs):
            result = actual.execute_query(name, params, device_id=device, exact_total=True, timeout_s=30, **kwargs)
            scope = result["scope"]
            coverage = scope if scope["kind"] != "event" else scope["source_coverage"]
            require(
                coverage["range_complete"] and not scope["boundary_events_included"],
                name + " scope",
            )
            declared = {r["column"] for r in actual.get_template_info(name)["output_schema"]}
            require(all(set(row) <= declared for row in result["rows"]), name + " declared row keys")
            return result

        trace = query("event")
        require(
            trace["rows"] == sorted(events.values(), key=lambda r: r["id"]),
            "ALL nine-column real events/actions/streams/counters/text",
        )
        require(trace["total"] == len(events) and not trace["truncated"], "event exact total")
        allocation = query("allocation")
        require(
            allocation["rows"] == [{k: events[n][k] for k in ("id", *METRICS)} for n in sorted(events)],
            "allocation counters",
        )
        records.extend(("event", "allocation"))
        ranges = [
            (min(events), max(events)),
            *((i["startEventId"], i["endEventId"]) for i in oracle["slices"]),
        ]
        for lo, hi in ranges:
            params = {"start_id": lo, "end_id": hi}
            peak = query("memory_peak", params)["rows"][0]
            gap = query("allocator_gap", params)["rows"][0]
            for metric in METRICS:
                event = min(
                    (r for r in events.values() if lo <= r["id"] <= hi),
                    key=lambda r, metric=metric: (-r[metric], r["id"]),
                )
                require(
                    (peak["peak_" + metric], peak["peak_" + metric + "_event_id"]) == (event[metric], event["id"]),
                    "global peak earliest ties",
                )
                require(
                    gap["reserved_active_gap_at_" + metric + "_peak"] == event["reserved"] - event["active"],
                    "same-event active gap",
                )
                require(
                    gap["reserved_allocated_gap_at_" + metric + "_peak"] == event["reserved"] - event["allocated"],
                    "same-event allocated gap",
                )
        records.extend(("memory_peak", "allocator_gap"))
        global_blocks = query("block")
        require(
            {tuple(r[k] for k in BLOCK) for r in global_blocks["rows"]}
            == {tuple(r[k] for k in BLOCK) for r in blocks.values()},
            "all canonical lifetime fields/latest state",
        )
        require(
            len({r["lifecycle_id"] for r in global_blocks["rows"]}) == len(blocks),
            "lifecycle dedup",
        )
        for row in global_blocks["rows"]:
            for field, event_key, action in (
                ("allocation_source", "allocEventId", 4),
                ("free_source", "freeEventId", 6),
            ):
                event_id = row[event_key]
                expected = events.get(event_id)
                if expected is not None and expected["action"] == action:
                    source = row[field]
                    require(
                        source is not None and source["event"] == expected,
                        "full original source/free_completed identity",
                    )
                    owner = next(
                        s["index"] for s in oracle["slices"] if s["startEventId"] <= event_id <= s["endEventId"]
                    )
                    require(source["slice_index"] == owner, "cross-shard source ownership")
                    require(
                        source["frames"] is None and source["frames_status"] == "text_only",
                        "original no-extensions frame downgrade",
                    )
                else:
                    require(row[field] is None, "unknown source not invented")
        terminal = oracle["observations"][-1]
        expected_candidates = {
            n
            for n, b in terminal.items()
            if b["state"] in (0, 1) and b["freeEventId"] < 0 and events.get(b["allocEventId"], {}).get("action") == 4
        }
        candidates = query("leak_detection")
        require(
            {r["id"] for r in candidates["rows"]} == expected_candidates,
            "terminal candidates, not leak proof",
        )
        buckets = defaultdict(lambda: [0, 0])
        for b in blocks.values():
            if (
                events.get(b["allocEventId"], {}).get("action") == 4
                and events.get(b["freeEventId"], {}).get("action") == 6
            ):
                distance = b["freeEventId"] - b["allocEventId"]
                index = next((i for i, cap in enumerate((1000, 5000, 20000, 100000)) if distance < cap), 4)
                buckets[index][0] += 1
                buckets[index][1] += b["size"]
        expected_lifetimes = [
            {
                "lifetime_events": ("<1k", "1k-5k", "5k-20k", "20k-100k", ">=100k")[i],
                "block_count": b[0],
                "size_bytes": b[1],
            }
            for i, b in sorted(buckets.items())
        ]
        require(
            query("freed_block_lifetime")["rows"] == expected_lifetimes,
            "completed lifetime histogram",
        )
        records.extend(("block", "leak_detection", "freed_block_lifetime"))
        groups = defaultdict(list)
        for event in events.values():
            if event["callstack"] is not None:
                groups[event["callstack"]].append(event["size"])
        expected_groups = {
            (text, len(sizes), sum(sizes), sum(sizes) / len(sizes), max(sizes)) for text, sizes in groups.items()
        }
        stacks = query("callstack_analysis", {"min_count": 1})
        require(
            {(r["callstack"], r["alloc_count"], r["total_size"], r["avg_size"], r["max_size"]) for r in stacks["rows"]}
            == expected_groups,
            "ALL-action stack activity, not allocation-only or live bytes",
        )
        records.append("callstack_analysis")
        for event_id in points:
            index = next(i for i, s in enumerate(oracle["slices"]) if s["startEventId"] <= event_id <= s["endEventId"])
            expected = {
                n: b
                for n, b in oracle["observations"][index].items()
                if (b["allocEventId"] < 0 or b["allocEventId"] <= event_id)
                and (b["freeEventId"] < 0 or b["freeEventId"] > event_id)
            }
            active = query("active_blocks_at_event", {"event_id": event_id})
            require({r["id"] for r in active["rows"]} == set(expected), "point active IDs")
            require(
                sum(r["size"] for r in active["rows"]) == sum(b["size"] for b in expected.values()),
                "point active bytes",
            )
            grouped = query("active_memory_callstack_at_event", {"event_id": event_id, "top_n": -1})
            require(
                grouped["scope"]["source_coverage"]["active_bytes"] == sum(b["size"] for b in expected.values()),
                "unwindowed byte coverage",
            )
            expected_grouped = single.execute_query(
                "active_memory_callstack_at_event",
                {"event_id": event_id, "top_n": -1},
                device_id=device,
            )["rows"]
            fields = (
                "callstack",
                "category",
                "size_bytes",
                "requested_bytes",
                "block_count",
                "percent_of_active_blocks",
            )
            require(
                sorted(tuple(str(r[k]) for k in fields) for r in grouped["rows"])
                == sorted(tuple(str(r[k]) for k in fields) for r in expected_grouped),
                "canonical standalone active attribution",
            )
            preexisting = query("preexisting_live", {"event_id": event_id})["rows"][0]
            pre = [
                b
                for b in oracle["observations"][index].values()
                if b["allocEventId"] == -1
                and (b["freeEventId"] is None or b["freeEventId"] > event_id or b["freeEventId"] < -1)
            ]
            require(
                preexisting == {"block_count": len(pre), "size_bytes": sum(b["size"] for b in pre)},
                "preexisting versus static occupancy",
            )
        records.extend(("active_blocks_at_event", "active_memory_callstack_at_event", "preexisting_live"))
        page_params = {"order_by": "active", "order_dir": "DESC", "limit": 3, "offset": 1}
        page = query("event", page_params, max_rows=2)
        expected_page = sorted(events.values(), key=lambda r: (-r["active"], -r["id"]))[1:3]
        require(
            page["rows"] == expected_page and page["total"] == len(events) and page["has_more"] and page["truncated"],
            "global sort/page/exact total versus coverage",
        )
        overview = actual.get_database_overview()
    report = ReportService()
    try:
        for metric in METRICS:
            result = report.peak_memory_report(root, device_id=device, metric=metric, limit=-1, timeout_s=30)
            event = min(events.values(), key=lambda r, metric=metric: (-r[metric], r["id"]))
            require(
                result.event_id == event["id"] and result.active_bytes_at_event == event["active"],
                "report same metric event active counter",
            )
            require(
                result.included_bytes == sum(r["size_bytes"] for r in result.callstack_groups),
                "report included byte denominator",
            )
            require(
                result.source_coverage["allocation_source_complete"],
                "report allocation-source coverage",
            )
    finally:
        report.close()
    require(inventory(root) == before, "all artifact bytes/members/sidecars unchanged")
    return {
        "status": "passed",
        "templates": records,
        "real_events": len(events),
        "boundaries_excluded": oracle["boundaries"],
        "raw_block_rows": oracle["raw_blocks"],
        "canonical_lifecycles": len(blocks),
        "repeated_block_rows": oracle["raw_blocks"] - len(blocks),
        "terminal_candidates": len(expected_candidates),
        "all_action_stack_groups": len(groups),
        "points": points,
        "ranges": ranges,
        "overview": overview,
        "hashes_before_after": before,
        "reference_memory": "small materialized oracle; NOT product memory-bound evidence",
        "GUI": "human-deferred/pending/not-run",
        "original_producer": "not-run by this runner",
    }


def compare_forward(original: Path, compatible: Path, device: int) -> dict:
    """Physical forward-export comparison; NOT actual C++/GUI consumption."""
    before = (inventory(original), inventory(compatible))
    expected = physical_oracle(original, device)
    actual = physical_oracle(compatible, device)
    for field in (
        "events",
        "dictionaries",
        "schemas",
        "boundaries",
        "raw_blocks",
    ):
        require(actual[field] == expected[field], "forward physical " + field)

    def partition(rows):
        positive = {n: row for n, row in rows.items() if n >= 0}
        negative = Counter(tuple(row[k] for k in BLOCK if k != "id") for n, row in rows.items() if n < 0)
        return positive, negative

    require(
        partition(actual["blocks"]) == partition(expected["blocks"]),
        "forward physical blocks: exact real IDs; negative field MULTISET",
    )
    require(len(actual["observations"]) == len(expected["observations"]), "forward physical shard count")
    for index, (own, reference) in enumerate(zip(actual["observations"], expected["observations"], strict=True)):
        require(
            partition(own) == partition(reference),
            f"forward physical shard {index}: exact real IDs; negative field MULTISET",
        )
    require(before == (inventory(original), inventory(compatible)), "forward all-member preservation")
    return {
        "status": "passed",
        "scope": "physical export versus existing original artifact; GUI/C++ consumer pending",
        "negative_identity": "producer-local tokens: cross-producer identity UNPROVED; exact six-field/state multisets global and per shard; own-token stability separately validated; no address dedup or ID rewriting",
        "real_events": len(actual["events"]),
        "raw_block_rows": actual["raw_blocks"],
        "all_member_hashes": list(before),
    }


def cli_acceptance(root: Path, device: int, output: Path) -> list[dict]:
    """Write ONLY the new evidence directory's test focus; input remains read-only."""
    import pt_snap_cli.api as source_api
    from pt_snap_cli.api import SnapshotAnalyzer

    home = output / "isolated-home"
    home.mkdir()
    env = {**os.environ, "HOME": str(home), "PYTHONDONTWRITEBYTECODE": "1"}
    env.pop("PT_SNAP_DB_PATH", None)
    parent_api = Path(source_api.__file__).resolve()
    inherited = [str(Path(part or ".").absolute()) for part in env.get("PYTHONPATH", "").split(os.pathsep)]
    env["PYTHONPATH"] = os.pathsep.join([str(parent_api.parents[1]), *inherited])
    probe_command = [
        sys.executable,
        "-c",
        "import pathlib,pt_snap_cli.api; print(pathlib.Path(pt_snap_cli.api.__file__).resolve())",
    ]
    probe = subprocess.run(probe_command, cwd=output, env=env, capture_output=True, text=True, timeout=30, check=False)  # nosec B603 # Local developer tool/interpreter and explicit argv; shell execution is disabled.
    require(
        probe.returncode == 0 and probe.stdout.strip() == str(parent_api),
        "child uses the exact parent API source",
    )
    commands = [
        ["focus", str(root), "--device", str(device), "--json"],
        [
            "query",
            "--template-use",
            "event",
            "--params",
            '{"order_by":"active","order_dir":"DESC","limit":3,"offset":1}',
            "-n",
            "2",
            "--exact-total",
            "--json",
        ],
        [
            "report",
            "peak-memory",
            str(root),
            "--device",
            str(device),
            "--metric",
            "reserved",
            "--limit",
            "-1",
            "--json",
        ],
    ]
    records = []
    for args in commands:
        command = [sys.executable, "-m", "pt_snap_cli.cli", *args]
        result = subprocess.run(command, cwd=output, env=env, capture_output=True, text=True, timeout=60, check=False)  # nosec B603 # Local developer tool/interpreter and explicit argv; shell execution is disabled.
        records.append(
            {
                "command": command,
                "cwd": str(output),
                "source_api": str(parent_api),
                "source_identity_probe": {
                    "command": probe_command,
                    "cwd": str(output),
                    "exit": probe.returncode,
                    "stdout": probe.stdout,
                    "stderr": probe.stderr,
                },
                "env": {key: env[key] for key in ("HOME", "PYTHONDONTWRITEBYTECODE", "PYTHONPATH") if key in env},
                "exit": result.returncode,
                "stderr": result.stderr,
                "status": "passed" if result.returncode == 0 else "failed",
            }
        )
        require(result.returncode == 0, "actual CLI " + args[0])
        data = json.loads(result.stdout)
        if args[0] == "query":
            with SnapshotAnalyzer(root) as analyzer:
                api = analyzer.execute_query(
                    "event",
                    {"order_by": "active", "order_dir": "DESC", "limit": 3, "offset": 1},
                    device_id=device,
                    max_rows=2,
                    exact_total=True,
                )
            require(
                all(
                    data[k] == api[k]
                    for k in (
                        "rows",
                        "total",
                        "returned",
                        "scope",
                        "has_more",
                        "truncated",
                        "total_is_exact",
                    )
                ),
                "actual CLI/API normalized scope/page",
            )
        if args[0] == "report":
            require(
                data["source_coverage"]["allocation_source_complete"] and data["scope"]["range_complete"],
                "actual CLI report coverage",
            )
        records[-1]["results"] = {
            k: data[k]
            for k in (
                "event_id",
                "returned",
                "total",
                "scope",
                "has_more",
                "truncated",
                "source_coverage",
            )
            if k in data
        }
    return records


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact", required=True, type=Path)
    parser.add_argument("--receipt", required=True, type=Path)
    parser.add_argument("--source", type=Path, help="Optional hash-only original pickle identity check")
    parser.add_argument(
        "--compatible",
        type=Path,
        help="Optional EXISTING pt-snap physical export; never generated here",
    )
    parser.add_argument("--device", required=True, type=int)
    parser.add_argument("--output", required=True, type=Path, help="NEW exclusive evidence directory")
    args = parser.parse_args()
    receipt = read_json(args.receipt)
    root = canonical(args.artifact)
    verify_receipt(root, receipt, args.source)  # before any SQLite/product open
    output = canonical(args.output)
    disjoint_output(root, output)
    if args.compatible is not None:
        compatible = canonical(args.compatible)
        disjoint_output(compatible, output)
        manifest = read_json(compatible / "manifest.json")
        identity = manifest.get("ptSnap", {}).get("identity", {})
        require(
            identity.get("sourceSha256") == receipt.get("fixtureSHA256")
            and manifest.get("cacheHash") == receipt.get("saltedCacheHash"),
            "forward same source identity",
        )
    # pylint: disable-next=unidiomatic-typecheck  # Reject bool/subclasses: the contract requires exact scalar types.
    if type(args.device) is not int or args.device < 0:
        raise ValueError("Explicit nonnegative device required")
    output.mkdir()  # never adopt/replace an existing directory
    try:
        result = compare_artifact(root, args.device, output / "canonical-reference.db")
        if args.compatible is not None:
            result["forward_physical"] = compare_forward(root, compatible, args.device)
        result["cli_acceptance"] = cli_acceptance(root, args.device, output)
        verify_receipt(root, receipt, args.source)
    except Exception as exc:
        result = {"status": "failed", "error": repr(exc), "GUI": "pending/not-run"}
        with (output / "acceptance.json").open("x") as file:
            json.dump(result, file, indent=2)
        raise
    result.update(
        {
            "revision": REVISION,
            "receipt_authority": "explicit caller-reviewed input; authenticity not established by hashes",
            "command": sys.argv,
            "cwd": str(Path.cwd()),
            "python": sys.executable,
        }
    )
    with (output / "acceptance.json").open("x") as file:
        json.dump(result, file, indent=2)
    print(
        json.dumps(
            {
                "status": result["status"],
                "real_events": result["real_events"],
                "output": str(output),
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
