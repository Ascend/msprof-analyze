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

import os

import pandas as pd

from msprof_analyze.prof_exports.base_stats_export import BaseStatsExport
from msprof_analyze.prof_common.constant import Constant
from msprof_analyze.prof_common.db_manager import DBManager
from msprof_analyze.prof_common.logger import get_logger
from msprof_analyze.cluster_analyse.common_func.table_constant import TableConstant

logger = get_logger()


QUERY_API_STATISTIC_SQL = """
SELECT
    STRING_IDS.value AS "API Name",
    SUM(TASK.endNs - TASK.startNs) AS "Total Time(ns)",
    COUNT(*) AS "Count",
    AVG(TASK.endNs - TASK.startNs) AS "Avg Time(ns)",
    MIN(TASK.endNs - TASK.startNs) AS "Min Time(ns)",
    MAX(TASK.endNs - TASK.startNs) AS "Max Time(ns)"
FROM CANN_API
JOIN STRING_IDS ON CANN_API.name = STRING_IDS.id
JOIN TASK ON CANN_API.connectionId = TASK.connectionId
GROUP BY STRING_IDS.value
ORDER BY "Total Time(ns)" DESC
"""


class ApiStatisticExport(BaseStatsExport):
    def __init__(self, db_path, recipe_name, param_dict=None):
        super().__init__(db_path, recipe_name, param_dict)
        self._query = QUERY_API_STATISTIC_SQL

    def get_param_order(self):
        return []


COMPUTE_INFO_SQL = """
WITH compute_info AS (
    SELECT 
        (SELECT value FROM STRING_IDS WHERE id = t.name) AS op_name,
        t.globalTaskId,
        {block_dim_state}
        (SELECT value FROM STRING_IDS WHERE id = t.opType) AS op_type,
        (SELECT value FROM STRING_IDS WHERE id = t.taskType) AS task_type,
        (SELECT value FROM STRING_IDS WHERE id = t.inputFormats) AS input_formats,
        (SELECT value FROM STRING_IDS WHERE id = t.inputShapes) AS input_shapes,
        (SELECT value FROM STRING_IDS WHERE id = t.inputDataTypes) AS input_data_types,
        (SELECT value FROM STRING_IDS WHERE id = t.outputShapes) AS output_shapes,
        (SELECT value FROM STRING_IDS WHERE id = t.outputFormats) AS output_formats,
        (SELECT value FROM STRING_IDS WHERE id = t.outputDataTypes) AS output_data_types
        {op_state}
    FROM 
        COMPUTE_TASK_INFO t
)
SELECT
    compute_info.*,
    task.startNs as task_start_time,
    task.endNs as task_end_time,
    task.endNs - task.startNs as task_duration,
    task.deviceId as device_id,
    task.modelId as model_id,
    task.streamId as stream_id,
    task.contextId as context_id,
    task.taskId as task_id
FROM 
    compute_info
JOIN 
    TASK as task ON compute_info.globalTaskId = task.globalTaskId;
"""

SELECT_OP_STATE = """,
        (SELECT value FROM STRING_IDS WHERE id = t.opState) AS op_state
"""

PMU_SQL = """
SELECT
    pmu.globalTaskId,
    str.value as name,
    pmu.value
FROM TASK_PMU_INFO AS pmu
JOIN STRING_IDS AS str ON str.id = pmu.name
"""

COMMUNICATION_INFO_SQL = """
WITH comm_info AS (
    SELECT 
        (SELECT value FROM STRING_IDS WHERE id = c.opName) AS op_name,
        (SELECT value FROM STRING_IDS WHERE id = c.opType) AS op_type,
        startNs as task_start_time,
        endNs as task_end_time,
        endNs - startNs as task_duration,
        connectionId
    FROM 
        COMMUNICATION_OP c
)
SELECT 
    comm.*,
    t.deviceId as device_id,
    t.modelId as model_id,
    'COMMUNICATION' as task_type
FROM 
    comm_info comm
JOIN (
    SELECT 
        connectionId,
        deviceId,
        modelId
    FROM TASK
    GROUP BY connectionId
    HAVING COUNT(DISTINCT deviceId) = 1 AND COUNT(DISTINCT modelId) = 1
) t ON comm.connectionId = t.connectionId
"""

COMMUNICATION_SCHEDULE_SQL = """
SELECT
    (SELECT value FROM STRING_IDS WHERE id = CSTI.name) AS op_name,
    (SELECT value FROM STRING_IDS WHERE id = CSTI.opType) AS op_type,
    (SELECT value FROM STRING_IDS WHERE id = CSTI.taskType) AS task_type,
    task.startNs as task_start_time,
    task.endNs as task_end_time,
    task.endNs - task.startNs as task_duration,
    task.deviceId as device_id,
    task.modelId as model_id,
    task.streamId as stream_id,
    task.contextId as context_id,
    task.taskId as task_id
FROM COMMUNICATION_SCHEDULE_TASK_INFO as CSTI 
JOIN TASK as task ON task.globalTaskId = CSTI.globalTaskId
"""


class KernelDetailsExport:
    COLUMN_BLOCK_NUM = "blockNum"

    def __init__(self, db_path, recipe_name, param_dict=None):
        self._db_path = db_path
        self._recipe_name = recipe_name
        self._param_dict = param_dict
        self.has_op_state = False

    def read_export_db(self):
        try:
            if not self._db_path:
                logger.error("db path is None.")
                return None
            if not os.path.exists(self._db_path):
                logger.error(f"Db file does not exist: {self._db_path}")
                return None

            compute_df = self._export_compute_task()
            communication_df = self._execute_sql(COMMUNICATION_INFO_SQL, [Constant.TABLE_COMMUNICATION_OP])
            comm_schedule_df = self._execute_sql(COMMUNICATION_SCHEDULE_SQL,
                                                 [Constant.TABLE_COMMUNICATION_SCHEDULE_TASK_INFO])

            if compute_df.empty and communication_df.empty and comm_schedule_df.empty:
                logger.warning(f"No compute and communication operators in db: {self._db_path}")
                return None

            total_df = self._post_process([compute_df, communication_df, comm_schedule_df])
            return total_df

        except Exception as e:
            logger.error(f"File {self._db_path} read failed error: {e}")
            return None

    def _export_compute_task(self):
        if self._check_table_column_exists(Constant.TABLE_COMPUTE_TASK_INFO, TableConstant.OP_STATE):
            op_state = SELECT_OP_STATE
            self.has_op_state = True
        else:
            op_state = ""
            self.has_op_state = False

        if self._check_table_column_exists(Constant.TABLE_COMPUTE_TASK_INFO, self.COLUMN_BLOCK_NUM):
            block_dim_state = """
            t.blockNum AS block_dim,
            t.mixBlockNum AS mix_block_dim,
            """
        else:
            block_dim_state = """
            t.blockDim AS block_dim,
            t.mixBlockDim AS mix_block_dim,
            """

        comp_info_sql = COMPUTE_INFO_SQL.format(
            op_state=op_state,
            block_dim_state=block_dim_state
        )

        basic_df = self._execute_sql(comp_info_sql, [Constant.TABLE_COMPUTE_TASK_INFO])
        pmu_df = self._execute_sql(PMU_SQL, [Constant.TABLE_TASK_PMU_INFO])

        if basic_df.empty or pmu_df.empty:
            return basic_df

        pivoted_pmu_df = pmu_df.pivot_table(
            index='globalTaskId',
            columns='name',
            values='value',
            aggfunc='first'
        ).reset_index()

        compute_df = basic_df.merge(pivoted_pmu_df, on='globalTaskId', how='left').fillna(0)
        return compute_df

    def _post_process(self, df_list):
        total_df = pd.concat(df_list, ignore_index=True).sort_values(by='task_start_time')
        total_df = total_df.fillna('N/A')

        total_df['task_wait_time'] = total_df['task_end_time'] - total_df['task_start_time'].shift(1)
        total_df.loc[0, 'task_wait_time'] = 0

        time_cols = [col for col in total_df.columns.tolist() if 'time' in col]
        time_cols.append('task_duration')
        for col in time_cols:
            total_df[col] = total_df[col].apply(lambda x: x / 1000 if x != 'N/A' else x)

        total_df = total_df.rename(columns={'aiv_total_time': 'aiv_time', 'aic_total_time': 'aicore_time'},
                                   errors='ignore')
        total_df = total_df.drop(columns=['task_end_time', 'globalTaskId', 'connectionId'], errors='ignore')
        return total_df

    def _check_table_column_exists(self, table_name, column_name):
        if not os.path.exists(self._db_path):
            logger.error(f"Db file does not exist: {self._db_path}")
            return False
        conn, cursor = DBManager.create_connect_db(self._db_path, Constant.ANALYSIS)
        if not conn:
            return False
        try:
            query = f"PRAGMA table_info({table_name})"
            cursor.execute(query)
            columns = cursor.fetchall()
            for col in columns:
                if col[1] == column_name:
                    return True
            return False
        finally:
            DBManager.destroy_db_connect(conn, cursor)

    def _execute_sql(self, query, required_tables=None):
        if not os.path.exists(self._db_path):
            logger.error(f"Db file does not exist: {self._db_path}")
            return pd.DataFrame()
        conn, cursor = DBManager.create_connect_db(self._db_path, Constant.ANALYSIS)
        if not conn:
            return pd.DataFrame()
        try:
            if required_tables:
                for table in required_tables:
                    cursor.execute(f"SELECT name FROM sqlite_master WHERE type='table' AND name='{table}'")
                    if not cursor.fetchone():
                        logger.warning(f"Table {table} not found in {self._db_path}")
                        return pd.DataFrame()

            data = pd.read_sql(query, conn)
            return data
        except Exception as e:
            logger.error(f"Failed to execute SQL: {e}")
            return pd.DataFrame()
        finally:
            DBManager.destroy_db_connect(conn, cursor)
