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
from msprof_analyze.prof_common.constant import Constant
from msprof_analyze.prof_common.logger import get_logger
from msprof_analyze.prof_exports.base_stats_export import BaseStatsExport


logger = get_logger()


QUERY_COMPUTE_TASK = """
    WITH task_connections AS (
        SELECT 
            str.value AS name,
            task.startNs,
            task.endNs,
            conn.id AS api_conn_id
        FROM 
            {compute_table} AS compute
        LEFT JOIN 
            TASK task ON compute.globalTaskId = task.globalTaskId
        LEFT JOIN 
            STRING_IDS str ON str.id = compute.name
        LEFT JOIN 
            CONNECTION_IDS conn ON conn.connectionId = task.connectionId
    )"""

QUERY_COMMUNICATION_TASK = """
    WITH task_connections AS (
        SELECT 
            str.value AS name,
            comm.startNs,
            comm.endNs,
            conn.id AS api_conn_id
        FROM 
            COMMUNICATION_OP AS comm
        JOIN 
            STRING_IDS str ON str.id = comm.opType
        JOIN 
            CONNECTION_IDS conn ON conn.connectionId = comm.connectionId
    )"""


QUERY_TASK_LINK_PYTORCH_API = """
    SELECT 
        tc.name as kernel_name,
        tc.startNs as kernel_ts,
        tc.endNs as kernel_end,
        api_str.value AS op_name,
        api.startNs as op_ts,
        api.endNs as op_end
    FROM 
        task_connections tc
    JOIN 
        PYTORCH_API api ON tc.api_conn_id = api.connectionId
    JOIN 
        STRING_IDS api_str ON api.name = api_str.id
    ORDER BY op_ts, kernel_ts
"""



QUERY_MSTX_RANGE_WITH_DOMAIN = """
    SELECT
        mstx.startNs,
        mstx.endNs, 
        str_name.value AS name
    FROM
        MSTX_EVENTS mstx
    LEFT JOIN
        STRING_IDS str_name ON mstx.message = str_name.id
    LEFT JOIN
        STRING_IDS str_domain ON mstx.domainId = str_domain.id
    WHERE
        mstx.eventType = 2 AND str_domain.value = 'Module'
    ORDER BY mstx.startNs
"""

QUEYR_FWD_BWD_FLOW = """
    SELECT 
        c.connectionId as connectionId,
        fwd_ids.value as fwd_name,
        fwd_pa.startNs as fwd_ts,
        fwd_pa.endNs as fwd_end,
        bwd_ids.value as bwd_name,
        bwd_pa.startNs as bwd_ts,
        bwd_pa.endNs as bwd_end
    FROM (
        SELECT 
            connectionId,
            MIN(id) as min_id,
            MAX(id) as max_id
        FROM CONNECTION_IDS 
        GROUP BY connectionId
        HAVING COUNT(*) > 1
    ) c
    LEFT JOIN PYTORCH_API fwd_pa ON fwd_pa.connectionId = c.min_id
    LEFT JOIN STRING_IDS fwd_ids ON fwd_ids.id = fwd_pa.name
    LEFT JOIN PYTORCH_API bwd_pa ON bwd_pa.connectionId = c.max_id
    LEFT JOIN STRING_IDS bwd_ids ON bwd_ids.id = bwd_pa.name
    WHERE fwd_ids.value NOT LIKE 'Enqueue%' AND fwd_ids.value NOT LIKE 'Dequeue%'
    ORDER BY c.connectionId
"""


class FrameworkOpToKernelExport(BaseStatsExport):

    def __init__(self, db_path, recipe_name, table_name):
        super().__init__(db_path, recipe_name, param_dict=None)
        if table_name in [Constant.TABLE_COMPUTE_TASK_INFO, Constant.TABLE_COMMUNICATION_SCHEDULE_TASK_INFO]:
            self._query = (QUERY_COMPUTE_TASK + QUERY_TASK_LINK_PYTORCH_API).format(compute_table=table_name)
        elif table_name == Constant.TABLE_COMMUNICATION_OP:
            self._query = QUERY_COMMUNICATION_TASK + QUERY_TASK_LINK_PYTORCH_API
        else:
            logger.error(f"FrameworkOpToKernelExport not support {table_name}")

    def get_param_order(self):
        return []


class ModuleMstxRangeExport(BaseStatsExport):

    def __init__(self, db_path, recipe_name):
        super().__init__(db_path, recipe_name, param_dict=None)
        self._query = QUERY_MSTX_RANGE_WITH_DOMAIN

    def get_param_order(self):
        return []


class FwdBwdFlowExport(BaseStatsExport):
    def __init__(self, db_path, recipe_name):
        super().__init__(db_path, recipe_name, param_dict=None)
        self._query = QUEYR_FWD_BWD_FLOW

    def get_param_order(self):
        return []
