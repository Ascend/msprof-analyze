# -------------------------------------------------------------------------
# This file is part of the MindStudio project.
# Copyright (c) 2024 Huawei Technologies Co.,Ltd.
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

from msprof_analyze.prof_exports.base_stats_export import BaseStatsExport

QUERY_OVERLAP_BUSY_TIME_SQL = '''
WITH combined_tasks AS (
    SELECT
        TASK.startNs as startNs,
        TASK.endNs as endNs
    FROM COMPUTE_TASK_INFO CTI
    JOIN TASK ON TASK.globalTaskId = CTI.globalTaskId

    UNION ALL

    SELECT
        COMM.startNs as startNs,
        COMM.endNs as endNs
    FROM COMMUNICATION_OP COMM
),

-- Assign group numbers to identify continuous overlapping intervals
grouped_tasks AS (
    SELECT
        startNs,
        endNs,
        SUM(new_group) OVER (ORDER BY startNs) AS group_id
    FROM (
        SELECT
            startNs,
            endNs,
            -- Detect when a new group should start (no overlap with previous max end)
            CASE WHEN startNs > MAX(endNs) OVER (
                ORDER BY startNs
                ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING
            ) OR MAX(endNs) OVER (
                ORDER BY startNs
                ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING
            ) IS NULL THEN 1 ELSE 0 END AS new_group
        FROM combined_tasks
    )
)

-- Merge intervals within each group
SELECT
    MIN(startNs) AS "start_ns",
    MAX(endNs) AS "end_ns",
    MAX(endNs) - MIN(startNs) AS "duration"
FROM grouped_tasks
GROUP BY group_id
ORDER BY startNs
'''


class BusyTimeOverlapExport(BaseStatsExport):
    def __init__(self, db_path, recipe_name):
        super().__init__(db_path, recipe_name)
        self._query = QUERY_OVERLAP_BUSY_TIME_SQL

    def get_param_order(self):
        return []


QUERY_DEVICE_TASK_LINK_CANN_PYTORCH_API = """
    SELECT
        task_str.value as task_type,
        TASK.startNs as task_ts,
        TASK.endNs as task_end,
        cann.startNs as cann_ts,
        cann.endNs as cann_end,
        pytorch.startNs as pytorch_ts,
        pytorch.endNs as pytorch_end
    FROM TASK
    LEFT JOIN CANN_API cann ON TASK.connectionId = cann.connectionId
    LEFT JOIN STRING_IDS as task_str ON TASK.taskType = task_str.id
    LEFT JOIN CONNECTION_IDS conn ON conn.connectionId = TASK.connectionId
    LEFT JOIN PYTORCH_API pytorch ON pytorch.connectionId = conn.id
    ORDER BY TASK.startNs ASC
"""


class DeviceTaskLinkCannPytorchExport(BaseStatsExport):
    """Export device task linked with CANN / PyTorch APIs for a given rank db."""

    def __init__(self, db_path, recipe_name):
        super().__init__(db_path, recipe_name)
        self._query = QUERY_DEVICE_TASK_LINK_CANN_PYTORCH_API

    def get_param_order(self):
        return []
