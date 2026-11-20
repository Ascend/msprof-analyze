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

"""Opt-in same-artifact ATTACH, scratch and automatic lifecycle-plan comparison.

Read only an already finalized dataset; never import pickle or run a model. Each
query gets a fresh cache/budget and may create bounded private scratch storage.
Admission is outside the timings. This is an internal reducer microbenchmark,
not a cold CLI/end-to-end measurement or a portable speed assertion.

PYTHONPATH=src python benchmarks/lifecycle_query_plans.py DATASET --runs 3
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import sqlite3
import statistics
import time
from contextlib import closing, nullcontext
from pathlib import Path
from unittest.mock import patch

from pt_snap_cli.core.dataset.lifecycle import dataset_lifecycle_sql
from pt_snap_cli.core.cache.context_cache import ContextCache
from pt_snap_cli.core.dataset.query.dataset_global import global_query
from pt_snap_cli.core.dataset.lifecycle.dataset_lifecycle_scratch import _ScratchSources
from pt_snap_cli.core.dataset.dataset_resolver import DatasetResolver
from pt_snap_cli.core.dataset.dataset_sources import DatasetSourceResolver, QueryBudget
from pt_snap_cli.query.registry import get_query


def measure(resolved, device, template, plan):
    config = get_query(template)
    budget = QueryBudget(
        None,
        time.monotonic(),
        max_work_rows=128,
        max_scratch_db_bytes=0 if plan == "attach" else 512 * 1024**2,
    )
    storage = []
    original_build = _ScratchSources.build

    def build(database, items, maximum):
        original_build(database, items, maximum)
        storage.append(
            database.connection.execute("PRAGMA page_count").fetchone()[0]
            * database.connection.execute("PRAGMA page_size").fetchone()[0]
        )

    forced = (
        patch.object(dataset_lifecycle_sql, "_required_slices", return_value=None)
        if plan == "scratch"
        else nullcontext()
    )
    # pylint: disable-next=confusing-with-statement  # closing() owns lifetime; the SQLite context owns the transaction.
    with closing(ContextCache()) as cache, forced, patch.object(_ScratchSources, "build", build):
        source = DatasetSourceResolver(resolved, device, cache, budget)
        started = time.perf_counter()
        result = global_query(source, template, config.validate_params({}), 5, True, None, config.semantics_version)
        elapsed = time.perf_counter() - started
    coverage = {key: value for key, value in result.scope["source_coverage"].items() if key != "source_queries"}
    signature = json.dumps(
        [result.rows, result.total, result.total_is_exact, result.has_more, coverage],
        sort_keys=True,
    ).encode()
    return {
        "template": template,
        "plan": plan,
        "seconds": elapsed,
        "work_rows": budget.work_rows,
        "work_bytes": budget.work_bytes,
        "scratch_builds": len(storage),
        "derived_db_bytes": storage,
        "result_sha256": hashlib.sha256(signature).hexdigest(),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset", type=Path)
    parser.add_argument("--device", type=int, default=0)
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--warmups", type=int, default=1)
    parser.add_argument(
        "--plans",
        nargs="+",
        choices=("attach", "scratch", "auto"),
        default=["attach", "scratch", "auto"],
    )
    args = parser.parse_args()
    if args.runs < 1 or args.warmups < 0:
        parser.error("runs must be positive and warmups nonnegative")
    resolved = DatasetResolver().inspect(args.dataset)
    if resolved is None:
        parser.error("expected a finalized dataset")
    device = resolved.device(args.device)
    capacity = dataset_lifecycle_sql._attachment_limit()
    if capacity < 1 or ("attach" in args.plans and len(device.slices) > capacity):
        parser.error("forced ATTACH needs the complete device within this SQLite attachment limit")
    samples = []
    signatures = {}
    for template in ("block", "leak_detection", "freed_block_lifetime"):
        for run in range(-args.warmups, args.runs):
            # Alternate plan order to reduce systematic warm-cache/order bias.
            for plan in args.plans if run % 2 == 0 else reversed(args.plans):
                sample = measure(resolved, args.device, template, plan)
                expected = signatures.setdefault(template, sample["result_sha256"])
                if sample["result_sha256"] != expected:
                    raise AssertionError(f"Different lifecycle semantics: {template}/{plan}")
                if run >= 0:
                    samples.append({"run": run, **sample})
    resolved.require_unchanged()
    print(
        json.dumps(
            {
                "dataset": str(resolved.root),
                "fingerprint": resolved.fingerprint,
                "source_bytes": sum((resolved.root / item.file).stat().st_size for item in device.slices),
                "slices": len(device.slices),
                "python": platform.python_version(),
                "platform": platform.platform(),
                "sqlite": sqlite3.sqlite_version,
                "warmups_per_plan": args.warmups,
                "runs_per_plan": args.runs,
                "timing_scope": "admitted dataset; fresh cache/budget; page=5; exact total; includes routing probe",
                "all_results_equal": True,
                "sources_unchanged": True,
                "median_seconds": {
                    template: {
                        plan: statistics.median(
                            sample["seconds"]
                            for sample in samples
                            if sample["template"] == template and sample["plan"] == plan
                        )
                        for plan in args.plans
                    }
                    for template in signatures
                },
                "samples": samples,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
