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

"""Normalized observations captured before the first-party runtime relocation."""

FIXTURE_REPLAY_GOLDEN = {
    ("snapshot_1768383987920985470.pkl", 0): {
        "initial": (52, 0, 9700, 0, 0, 551550976),
        "actions": {
            "alloc": 3216,
            "free_completed": 3216,
            "free_requested": 3216,
            "segment_alloc": 52,
        },
        "final": (0, 0, 0, 0, 0, 0),
    },
    ("snapshot_expandable.pkl", 0): {
        "initial": (2, 645, 8092, 408698880, 408698880, 643825664),
        "actions": {
            "alloc": 2899,
            "free_completed": 2574,
            "free_requested": 2574,
            "segment_map": 45,
        },
        "final": (2, 320, 0, 94482944, 94482944, 113246208),
    },
    ("snapshot_with_empty_cache.pkl", 0): {
        "initial": (34, 645, 8180, 416417792, 416417792, 509607936),
        "actions": {
            "alloc": 2899,
            "free_completed": 2574,
            "free_requested": 2574,
            "segment_alloc": 79,
            "segment_free": 54,
        },
        "final": (9, 320, 0, 95524864, 95524864, 113246208),
    },
    ("snapshot_with_empty_cache_expandable.pkl", 0): {
        "initial": (3, 645, 8132, 408698880, 408698880, 490733568),
        "actions": {
            "alloc": 2899,
            "free_completed": 2574,
            "free_requested": 2574,
            "segment_map": 75,
            "segment_unmap": 10,
        },
        "final": (2, 320, 0, 94482944, 94482944, 113246208),
    },
    ("snapshot_with_multi_devices.pkl", 0): {
        "initial": (3, 645, 8132, 408698880, 408698880, 490733568),
        "actions": {
            "alloc": 2899,
            "free_completed": 2574,
            "free_requested": 2574,
            "segment_map": 75,
            "segment_unmap": 10,
        },
        "final": (2, 320, 0, 94482944, 94482944, 113246208),
    },
    ("snapshot_with_multi_devices.pkl", 1): {
        "initial": (52, 0, 9700, 0, 0, 551550976),
        "actions": {
            "alloc": 3216,
            "free_completed": 3216,
            "free_requested": 3216,
            "segment_alloc": 52,
        },
        "final": (0, 0, 0, 0, 0, 0),
    },
}

DATABASE_GOLDEN = {
    ("snapshot_1768383987920985470.pkl", 0): {
        "rows": (9700, 3216),
        "actions": {2: 52, 4: 3216, 5: 3216, 6: 3216},
        "synthetic": (0, 0),
        "first_totals": (0, 0, 2097152),
        "last_positive_totals": (0, 0, 551550976),
        "nonempty_callstacks": 5979,
    },
    ("snapshot_expandable.pkl", 0): {
        "rows": (8094, 3219),
        "actions": {0: 47, 4: 2899, 5: 2574, 6: 2574},
        "synthetic": (2, 320),
        "first_totals": (94482944, 94482944, 113246208),
        "last_positive_totals": (408698880, 408698880, 643825664),
        "nonempty_callstacks": 4369,
    },
    ("snapshot_with_empty_cache.pkl", 0): {
        "rows": (8189, 3219),
        "actions": {2: 88, 3: 54, 4: 2899, 5: 2574, 6: 2574},
        "synthetic": (9, 320),
        "first_totals": (95524864, 95524864, 113246208),
        "last_positive_totals": (416417792, 416417792, 509607936),
        "nonempty_callstacks": 4450,
    },
    ("snapshot_with_empty_cache_expandable.pkl", 0): {
        "rows": (8134, 3219),
        "actions": {0: 77, 1: 10, 4: 2899, 5: 2574, 6: 2574},
        "synthetic": (2, 320),
        "first_totals": (94482944, 94482944, 113246208),
        "last_positive_totals": (408698880, 408698880, 490733568),
        "nonempty_callstacks": 4405,
    },
    ("snapshot_with_multi_devices.pkl", 0): {
        "rows": (8134, 3219),
        "actions": {0: 77, 1: 10, 4: 2899, 5: 2574, 6: 2574},
        "synthetic": (2, 320),
        "first_totals": (94482944, 94482944, 113246208),
        "last_positive_totals": (408698880, 408698880, 490733568),
        "nonempty_callstacks": 4405,
    },
    ("snapshot_with_multi_devices.pkl", 1): {
        "rows": (9700, 3216),
        "actions": {2: 52, 4: 3216, 5: 3216, 6: 3216},
        "synthetic": (0, 0),
        "first_totals": (0, 0, 2097152),
        "last_positive_totals": (0, 0, 551550976),
        "nonempty_callstacks": 5979,
    },
}

TRACE_SCHEMA = [
    (0, "id", "INTEGER", 0, None, 1),
    (1, "action", "INTEGER", 0, None, 0),
    (2, "address", "INTEGER", 0, None, 0),
    (3, "size", "INTEGER", 0, None, 0),
    (4, "stream", "INTEGER", 0, None, 0),
    (5, "allocated", "INTEGER", 0, None, 0),
    (6, "active", "INTEGER", 0, None, 0),
    (7, "reserved", "INTEGER", 0, None, 0),
    (8, "callstackId", "INTEGER", 0, None, 0),
]

CALLSTACK_SCHEMA = [
    (0, "id", "INTEGER", 0, None, 1),
    (1, "callstack", "TEXT", 0, None, 0),
]

BLOCK_SCHEMA = [
    (0, "id", "INTEGER", 0, None, 1),
    (1, "address", "INTEGER", 0, None, 0),
    (2, "size", "INTEGER", 0, None, 0),
    (3, "requestedSize", "INTEGER", 0, None, 0),
    (4, "state", "INTEGER", 0, "99", 0),
    (5, "allocEventId", "INTEGER", 0, None, 0),
    (6, "freeEventId", "INTEGER", 0, None, 0),
]

ACTION_VALUE_MAP = {
    "segment_map": 0,
    "segment_unmap": 1,
    "segment_alloc": 2,
    "segment_free": 3,
    "alloc": 4,
    "free_requested": 5,
    "free_completed": 6,
    "workspace_snapshot": 7,
    "oom": 8,
}

BLOCK_STATE_VALUE_MAP = {
    "inactive": -1,
    "active_allocated": 1,
    "active_pending_free": 0,
}
