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

"""Strict differential comparison with deterministic failure evidence."""

import dataclasses
import json

# Other result metadata describes dataset-only source provenance. Every field
# returned by the standalone SQL oracle is compared, plus these envelope fields.
ENVELOPE_FIELDS = (
    "total",
    "returned",
    "total_is_exact",
    "has_more",
    "truncated",
    "device_id",
    "template",
    "semantics_version",
)


def compare_case(actual, reference, query, root, seed, layout, capacity):
    context = {"seed": seed, "format": layout, "capacity": capacity, **dataclasses.asdict(query)}
    outcomes = {}
    errors = {}
    for label, analyzer in (("dataset", actual), ("standalone", reference)):
        options = query.options()
        if label == "dataset" and query.slice_index is not None:
            options["slice_index"] = query.slice_index
        try:
            outcomes[label] = analyzer.execute_query(query.template, query.params, **options)
        except Exception as exc:
            # Capture both outcomes for diagnosis, but NEVER accept two failures.
            errors[label] = {"type": type(exc).__name__, "message": str(exc)}
    try:
        assert not errors, f"unexpected query errors: {errors}"
        got, want = outcomes["dataset"], outcomes["standalone"]
        # Dataset adds provenance fields. Only state at a point is observational
        # rather than comparable; the caller independently checks its owner-slice value.
        omit = {"state"} if query.template == "active_blocks_at_event" else set()
        fields = set(want["rows"][0]) - omit if want["rows"] else set()
        actual_rows = [{key: row[key] for key in fields} for row in got["rows"]]
        expected_rows = [{key: row[key] for key in fields} for row in want["rows"]]
        assert actual_rows == expected_rows, "row values/order differ"
        for key in ENVELOPE_FIELDS:
            assert got[key] == want[key], f"{key}: {got[key]!r} != {want[key]!r}"
        assert got["scope"]["boundary_events_included"] is False
        if query.slice_index is not None:
            assert got["scope"]["slice_indices"] == [query.slice_index]
        if query.template == "leak_detection":
            # #254: equality is valid here because this generated, proved history
            # retains every live allocation at the terminal shard. It is NOT a
            # universal equivalence for earlier-only/unproved/inactive histories.
            for row in got["rows"]:
                assert row["terminal_survivor"] and row["state"] in (0, 1)
                assert row["identity_status"] == "proved_allocation_event"
                assert row["freeEventId"] == -1 and row["allocEventId"] >= 0
        return got
    except (AssertionError, KeyError) as exc:
        evidence = root / "differential-failure.json"
        evidence.write_text(
            json.dumps(
                {"case": context, "errors": errors, "outcomes": outcomes},
                ensure_ascii=False,
                indent=2,
            )
        )
        replay = (
            f"PT_SNAP_DIFFERENTIAL_SEED={seed} pytest test/core/test_dataset_realistic.py -k 'seeded and {layout}'"
        )
        raise AssertionError(
            f"{exc}; case={json.dumps(context, sort_keys=True)}; evidence={evidence}; replay: {replay}"
        ) from exc
