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
    ROUND((TASK.endNs - TASK.startNs)/{NS_TO_US}, 3) as "Duration(us)",
    ROUND(MAX(CASE WHEN PMU_IDS.value = 'aic_scalar_time' THEN TASK_PMU_INFO.value END)/{NS_TO_US}, 3) AS "aic_scalar_time(us)",
    ROUND(MAX(CASE WHEN PMU_IDS.value = 'aic_mte2_time' THEN TASK_PMU_INFO.value END)/{NS_TO_US}, 3) AS "aic_mte2_time(us)",
    ROUND(MAX(CASE WHEN PMU_IDS.value = 'aiv_scalar_time' THEN TASK_PMU_INFO.value END)/{NS_TO_US}, 3) AS "aiv_scalar_time(us)",
    ROUND(MAX(CASE WHEN PMU_IDS.value = 'aiv_vec_time' THEN TASK_PMU_INFO.value END)/{NS_TO_US}, 3) AS "aiv_vec_time(us)",
    ROUND(MAX(CASE WHEN PMU_IDS.value = 'aiv_mte2_time' THEN TASK_PMU_INFO.value END)/{NS_TO_US}, 3) AS "aiv_mte2_time(us)",
    ROUND(MAX(CASE WHEN PMU_IDS.value = 'aiv_mte3_time' THEN TASK_PMU_INFO.value END)/{NS_TO_US}, 3) AS "aiv_mte3_time(us)"
FROM COMPUTE_TASK_INFO
LEFT JOIN TASK
    ON COMPUTE_TASK_INFO.globalTaskId = TASK.globalTaskId
LEFT JOIN TASK_PMU_INFO
    ON COMPUTE_TASK_INFO.globalTaskId = TASK_PMU_INFO.globalTaskId
LEFT JOIN MSTX_EVENTS
    ON MSTX_EVENTS.startNs <= TASK.startNs
    AND MSTX_EVENTS.endNs >= TASK.endNs
LEFT JOIN STRING_IDS AS OPNAME_IDS
    ON COMPUTE_TASK_INFO.name = OPNAME_IDS.id
LEFT JOIN STRING_IDS AS PMU_IDS
    ON TASK_PMU_INFO.name = PMU_IDS.id
LEFT JOIN STRING_IDS AS MESSAGE_IDS
    ON MSTX_EVENTS.message = MESSAGE_IDS.id
WHERE
    PMU_IDS.value IN ('aic_scalar_time', 'aic_mte2_time', 'aiv_scalar_time', 'aiv_vec_time', 'aiv_mte2_time', 'aiv_mte3_time')
    AND MESSAGE_IDS.value LIKE 'autofuse%'
GROUP BY
    COMPUTE_TASK_INFO.globalTaskId
ORDER BY
    TASK.startNs
"""
)


class AutofuseExport(BaseStatsExport):
    def __init__(self, db_path):
        super().__init__(db_path, "", {})
        self._query = QUERY

    def get_param_order(self):
        return []
