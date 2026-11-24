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

"""Bounded, reproducible seed profiles and valid query cases for both layouts."""

import os
import random
import re
from dataclasses import dataclass, field

from test.core.dataset_lifecycle_fixtures import EVENT_COUNT, shapes

REGRESSION_SEEDS = (0, 7, 31, 67, 136, 196, 2026, 8191)
DEFAULT_SEEDS = 20
MAX_SEEDS = 10_000
SUPPORTED_TEMPLATES = frozenset(
    (
        "memory_peak",
        "allocator_gap",
        "allocation",
        "event",
        "block",
        "leak_detection",
        "freed_block_lifetime",
        "callstack_analysis",
        "preexisting_live",
        "active_blocks_at_event",
        "active_memory_callstack_at_event",
    )
)
FRAME_TEMPLATES = frozenset(("active_memory_frame_tree_at_event",))
UNSUPPORTED_TEMPLATES = frozenset(("event_frames",))


def configured_seeds(environ=None):
    """The nightly bank strictly extends PR seeds; replay overrides the count."""
    environ = os.environ if environ is None else environ

    def integer(name, default, minimum, maximum):
        raw = environ.get(name, str(default)).strip()
        if re.fullmatch(r"[0-9]+", raw) is None or not minimum <= int(raw) <= maximum:
            raise ValueError(f"{name} must be an integer in [{minimum}, {maximum}], got {raw!r}")
        return int(raw)

    count = integer("PT_SNAP_DIFFERENTIAL_SEEDS", DEFAULT_SEEDS, 1, MAX_SEEDS)
    if "PT_SNAP_DIFFERENTIAL_SEED" in environ:
        return (integer("PT_SNAP_DIFFERENTIAL_SEED", 0, 0, 2**63 - 1),)
    bank = list(REGRESSION_SEEDS)
    candidate = 0
    while len(bank) < count:
        if candidate not in REGRESSION_SEEDS:
            bank.append(candidate)
        candidate += 1
    return tuple(bank[:count])


def capacity_for_seed(seed):
    # 5 to 40 shards, including a partial final shard (capacity=3).
    return (2, 3, 4, 5, 10, 16)[seed % 6]


@dataclass(frozen=True)
class QueryCase:
    label: str
    template: str
    params: dict = field(default_factory=dict)
    exact_total: bool = True
    max_rows: int | None = None
    slice_index: int | None = None
    active_oracle: bool = False

    def options(self):
        return {"exact_total": self.exact_total, "max_rows": self.max_rows}


def query_cases(seed, capacity):
    rng = random.Random(seed + 1_000_003)
    cases = [
        QueryCase(f"regression-{index}", template, params) for index, (template, params) in enumerate(shapes(seed))
    ]
    # Every seed exercises critical transitions and both static policies; random
    # coverage cannot accidentally omit free_requested vs free_completed/reuse.
    boundaries = sorted({0, capacity - 1, capacity, 17, 18, 22, 23, 24, 60, 61, EVENT_COUNT - 1})
    for at in boundaries:
        for include_static in (True, False):
            cases.append(
                QueryCase(
                    f"boundary-{at}-static-{include_static}",
                    "active_blocks_at_event",
                    {"event_id": at, "include_static": include_static},
                    exact_total=include_static,
                    active_oracle=True,
                )
            )
    # Empty, full, truncated, and beyond-end pages with both exactness settings
    # occur per seed, rather than waiting for the random parameter bank.
    for exact in (False, True):
        for offset, limit, max_rows in ((0, 0, None), (0, -1, None), (2, 7, 3), (999, 2, None)):
            cases.append(
                QueryCase(
                    f"page-{exact}-{offset}-{limit}",
                    "event",
                    {
                        "min_id": 0,
                        "offset": offset,
                        "limit": limit,
                        "order_by": "id",
                        "order_dir": rng.choice(("ASC", "DESC")),
                    },
                    exact_total=exact,
                    max_rows=max_rows,
                )
            )
    low, high = sorted(rng.sample(range(EVENT_COUNT), 2))
    at = rng.choice(boundaries)

    def paging(choices):
        return {
            "order_by": rng.choice(choices),
            "order_dir": rng.choice(("ASC", "DESC")),
            "offset": rng.choice((0, 1, 7, EVENT_COUNT + 1)),
            "limit": rng.choice((-1, 0, 1, 5, 19)),
        }

    params = {
        "memory_peak": {"start_id": low, "end_id": high},
        "allocator_gap": {"start_id": low, "end_id": high},
        "allocation": {
            "min_id": low,
            "max_id": high,
            "min_active": rng.choice((0, 256, 1024)),
            **paging(("id", "allocated", "active", "reserved")),
        },
        "event": {
            "min_id": low,
            "max_id": high,
            "action": rng.choice((4, 5, 6, 7)),
            "stream": rng.choice((0, 1)),
            **paging(
                (
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
            ),
        },
        "block": {
            "min_size": rng.choice((0, 16, 32, 128)),
            "max_size": 256,
            "min_allocEventId": rng.choice((-1, 0, low)),
            **paging(("id", "address", "size", "requestedSize", "state", "allocEventId", "freeEventId")),
        },
        "leak_detection": {
            "min_size": rng.choice((0, 16, 64, 128)),
            "limit": rng.choice((-1, 0, 1, 7)),
        },
        "freed_block_lifetime": {},
        "callstack_analysis": {
            "min_count": rng.choice((1, 2, 5)),
            "min_size": rng.choice((0, 32, 128)),
            "limit": rng.choice((-1, 0, 1, 7)),
        },
        "preexisting_live": {"event_id": at},
        "active_blocks_at_event": {
            "event_id": at,
            "include_static": rng.choice((True, False)),
            "min_size": rng.choice((0, 16, 128)),
            **paging(("size", "requestedSize", "allocEventId", "freeEventId", "id")),
        },
        "active_memory_callstack_at_event": {
            "event_id": at,
            "include_static": rng.choice((True, False)),
            "min_size": rng.choice((0, 16, 128)),
            "top_n": rng.choice((-1, 0, 1, 2, 20)),
        },
    }
    for template, parameters in params.items():
        cases.append(
            QueryCase(
                f"random-{template}",
                template,
                parameters,
                exact_total=rng.choice((False, True)),
                max_rows=rng.choice((None, 0, 1, 4)),
            )
        )
    # Explicit shard selection has a matching standalone event predicate. Leak
    # slice scope is intentionally unsupported and is not a differential pass.
    for index in sorted({0, (EVENT_COUNT - 1) // capacity, rng.randrange((EVENT_COUNT - 1) // capacity + 1)}):
        lo, hi = index * capacity, min((index + 1) * capacity, EVENT_COUNT) - 1
        for template in ("event", "allocation", "memory_peak", "allocator_gap"):
            bounds = (
                {"min_id": lo, "max_id": hi} if template in ("event", "allocation") else {"start_id": lo, "end_id": hi}
            )
            cases.append(
                QueryCase(
                    f"slice-{index}-{template}",
                    template,
                    bounds,
                    exact_total=rng.choice((False, True)),
                    slice_index=index,
                )
            )
    return cases
