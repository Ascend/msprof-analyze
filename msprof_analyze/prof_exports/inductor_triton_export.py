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
from msprof_analyze.prof_exports.base_stats_export import BaseStatsExport

NS_TO_US = 1000.0
QUERY = (
    ""  # nosec B608
    f"""
SELECT
    MESSAGE_IDS.value as "message",
    OPNAME_IDS.value as "Name",
    ROUND((TASK.endNs - TASK.startNs)/{NS_TO_US}, 3) as "Duration(us)"
FROM COMPUTE_TASK_INFO
LEFT JOIN TASK
    ON COMPUTE_TASK_INFO.globalTaskId = TASK.globalTaskId
LEFT JOIN MSTX_EVENTS
    ON MSTX_EVENTS.startNs <= TASK.startNs
    AND MSTX_EVENTS.endNs >= TASK.endNs
LEFT JOIN STRING_IDS AS OPNAME_IDS
    ON COMPUTE_TASK_INFO.name = OPNAME_IDS.id
LEFT JOIN STRING_IDS AS MESSAGE_IDS
    ON MSTX_EVENTS.message = MESSAGE_IDS.id
WHERE
    MESSAGE_IDS.value LIKE 'inductor_triton%'
ORDER BY
    TASK.startNs
"""
)


class InductorTritonExport(BaseStatsExport):
    def __init__(self, db_path):
        super().__init__(db_path, "", {})
        self._query = QUERY

    def get_param_order(self):
        return []
