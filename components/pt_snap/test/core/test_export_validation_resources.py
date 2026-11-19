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

"""Nightly million-event validation-only memory acceptance (#253)."""

import json
import os
import platform
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

import pytest

import pt_snap_cli

PROBE = Path(__file__).resolve().parents[2] / "benchmarks/export_validation_memory.py"
MIB = 1024 * 1024


def run_probe(tmp_path, *arguments):
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path(pt_snap_cli.__file__).resolve().parents[1])
    env["HOME"] = env["USERPROFILE"] = str(tmp_path)
    result = subprocess.run(
        [sys.executable, str(PROBE), *map(str, arguments)],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


@pytest.mark.nightly
@pytest.mark.slow
def test_million_event_export_validation_memory_is_bounded(tmp_path, record_property):
    # fcntl/resource are supported on the Linux scheduled runner. Keep the
    # expensive gate out of every-PR platform jobs; do not silently skip it.
    import fcntl

    evidence = []
    with Path("/tmp/ptsnap-large-acceptance.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        for events in (10_000, 1_000_000):
            root = tmp_path / f"native-{events}"
            built = run_probe(tmp_path, "build", root, "--events", events)
            assert built["events"] == events and built["capacity"] == 500_000
            assert len(built["slices"]) == (1 if events == 10_000 else 2)
            # Setup and both instruments each get a fresh process. RSS never
            # includes tracemalloc overhead or the synthetic fixture builder.
            for metric in ("python", "rss"):
                result = run_probe(tmp_path, "measure", root, "--metric", metric)
                assert result["events"] == events
                assert result["tracemalloc_enabled"] == (metric == "python")
                evidence.append(result)
    record_property("export_validation_memory", json.dumps(evidence, sort_keys=True))
    destination = os.environ.get("PT_SNAP_ACCEPTANCE_EVIDENCE_DIR")
    if destination:
        output = Path(destination)
        output.mkdir(parents=True, exist_ok=True)
        (output / "export-validation-memory.json").write_text(json.dumps(evidence, indent=2) + "\n")
    python_results = [row for row in evidence if row["metric"] == "python"]
    rss_results = [row for row in evidence if row["metric"] == "rss"]
    # A Python list of one million integer IDs needs tens of MiB. Leave ample
    # runtime headroom while rejecting the old O(events) validation regression.
    assert all(row["python_peak_bytes"] < 8 * MIB for row in python_results), evidence
    assert python_results[1]["python_peak_bytes"] - python_results[0]["python_peak_bytes"] < 2 * MIB
    # Linux VmHWM belongs to the current address space. ru_maxrss can carry
    # the previous producer/pytest parent's peak across exec; keep it diagnostic.
    assert all("/proc/self/status" in row["rss_source"] for row in rss_results)
    assert all(row["rss_high_water_increase_bytes"] < 32 * MIB for row in rss_results), evidence
    assert all(row["rss_high_water_after_bytes"] < 128 * MIB for row in rss_results), evidence


@pytest.mark.nightly
@pytest.mark.slow
def test_first_500k_dataset_cli_query_startup_trend(tmp_path, record_property):
    """Fresh CLI/process cache, with no latency threshold or OS-cold claim."""
    import fcntl

    from test.core.test_dataset_scale_acceptance import scale_dataset

    with Path("/tmp/ptsnap-large-acceptance.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        root = scale_dataset(tmp_path / "dataset", 500_000, 500_000, "synthetic stack")
        env = os.environ.copy()
        env["PYTHONPATH"] = str(Path(pt_snap_cli.__file__).resolve().parents[1])
        env["HOME"] = env["USERPROFILE"] = str(tmp_path)
        for key in ("PT_SNAP_DB_PATH", "PT_SNAP_QUERY_TIMEOUT", "PT_SNAP_DATASET_CACHE"):
            env.pop(key, None)
        command = [
            sys.executable,
            "-m",
            "pt_snap_cli.cli",
            "query",
            str(root),
            "--template-use",
            "memory_peak",
            "--json",
        ]
        started = time.perf_counter()
        result = subprocess.run(
            command,
            cwd=tmp_path,
            env=env,
            capture_output=True,
            text=True,
            timeout=180,
            check=False,
        )
        seconds = time.perf_counter() - started
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["rows"][0]["peak_active"] == 16
    evidence = {
        "events": 500_000,
        "shards": 1,
        "python": platform.python_version(),
        "sqlite": sqlite3.sqlite_version,
        "platform": platform.platform(),
        "runtime_module": str(Path(pt_snap_cli.__file__).resolve()),
        "command": command,
        "seconds": seconds,
        "cache_contract": "default strong; fresh CLI process and empty process-local cache",
        "os_cache": "uncontrolled; fixture construction may warm the OS page cache",
        "timing_gate": False,
    }
    record_property("dataset_cold_start_trend", json.dumps(evidence, sort_keys=True))
    destination = os.environ.get("PT_SNAP_ACCEPTANCE_EVIDENCE_DIR")
    if destination:
        output = Path(destination)
        output.mkdir(parents=True, exist_ok=True)
        (output / "dataset-cold-start-trend.json").write_text(json.dumps(evidence, indent=2) + "\n")
