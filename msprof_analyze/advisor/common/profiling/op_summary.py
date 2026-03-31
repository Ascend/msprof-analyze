#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# Copyright (C) 2024-2024. Huawei Technologies Co., Ltd. All rights reserved.
# Licensed under the Apache License, Version 2.0 (the "License");
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

import logging
import os
from abc import abstractmethod
from decimal import Decimal
from typing import List, Any
import pandas as pd

from msprof_analyze.cluster_analyse.common_func.table_constant import TableConstant
from msprof_analyze.prof_common.constant import Constant
from msprof_analyze.advisor.dataset.profiling.info_collection import OpInfo
from msprof_analyze.advisor.dataset.profiling.profiling_parser import ProfilingParser
from msprof_analyze.advisor.utils.utils import format_excel_title, lazy_property

logger = logging.getLogger()


class OpSummaryBase(ProfilingParser):
    FILE_PATTERN_MSG = "op_summary file pattern"
    FILE_INFO = "op summary"
    STATIC_OP_STATE = "static"
    DYNAMIC_OP_STATE = "dynamic"

    file_pattern_list = []

    def __init__(self, path: str) -> None:
        super().__init__(path)
        self.op_list: List[OpInfo] = []
        self._total_task_duration = 0.0
        self._total_task_wait_time = 0.0

    @abstractmethod
    def parse_from_file(self, file: str):
        return False

    @abstractmethod
    def get_static_shape_operators(self):
        return False

    @abstractmethod
    def contains_op_state_info(self):
        return False

    def get_total_task_duration(self):
        """
        get total task duration of all operators
        :return:
        """
        return self._total_task_duration

    @lazy_property
    def task_dict(self):
        """
        task dict
        """
        task_dict = {}
        for op_info in self.op_list:
            if op_info.op_name not in task_dict:
                task_dict[op_info.op_name] = [op_info]
            else:
                task_dict[op_info.op_name].append(op_info)

        return task_dict


class OpSummary(OpSummaryBase):
    """
    op summary
    """
    FILE_PATTERN_MSG = "op_summary_*.csv"
    FILE_INFO = "op summary from text"
    file_pattern_list = [r"^op_summary_[_\d]+\.csv$"]

    def __init__(self, path: str) -> None:
        super().__init__(path)
        self._raw_data: List[List[str]] = []

    def parse_from_file(self, file: str):
        if not self._parse_csv(file):
            return False
        title_dict = dict(enumerate(self._raw_data[0]))
        for op_data in self._raw_data[1:]:
            op_info = OpInfo()
            for idx, value in enumerate(op_data):
                title = title_dict.get(idx, "")
                formatted_title = format_excel_title(title)
                if formatted_title == 'task_start_time' and 'us' in title and \
                        value.replace('.', '').replace("E+", "").isnumeric():
                    value = str(Decimal(value) * Decimal(1000))
                op_info.add_attr(formatted_title, value)
            self.op_list.append(op_info)
            self._total_task_duration += self.get_float(op_info.get_attr("task_duration"))
            self._total_task_wait_time += self.get_float(op_info.get_attr("task_wait_time"))
        if not self.op_list:
            logger.error("No valid op info in %s", file)
            return False
        return True

    def get_static_shape_operators(self) -> List[Any]:
        return [op_info.get_attr("op_name")
                for op_info in self.op_list if op_info.get_attr("op_state") == self.STATIC_OP_STATE]

    def contains_op_state_info(self):
        return True


class OpSummaryDB(OpSummaryBase):
    FILE_PATTERN_MSG = "ascend_*_profiler.db"
    FILE_INFO = "op summary from db"
    COLUMN_BLOCK_NUM = "blockNum"

    file_pattern_list = [r'^ascend_pytorch_profiler(?:_\d+)?\.db$',
                         r'^ascend_mindspore_profiler(?:_\d+)?\.db$',
                         r'^msprof_\d{14}\.db$']

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

    def __init__(self, path: str) -> None:
        super().__init__(path)
        self.has_op_state = False

    def parse_from_file(self, file: str):
        if not file or not os.path.exists(file):
            logger.error("db path is None.")
            return False
        # export data
        compute_df = self.export_compute_task(file)
        communication_df = self._execute_sql(file, self.COMMUNICATION_INFO_SQL, [Constant.TABLE_COMMUNICATION_OP])
        comm_schedule_df = self._execute_sql(file, self.COMMUNICATION_SCHEDULE_SQL,
                                             [Constant.TABLE_COMMUNICATION_SCHEDULE_TASK_INFO])
        if compute_df.empty and communication_df.empty and comm_schedule_df.empty:
            logger.warning(f"No compute and communication operators in db: {file}")
            return False
        # post process
        total_df = self.post_process([compute_df, communication_df, comm_schedule_df])
        # calculate total
        self._total_task_duration = float(total_df['task_duration'].sum())
        self._total_task_wait_time = float(total_df['task_wait_time'].sum())
        # convert to op_list
        self.convert_to_op_info_list(total_df)
        return True

    def contains_op_state_info(self):
        return self.has_op_state

    def get_static_shape_operators(self) -> List[Any]:
        if not self.contains_op_state_info():
            return []
        return [op_info.get_attr("op_name")
                for op_info in self.op_list if op_info.get_attr("op_state") == self.STATIC_OP_STATE]


    def export_compute_task(self, db_path):
        # check whether opState in COMPUTE_TASK_INFO
        if self._check_table_column_exists(db_path, Constant.TABLE_COMPUTE_TASK_INFO, TableConstant.OP_STATE):
            op_state = self.SELECT_OP_STATE
            self.has_op_state = True
        else:
            op_state = ""
            self.has_op_state = False
        if self._check_table_column_exists(db_path, Constant.TABLE_COMPUTE_TASK_INFO, self.COLUMN_BLOCK_NUM):
            block_dim_state = """
            t.blockNum AS block_dim,
            t.mixBlockNum AS mix_block_dim,
            """
        else:
            block_dim_state = """
            t.blockDim AS block_dim,
            t.mixBlockDim AS mix_block_dim,
            """
        comp_info_sql = self.COMPUTE_INFO_SQL.format(
            op_state=op_state,
            block_dim_state=block_dim_state
        )
        # export basic compute_task_info, task_pmu_info
        basic_df = self._execute_sql(db_path, comp_info_sql, [Constant.TABLE_COMPUTE_TASK_INFO])
        pmu_df = self._execute_sql(db_path, self.PMU_SQL, [Constant.TABLE_TASK_PMU_INFO])
        if basic_df.empty or pmu_df.empty:
            return basic_df
        # join pmu info
        pivoted_pmu_df = pmu_df.pivot_table(
            index='globalTaskId',
            columns='name',
            values='value',
            aggfunc='first'  # 如果有多个值，取第一个
        ).reset_index()
        compute_df = basic_df.merge(pivoted_pmu_df, on='globalTaskId', how='left').fillna(0)
        return compute_df

    def export_communication_task(self, db_path):
        return self._execute_sql(db_path, self.COMMUNICATION_INFO_SQL)

    def post_process(self, df_list):
        # union compute and communication operator info
        total_df = pd.concat(df_list, ignore_index=True).sort_values(by='task_start_time')
        total_df = total_df.fillna('N/A')
        # calculate task_wait_time
        total_df['task_wait_time'] = total_df['task_end_time'] - total_df['task_start_time'].shift(1)
        total_df.loc[0, 'task_wait_time'] = 0
        # process time units
        time_cols = [col for col in total_df.columns.tolist() if 'time' in col]
        time_cols.append('task_duration')
        for col in time_cols:
            total_df[col] = total_df[col].apply(lambda x: Decimal(x) / 1000 if x != 'N/A' else x)
        # process columns
        total_df = total_df.rename(columns={'aiv_total_time': 'aiv_time', 'aic_total_time': 'aicore_time'},
                                   errors='ignore')
        total_df = total_df.drop(columns=['task_end_time', 'globalTaskId', 'connectionId'], errors='ignore')
        return total_df

    def convert_to_op_info_list(self, df):
        for row in df.itertuples(index=False):
            op_info = OpInfo()
            for col in df.columns:
                setattr(op_info, col, getattr(row, col))
            self.op_list.append(op_info)