# Copyright (c) 2026, Huawei Technologies Co., Ltd.
# All rights reserved.
#
# Licensed under the Apache License, Version 2.0  (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
from msprof_analyze.prof_exports.base_stats_export import BaseStatsExport

NS_TO_US = 1000.0
QUERY = f"""
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
LEFT JOIN STRING_IDS AS DOMAIN_IDS
    ON MSTX_EVENTS.domainId = DOMAIN_IDS.id
WHERE
    PMU_IDS.value IN ('aic_scalar_time', 'aic_mte2_time', 'aiv_scalar_time', 'aiv_vec_time', 'aiv_mte2_time', 'aiv_mte3_time')
    AND DOMAIN_IDS.value = 'autofuse'
GROUP BY
    COMPUTE_TASK_INFO.globalTaskId
ORDER BY
    TASK.startNs
"""


class AutofuseExport(BaseStatsExport):
    def __init__(self, db_path):
        super().__init__(db_path, "", {})
        self._query = QUERY

    def get_param_order(self):
        return []
