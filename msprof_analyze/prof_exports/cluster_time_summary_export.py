# Copyright (c) 2025, Huawei Technologies Co., Ltd.
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


class CommunicationTimeExport(BaseStatsExport):
    QUERY = """
        SELECT 
            RANK_DEVICE_MAP.rankId,
            si_group.value AS groupName,
            si_op.value AS opName,
            COMMUNICATION_OP.startNs as startNs,
            (COMMUNICATION_OP.endNs - COMMUNICATION_OP.startNs) / 1000.0 AS communication_time
        FROM COMMUNICATION_OP
        CROSS JOIN RANK_DEVICE_MAP
        JOIN STRING_IDS si_group ON COMMUNICATION_OP.groupName = si_group.id
        JOIN STRING_IDS si_op ON COMMUNICATION_OP.opName = si_op.id
        JOIN CANN_API ON CANN_API.connectionId = COMMUNICATION_OP.connectionId
        WHERE CANN_API.startNs >= ? and CANN_API.startNs <= ?
    """


    def __init__(self, db_path, recipe_name, param_dict):
        super().__init__(db_path, recipe_name, param_dict)
        self._query = self.QUERY

    def get_param_order(self):
        return [Constant.START_NS, Constant.END_NS]


class CommunicationOpWithStepExport(BaseStatsExport):
    QUERY = """
        SELECT 
            RANK_DEVICE_MAP.rankId AS rank,
            si_group.value AS groupName,
            si_op.value AS opName,
            (COMMUNICATION_OP.endNs - COMMUNICATION_OP.startNs) / 1000.0 AS communication_time,
            {step_field}
        FROM COMMUNICATION_OP
        CROSS JOIN RANK_DEVICE_MAP
        JOIN STRING_IDS si_group ON COMMUNICATION_OP.groupName = si_group.id
        JOIN STRING_IDS si_op ON COMMUNICATION_OP.opName = si_op.id
        JOIN CANN_API ON CANN_API.connectionId = COMMUNICATION_OP.connectionId
        {join_statement}
        WHERE CANN_API.startNs >= ? and CANN_API.startNs <= ?
    """


    def __init__(self, db_path, recipe_name, param_dict, step_exits=True):
        super().__init__(db_path, recipe_name, param_dict)
        step_field = "-1 AS step"
        join_statement = ""
        if step_exits:
            step_field = "step_time.id AS step"
            join_statement = """
            LEFT JOIN STEP_TIME step_time 
                ON CANN_API.startNs >= step_time.startNs AND CANN_API.startNs <= step_time.endNs
            """
        self._query = self.QUERY.format(
            step_field=step_field,
            join_statement=join_statement
        )

    def get_param_order(self):
        return [Constant.START_NS, Constant.END_NS]

class MemoryAndDispatchTimeExport(BaseStatsExport):
    QUERY = """
    WITH 
        computing AS (
            SELECT 
                TASK.startNs, 
                TASK.endNs, 
                CANN_API.startNs as apiStartNs, 
                0 AS type
            FROM COMPUTE_TASK_INFO
            JOIN TASK ON COMPUTE_TASK_INFO.globalTaskId = TASK.globalTaskId AND TASK.startNs != TASK.endNs
            JOIN CANN_API ON CANN_API.connectionId = TASK.connectionId
        ),
        communication AS (
            SELECT 
                COMMUNICATION_OP.startNs, 
                COMMUNICATION_OP.endNs, 
                CANN_API.startNs as apiStartNs, 
                1 AS type
            FROM COMMUNICATION_OP
            JOIN CANN_API ON CANN_API.connectionId = COMMUNICATION_OP.connectionId
        ),
        memory AS (
            SELECT 
                TASK.startNs, 
                TASK.endNs, 
                TASK.startNs as apiStartNs, 
                4 AS type
            FROM TASK
            WHERE taskType = (SELECT id FROM STRING_IDS WHERE value='MEMCPY_ASYNC')
        ),
        overlap AS (
            SELECT startNs, endNs, apiStartNs, type FROM computing
            UNION ALL SELECT startNs, endNs, apiStartNs, type FROM communication
            UNION ALL SELECT startNs, endNs, apiStartNs, type FROM memory
        )
    SELECT
        overlap.startNs AS start,
        overlap.endNs AS end,
        overlap.type,
        {step_field}
    FROM overlap
    {join_statement}
    WHERE overlap.apiStartNs >= ? and overlap.apiStartNs <= ?
    ORDER BY overlap.startNs, overlap.endNs
    """

    def __init__(self, db_path, recipe_name, param_dict, step_exits=True):
        super().__init__(db_path, recipe_name, param_dict)
        step_field = "-1 AS step"
        join_statement = ""
        if step_exits:
            step_field = "step_time.id AS step"
            join_statement = """
            LEFT JOIN STEP_TIME step_time
                ON overlap.apiStartNs >= step_time.startNs
                AND overlap.apiStartNs <= step_time.endNs
            """
        self._query = self.QUERY.format(
            step_field=step_field,
            join_statement=join_statement
        )
        self.mode = None

    def get_param_order(self):
        return [Constant.START_NS, Constant.END_NS]