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

"""Opt-in SAME-source three-mode baseline in isolated children and NEW outputs.

No warmup, downloads, installs, original producer, GUI or cleanup. Trusted pickle
loads require a separate provenance gate and explicit --trusted-pickle consent.
"""

from __future__ import annotations

import argparse
import functools
import hashlib
import json
import logging
import os
import platform
import sqlite3
import subprocess  # nosec B404 # Developer validation runner uses argument lists, never a shell.
import sys
import time
import uuid
from collections import defaultdict
from contextlib import closing
from pathlib import Path

try:
    import resource
except ImportError:  # Windows has no POSIX getrusage module.
    resource = None

MODES = ("single-db", "pt-snap-native-v2", "compatibility-v1")


def rss_kib(raw: float, system: str) -> float:
    return raw / 1024 if system == "darwin" else raw


def process_peak_rss() -> float | None:
    """Return this process's high-water RSS, or explicitly unavailable on Windows."""
    return None if resource is None else resource.getrusage(resource.RUSAGE_SELF).ru_maxrss


def source_identity(source: Path, expected: str) -> dict:
    if source.is_symlink() or source.resolve() != source or not source.is_file():
        raise ValueError("Source must be an explicit canonical regular file")
    if not isinstance(expected, str) or len(expected) != 64 or any(c not in "0123456789abcdef" for c in expected):
        raise ValueError("Require a lowercase SHA256 identity")
    if source.stat().st_size > 2 * 1024 * 1024:
        raise ValueError("Require the exact reviewed small source (<=2 MiB)")
    digest, size = hashlib.sha256(), 0
    with source.open("rb") as file:
        for chunk in iter(lambda file=file: file.read(1024 * 1024), b""):
            size += len(chunk)
            if size > 2 * 1024 * 1024:
                raise ValueError("Source grew beyond the small input bound")
            digest.update(chunk)
    if digest.hexdigest() != expected:
        raise ValueError("Require the exact reviewed small source (<=2 MiB)")
    return {"path": str(source), "sha256": expected, "bytes": size}


def instrument(module, name: str, label: str, phases: dict) -> None:
    original = getattr(module, name)

    @functools.wraps(original)
    def measured(*args, **kwargs):
        start = time.perf_counter()
        try:
            return original(*args, **kwargs)
        finally:
            phases[label]["seconds"] += time.perf_counter() - start
            phases[label]["calls"] += 1

    setattr(module, name, measured)  # child-local instrumentation only


def cache_hashes(output: Path) -> dict:
    result = {}
    for index, path in enumerate(output.rglob("*")):
        if index >= 256 or path.is_symlink() or path.resolve() != path:
            raise ValueError("Unknown/unsafe benchmark output member")
        if path.is_dir():
            continue
        if not path.is_file() or path.name.endswith(("-wal", "-shm", "-journal")):
            raise ValueError("Benchmark output must be finalized sidecar-free files")
        digest = hashlib.sha256()
        with path.open("rb") as file:
            for chunk in iter(lambda file=file: file.read(1024 * 1024), b""):
                digest.update(chunk)
        result[path.relative_to(output).as_posix()] = digest.hexdigest()
    return result


def require_owned_child(args, identity: dict) -> None:
    envelope = args.envelope
    if (
        # pylint: disable-next=too-many-boolean-expressions  # One preflight gate checks canonical path and consent together.
        envelope is None
        or envelope != args.output.parent / "run-envelope.json"
        or envelope.is_symlink()
        or envelope.resolve() != envelope
        or not envelope.is_file()
        or envelope.stat().st_size > 1024 * 1024
    ):
        raise ValueError("Hidden child requires the bounded same-run ownership envelope")
    with envelope.open("rb") as file:
        raw = file.read(1024 * 1024 + 1)
    if len(raw) > 1024 * 1024:
        raise ValueError("Oversized ownership envelope")
    owner = json.loads(raw)
    if (
        not isinstance(owner, dict)
        or owner.get("source") != identity
        or owner.get("device") != args.device
        or owner.get("capacity") != args.capacity
        or args.output.name != args.mode
    ):
        raise ValueError("Child source/options/output do not match this run")
    recorded = owner["cacheHashes"].get(args.mode)
    if args.phase == "cold":
        if recorded is not None or any(args.output.iterdir()):
            raise ValueError("Cold child requires an empty exclusively allocated output")
    elif recorded is None or cache_hashes(args.output) != recorded:
        raise ValueError("Reuse child requires unchanged successful owned cold output")


def child(args) -> dict:
    from pt_snap_cli.api import SnapshotAnalyzer
    from pt_snap_cli.core.importing import import_service
    from pt_snap_cli.core.splitting import sharded_replay_service
    from pt_snap_cli.core.importing.import_service import ImportService
    from pt_snap_cli.core.common.models import ImportOptions
    from pt_snap_cli.snapshot.tools.adaptors import snapshot2db

    logging.disable(logging.CRITICAL)
    identity = source_identity(args.source, args.sha256)
    require_owned_child(args, identity)  # BEFORE any import/pickle execution
    phases = defaultdict(lambda: {"seconds": 0.0, "calls": 0})
    instrument(snapshot2db, "load_snapshot_representation", "load_representation", phases)
    instrument(sharded_replay_service, "load_snapshot_representation", "load_representation", phases)
    instrument(snapshot2db, "replay_snapshot", "standalone_replay_with_sqlite_hooks", phases)
    instrument(sharded_replay_service, "build_shards", "sharded_replay_with_sqlite_and_backfill", phases)
    instrument(import_service, "convert_shards", "compatible_conversion", phases)
    options = ImportOptions(
        args.source,
        args.output,
        device=args.device,
        set_focus=False,
        force=False,
        events_per_slice=None if args.mode == "single-db" else args.capacity,
        format=args.mode,
    )
    start = time.perf_counter()
    service = ImportService()
    if args.phase == "reuse":

        def no_rebuild(*_args, **_kwargs):
            raise AssertionError("Reuse cache miss: refuse deserialization/rebuild/overwrite")

        service._backend.dump_to_db = no_rebuild
        service._dataset_backend.dump_to_dataset = no_rebuild
        service._msinsight_backend.dump_to_dataset = no_rebuild
    result = service.import_snapshot(options)
    wall = time.perf_counter() - start
    peak_rss = process_peak_rss()  # this process ONLY, before analysis
    peak_rss_kib = rss_kib(peak_rss, sys.platform) if peak_rss is not None else None
    if result.reused != (args.phase == "reuse"):
        raise AssertionError("Cold/reuse measurement did not follow requested cache path")
    members = [result.db_path] if result.db_path.is_file() else sorted(result.db_path.rglob("*.db"))
    disk = {str(p.relative_to(args.output)): p.stat().st_size for p in args.output.rglob("*") if p.is_file()}
    raw_blocks = 0
    unique = set()
    for member in members:
        with closing(sqlite3.connect(member.as_uri() + "?mode=ro&immutable=1", uri=True)) as conn:
            for row in conn.execute(
                f"SELECT id,address,size,requestedSize,allocEventId,freeEventId FROM block_{args.device}"  # nosec B608 # Table suffix is the integer device ID; row values use bound parameters.
            ):
                raw_blocks += 1
                unique.add(tuple(row))
    query_rows = {}
    with SnapshotAnalyzer(result.db_path) as analyzer:
        capabilities = analyzer.list_capabilities()["templates"]
        ids = analyzer.get_database_overview()["devices"]
        last = next(d["last_event_id"] for d in ids if d["device_id"] == args.device)
        params = {
            "event": {"id": last},
            "active_blocks_at_event": {"event_id": last},
            "active_memory_callstack_at_event": {"event_id": last, "top_n": -1},
            "preexisting_live": {"event_id": last},
            "callstack_analysis": {"min_count": 1},
        }
        for template in capabilities:
            name = template["name"]
            if name not in (
                "event",
                "allocation",
                "memory_peak",
                "allocator_gap",
                "active_blocks_at_event",
                "active_memory_callstack_at_event",
                "preexisting_live",
                "block",
                "freed_block_lifetime",
                "leak_detection",
                "callstack_analysis",
            ):
                continue
            start = time.perf_counter()
            query = analyzer.execute_query(
                name, params.get(name, {}), device_id=args.device, exact_total=True, timeout_s=30
            )
            query_rows[name] = {
                "seconds": time.perf_counter() - start,
                "returned": query["returned"],
                "total": query["total"],
                "has_more": query["has_more"],
                "truncated": query["truncated"],
                "scope": query.get("scope"),
                "dataset_support": template["dataset_support"],
                "status": "passed",
            }
    if source_identity(args.source, args.sha256) != identity:
        raise AssertionError("Source changed during measurement")
    return {
        "status": "passed",
        "mode": args.mode,
        "phase": args.phase,
        "import_wall_seconds": wall,
        "isolated_import_process_peak_rss_raw": peak_rss,
        "isolated_import_process_peak_rss_kib": peak_rss_kib,
        "isolated_import_process_peak_rss_mib": (peak_rss_kib / 1024 if peak_rss_kib is not None else None),
        "rss_scope": (
            "RUSAGE_SELF fresh child high-water through import, before queries; includes interpreter/imports"
            if peak_rss is not None
            else "unavailable: this platform does not provide POSIX resource.getrusage"
        ),
        "phase_timings": dict(phases),
        "phase_timing_scope": "named wrapped functions, inclusive; sharded replay includes SQLite writes/backfills, NOT parser-only",
        "phase_rss": {
            "status": "unavailable",
            "reason": "No per-phase sampler/isolation; cumulative high-waters cannot be subtracted into load/replay peaks",
        },
        "other_phase_timings": {
            "status": "unavailable",
            "reason": "validation/hash/metadata/publication remainder not separately instrumented",
        },
        "reused": result.reused,
        "source": identity,
        "device": args.device,
        "capacity": args.capacity if args.mode != "single-db" else None,
        "artifact": str(result.db_path),
        "total_disk_bytes": sum(disk.values()),
        "individual_files_bytes": disk,
        "individual_shard_bytes": {str(p.relative_to(args.output)): p.stat().st_size for p in members},
        "raw_block_rows": raw_blocks,
        "unique_block_invariants": len(unique),
        "repeated_block_rows": raw_blocks - len(unique),
        "repeated_block_cost": {
            "repeated_base_integer_cells": (raw_blocks - len(unique)) * 7,
            "physical_disk_attribution": "unavailable: shared SQLite pages/indexes cannot be apportioned to duplicated rows by file-size subtraction",
        },
        "queries": query_rows,
        "errors": [],
        "python": sys.executable,
        "python_version": sys.version,
        "platform": platform.platform(),
        "source_module": import_service.__file__,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--sha256", required=True)
    parser.add_argument("--device", required=True, type=int)
    parser.add_argument("--capacity", required=True, type=int)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--trusted-pickle", required=True, action="store_true")
    parser.add_argument("--mode", choices=MODES, help=argparse.SUPPRESS)
    parser.add_argument("--phase", choices=("cold", "reuse"), help=argparse.SUPPRESS)
    parser.add_argument("--envelope", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if (args.mode is None) != (args.phase is None) or (args.mode is None) != (args.envelope is None):
        parser.error("Hidden mode/phase/envelope must be supplied together")
    args.source = args.source.absolute()
    args.output = args.output.absolute()
    identity = source_identity(args.source, args.sha256)
    if args.device < 0 or args.capacity <= 0 or args.output.is_symlink() or args.output.resolve() != args.output:
        raise ValueError("Canonical output, nonnegative device and positive capacity required")
    if args.mode:
        print(json.dumps(child(args)))
        return 0
    args.output.mkdir()  # exclusive parent; no adoption, replacement or cleanup
    envelope = args.output / "run-envelope.json"
    owner = {
        "runId": uuid.uuid4().hex,
        "source": identity,
        "device": args.device,
        "capacity": args.capacity,
        "cacheHashes": {},
    }
    with envelope.open("x") as file:
        json.dump(owner, file)
    records = []
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
    script = Path(__file__).resolve()
    head = subprocess.run(["git", "rev-parse", "HEAD"], check=True, capture_output=True, text=True).stdout.strip()  # nosec B603, B607 # Local developer tool/interpreter and explicit argv; shell execution is disabled.
    source_diff = subprocess.run(["git", "diff", "--binary", "HEAD"], check=True, capture_output=True).stdout  # nosec B603, B607 # Local developer tool/interpreter and explicit argv; shell execution is disabled.
    status = "passed"
    for mode in MODES:
        output = args.output / mode
        output.mkdir()
        for phase in ("cold", "reuse"):
            command = [
                sys.executable,
                str(script),
                "--source",
                str(args.source),
                "--sha256",
                args.sha256,
                "--device",
                str(args.device),
                "--capacity",
                str(args.capacity),
                "--output",
                str(output),
                "--trusted-pickle",
                "--mode",
                mode,
                "--phase",
                phase,
                "--envelope",
                str(envelope),
            ]
            start = time.perf_counter()
            result = subprocess.run(command, capture_output=True, text=True, env=env, check=False)  # nosec B603 # Local developer tool/interpreter and explicit argv; shell execution is disabled.
            (args.output / f"{mode}-{phase}.stdout.log").write_text(result.stdout)
            (args.output / f"{mode}-{phase}.stderr.log").write_text(result.stderr)
            record = {
                "command": command,
                "cwd": str(Path.cwd()),
                "env": {k: env[k] for k in ("PYTHONPATH", "PYTHONDONTWRITEBYTECODE") if k in env},
                "exit": result.returncode,
                "status": "passed" if result.returncode == 0 else "failed",
                "subprocess_wall_seconds": time.perf_counter() - start,
            }
            if result.returncode == 0:
                record["results"] = json.loads(result.stdout)
                if phase == "cold":
                    owner["cacheHashes"][mode] = cache_hashes(output)
                    with envelope.open("w") as file:
                        json.dump(owner, file)
                elif cache_hashes(output) != owner["cacheHashes"][mode]:
                    raise AssertionError("Reuse changed owned artifact bytes")
            else:
                record["error"] = result.stderr
                status = "failed"
            records.append(record)
            if status == "failed":
                break
        if status == "failed":
            break
    report = {
        "status": status,
        "source_head": head,
        "tracked_diff_sha256": hashlib.sha256(source_diff).hexdigest(),
        "benchmark_script_sha256": hashlib.sha256(script.read_bytes()).hexdigest(),
        "records": records,
        "cold_definition": "fresh output/process, no warmup; OS page cache NOT cleared",
        "reuse_definition": "fresh process reusing only this run's recognized owned artifact, force=False",
        "original_producer": "not-run; preexisting single cold wall is not comparable RSS/phase evidence",
        "GUI": "pending/not-run",
        "limits": [
            "Pickle loads in full memory; sharding is not streaming",
            "Shards repeat long-lived blocks; compatible format repeats inline stack text",
            "No unstable elapsed-time assertion or performance benefit promise",
            "Query latency includes validation/member hashing and repeated scans; only one local observation",
        ],
    }
    with (args.output / "performance.json").open("x") as file:
        json.dump(report, file, indent=2)
    print(json.dumps({"status": status, "records": len(records), "output": str(args.output)}))
    return 0 if status == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
