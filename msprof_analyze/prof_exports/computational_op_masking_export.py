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
from msprof_analyze.prof_common.constant import Constant


class CommunicationOpWithExport(BaseStatsExport):
    QUERY = """
    SELECT
        COMMUNICATION_OP.startNs,
        COMMUNICATION_OP.endNs,
        D.group_name AS parallelType
    FROM COMMUNICATION_OP
    JOIN STRING_IDS ON COMMUNICATION_OP.groupName = STRING_IDS.id
    JOIN (
        SELECT 
            j.key,
            json_extract(j.value, '$.group_name') AS group_name
        FROM META_DATA,
            json_each(META_DATA.value) AS j
        WHERE META_DATA.name = "parallel_group_info"
    ) AS D ON STRING_IDS.value = D.key
    WHERE COMMUNICATION_OP.startNs >= ? AND COMMUNICATION_OP.endNs <= ?
    """

    def __init__(self, db_path, recipe_name, param_dict):
        super().__init__(db_path, recipe_name, param_dict)
        self._query = self.QUERY

    def get_param_order(self):
        return [Constant.START_NS, Constant.END_NS]


class ComputeTaskInfoWithExport(BaseStatsExport):
    QUERY = """
    WITH compute_info AS (
        SELECT 
            (SELECT value FROM STRING_IDS WHERE id = t.name) AS op_name,
            t.globalTaskId,
            (SELECT value FROM STRING_IDS WHERE id = t.opType) AS op_type,
            (SELECT value FROM STRING_IDS WHERE id = t.taskType) AS task_type
        FROM 
            COMPUTE_TASK_INFO t
    )
    SELECT
        compute_info.*,
        task.startNs as task_start_time,
        task.endNs as task_end_time,
        task.endNs - task.startNs as task_duration
    FROM 
        compute_info
    JOIN 
        TASK as task ON compute_info.globalTaskId = task.globalTaskId
    WHERE task.startNs >= ? AND task.endNs <= ?
    """

    def __init__(self, db_path, recipe_name, param_dict):
        super().__init__(db_path, recipe_name, param_dict)
        self._query = self.QUERY

    def get_param_order(self):
        return [Constant.START_NS, Constant.END_NS]
