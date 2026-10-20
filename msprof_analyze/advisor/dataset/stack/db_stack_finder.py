# -------------------------------------------------------------------------
# This file is part of the MindStudio project.
# Copyright (c) 2025 Huawei Technologies Co.,Ltd.
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

import os
from typing import List

import pandas as pd

from msprof_analyze.prof_common.constant import Constant
from msprof_analyze.prof_common.db_manager import DBManager
from msprof_analyze.prof_common.logger import get_logger

logger = get_logger()


class DBStackFinder:
    QUERY_API_CALL_STACK_SQL = """
    WITH ranked_api AS (
        SELECT
            api.*,
            ROW_NUMBER() OVER (ORDER BY api.startNs) AS dataset_index
        FROM
            PYTORCH_API as api
    )

    SELECT
        api.dataset_index,
        api_name_str.value AS name,
        api.startNs / 1000.0 AS ts,
        (api.endNs - api.startNs) / 1000.0 AS dur,
        GROUP_CONCAT(stack_str.value, ';\n' ORDER BY call.stackDepth ASC) AS call_stack
    FROM ranked_api as api
    LEFT JOIN STRING_IDS as api_name_str ON api.name = api_name_str.id
    LEFT JOIN PYTORCH_CALLCHAINS as call ON api.callchainId = call.id
    LEFT JOIN STRING_IDS as stack_str ON call.stack = stack_str.id
    WHERE api.callchainId IS NOT NULL
    GROUP BY api.startNs, api.name, api_name_str.value, api.globalTid, api.endNs, api.dataset_index;
    """

    QUERY_TASK_STACK_WITH_NAME_TEMPLATE = """
    WITH combined_tasks AS (
        SELECT name, taskType, globalTaskId FROM COMPUTE_TASK_INFO
        {comm_schedule}
    ),
    task_connections AS (
        SELECT
            str.value AS op_name,
            task.taskId AS task_id,
            str_type.value AS task_type,
            conn.id AS api_conn_id
        FROM combined_tasks ct
        JOIN TASK task ON ct.globalTaskId = task.globalTaskId
        JOIN STRING_IDS str ON str.id = ct.name
        JOIN STRING_IDS str_type ON str_type.id = ct.taskType
        JOIN CONNECTION_IDS conn ON conn.connectionId = task.connectionId
        WHERE str_type.value = ?
    )

    SELECT
        tc.op_name,
        tc.task_id,
        tc.task_type,
        api_str.value AS api_name,
        api.startNs / 1000.0 AS ts,
        (api.endNs - api.startNs) / 1000.0 AS dur,
        GROUP_CONCAT(stack_str.value, ';\n' ORDER BY cc.stackDepth ASC) AS call_stack
    FROM task_connections tc
    JOIN PYTORCH_API api ON tc.api_conn_id = api.connectionId
    JOIN STRING_IDS api_str ON api.name = api_str.id
    JOIN PYTORCH_CALLCHAINS cc ON api.callchainId = cc.id
    JOIN STRING_IDS stack_str ON cc.stack = stack_str.id
    GROUP BY tc.op_name, tc.task_id, tc.task_type, api_str.value, api.startNs, api.endNs
    """

    COMBINE_COMMUNICATION_SCHEDULE_INFO = """
    UNION ALL
    SELECT name, taskType, globalTaskId FROM COMMUNICATION_SCHEDULE_TASK_INFO
    """

    def __init__(self, db_path):
        self._db_path = db_path
        self.related_table = [Constant.TABLE_PYTORCH_API, Constant.TABLE_PYTORCH_CALLCHAINS]
        self.stack_map = {}

    def get_task_stack_by_op_name(self, op_name: List[str], task_type: str):
        """
        input:
            op_name: ascend_hardware上的算子名称，此处仅限为计算类算子
            task_type: e.g. AI_CPU/AI_CORE/MIX_AIC
        output:
            List[List[task_id, op_name, task_type, stack]]: 所有算子名称相符的堆栈信息
        """
        tag = task_type + "_" + "stack"
        if tag not in self.stack_map or self.stack_map[tag] is None:
            comm_schedule = (
                self.COMBINE_COMMUNICATION_SCHEDULE_INFO
                if DBManager.check_tables_in_db(self._db_path, Constant.TABLE_COMMUNICATION_SCHEDULE_TASK_INFO)
                else ""
            )
            if not self._query_stack(
                tag, self.QUERY_TASK_STACK_WITH_NAME_TEMPLATE.format(comm_schedule=comm_schedule), [task_type]
            ):
                return []

        df = self.stack_map[tag]
        filtered_df = df[df['op_name'].isin(op_name)]

        if filtered_df.empty:
            return []
        return filtered_df[['task_id', 'op_name', 'task_type', 'call_stack']].values.tolist()

    def get_api_stack_by_api_index(self, index_list: List[int]):
        """
        input:
            index_list: 框架侧api的根据startNs排序的index
        output:
            Dict: key为index, value为对应的stack
        """
        tag = "api_stack"
        if tag not in self.stack_map or self.stack_map[tag] is None:
            if not self._query_stack(tag, self.QUERY_API_CALL_STACK_SQL):
                return {}

        df = self.stack_map[tag]
        filtered_df = df[df['dataset_index'].isin(index_list)]

        if filtered_df.empty:
            return {}
        return filtered_df.set_index("dataset_index")["call_stack"].to_dict()

    def _is_db_contains_stack(self):
        return os.path.exists(self._db_path) and DBManager.check_tables_in_db(self._db_path, *self.related_table)

    def _query_stack(self, name, sql, params=None):
        if not self._is_db_contains_stack():
            self.stack_map[name] = None
            return False
        conn, cursor = None, None
        try:
            conn, cursor = DBManager.create_connect_db(self._db_path)
            if params:
                df = pd.read_sql(sql, conn, params=params)
            else:
                df = pd.read_sql(sql, conn)
            if df is None or df.empty:
                self.stack_map[name] = None
                return False
            self.stack_map[name] = df
            return True
        except Exception as e:
            logger.error("Error loading API stack data: %s", e)
            self.stack_map[name] = None
            return False
        finally:
            if conn and cursor:
                DBManager.destroy_db_connect(conn, cursor)
