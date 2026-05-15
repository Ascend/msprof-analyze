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

from msprof_analyze.prof_common.logger import get_logger
import os
from typing import Dict, List
import json
import pandas as pd

from msprof_analyze.prof_common.constant import Constant
from msprof_analyze.advisor.dataset.profiling.info_collection import TaskInfo
from msprof_analyze.advisor.dataset.profiling.profiling_parser import ProfilingParser

logger = get_logger()


class TaskChecker:
    """
    check task info
    """

    def __init__(self):
        self.sqe_keys = set()

    def is_sqe(self, task: TaskInfo) -> bool:
        """check sqe"""
        key = (task.pid, task.tid)
        if task.args.get('name', '').endswith('_SQE'):
            self.sqe_keys.add(key)
            return False

        return key in self.sqe_keys


class Msprof(ProfilingParser):
    """
    msprof

    """
    FILE_PATTERN_MSG = "msprof_*.json"
    FILE_INFO = "msprof"

    file_pattern_list = [r"^msprof[_\d]+.json$"]

    def __init__(self, path: str) -> None:
        super().__init__(path)
        self._tasks: List[TaskInfo] = []
        self._hccl_tasks: List[TaskInfo] = []
        self._iteration_time = 0.0
        self._model_id = None
        self._iteration_id = None
        self._process_pid: Dict[str, str] = {}
        self._min_time = 0.0
        self._max_time = 0.0
        self._data_process_time = 0.0
        self._start_point = 0.0

    def __len__(self):
        return len(self._tasks)

    @property
    def step_time(self):
        return self._iteration_time + self._data_process_time

    @property
    def iteration_time(self):
        return self._iteration_time

    @property
    def iter_max_time(self):
        return self._max_time

    @property
    def iter_min_time(self):
        return self._min_time

    @property
    def data_process_time(self):
        return self._data_process_time

    @property
    def tasks(self):
        return self._tasks

    @property
    def hccl_tasks(self):
        return self._hccl_tasks

    @property
    def model_id(self):
        return self._model_id

    @property
    def iteration_id(self):
        return self._iteration_id

    @property
    def process_pid(self):
        return self._process_pid

    @property
    def start_point(self):
        return self._start_point

    def parse_from_file(self, file: str):
        if not self._parse_json(file):
            return False
        min_time = float('inf')
        max_time = 0.0
        task_checker = TaskChecker()
        is_iter = False
        self._tasks = [None] * len(self._raw_data)
        task_index = 0
        for item in self._raw_data:
            task = TaskInfo(item)
            if task.cat == "Iteration Time":
                self._min_time = task.start_time
                self._max_time = task.end_time
                self._iteration_time = task.dur
                is_iter = True
            if task.cat == "Data_aug Bound" and "Data_aug Bound(us)" in task.args:
                self._data_process_time = task.args["Data_aug Bound(us)"]

            if self._start_point == 0 and task.start_time > 0:
                self._start_point = task.start_time

            if task_checker.is_sqe(task):
                continue

            self._tasks[task_index] = task
            task_index += 1
            self._parse_task(task)

            start_time = task.start_time
            dur = task.dur
            if start_time == -1 or dur == -1 or dur == 0:
                continue
            if start_time < min_time:
                min_time = start_time
            end_time = start_time + dur
            if end_time > max_time:
                max_time = end_time
        if not is_iter:
            self._iteration_time = dur
            self._max_time = max_time
            self._min_time = min_time
        self._tasks = self._tasks[:task_index]
        if self._tasks:
            self._tasks.sort(key=lambda x: x.start_time)
            return True
        return False

    def _parse_task(self, task):
        if "Iteration Refresh" in task.name:
            self._iteration_id = task.args.get("Iteration ID")
        elif "Model ID" in task.name:
            self._model_id = int(task.name.split(":")[1])
        elif "process_name" == task.name:
            self._process_pid[task.args.get("name")] = task.pid


class MsprofDB(Msprof):
    FILE_PATTERN_MSG = "ascend_*_profiler.db"
    FILE_INFO = "timeline info from db"

    file_pattern_list = [r'^ascend_pytorch_profiler(?:_\d+)?\.db$',
                         r'^ascend_mindspore_profiler(?:_\d+)?\.db$',
                         r'^msprof_\d{14}\.db$']

    HCCL_TASK_SQL = """
    SELECT
      str.value as name,
      task.globalPid as pid,
      task.startNs / 1000.0 as ts,
      (task.endNs - task.startNs) / 1000.0 as dur,
      JSON_OBJECT(
          'task type', str.value,
          'stream id', task.streamId,
          'task id', task.taskId,
          'transport type', trans.name,
          'link type', link.name,
          'size(Byte)', comm.size
      ) as args
      
    FROM COMMUNICATION_TASK_INFO as comm 
    JOIN TASK as task ON comm.globalTaskId = task.globalTaskId
    JOIN STRING_IDS as str ON str.id = comm.taskType
    JOIN ENUM_HCCL_LINK_TYPE as link ON link.id = comm.linkType
    JOIN ENUM_HCCL_TRANSPORT_TYPE as trans ON trans.id = comm.transportType
    """

    HCCL_OP_SQL = """
    SELECT
        str.value as name,
        comm.startNs / 1000.0 as ts,
        (comm.endNs - comm.startNs) / 1000.0 as dur
    FROM COMMUNICATION_OP as comm 
    JOIN STRING_IDS as str ON str.id = comm.opName
    """

    NODE_INFO_SQL = """
    WITH ranked_apis AS (
        SELECT 
            str.value AS name,
            api.startNs / 1000.0 AS ts,
            (api.endNs - api.startNs) / 1000.0 AS dur,
            type.name as type,
            LAG(str.value) OVER (ORDER BY api.startNs) AS prev_name
        FROM CANN_API as api
        JOIN STRING_IDS as str ON api.name = str.id
        JOIN ENUM_API_TYPE as type ON api.type = type.id
    )
    SELECT 
        name,
        ts,
        dur,
        json_object('item_id', prev_name) AS args
    FROM ranked_apis
    WHERE type = 'node'
    ORDER BY ts;
    """

    def __init__(self, path: str) -> None:
        super().__init__(path)

    def parse_from_file(self, file: str):
        if not file or not os.path.exists(file):
            logger.error("db path is None.")
            return False
        self.process_communication_tasks(file)
        self.process_node_tasks(file)
        return True

    def process_communication_tasks(self, db_path):
        self._process_task_data(db_path, self.HCCL_TASK_SQL, self._hccl_tasks, [Constant.TABLE_COMMUNICATION_TASK_INFO])
        self._process_task_data(db_path, self.HCCL_OP_SQL, self._hccl_tasks, [Constant.TABLE_COMMUNICATION_OP])
        self._hccl_tasks.sort(key=lambda x: x.start_time)

    def process_node_tasks(self, db_path):
        self._process_task_data(db_path, self.NODE_INFO_SQL, self._tasks)

    def _process_task_data(self, db_path, sql: str, result: list, tables_to_check=None):
        df = self._execute_sql(db_path, sql, tables_to_check)
        if df.empty:
            return
        if 'args' in df.columns:
            df['args'] = df['args'].apply(lambda x: json.loads(x) if pd.notna(x) else {})
        result.extend([TaskInfo(record) for record in df.to_dict('records')])



