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


class InductorTritonExport(BaseStatsExport):
    def __init__(self, db_path):
        super().__init__(db_path, "", {})
        self._query = QUERY

    def get_param_order(self):
        return []
