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
from typing import Dict, List

from msprof_analyze.advisor.dataset.profiling.info_collection import TaskInfo
from msprof_analyze.advisor.dataset.profiling.profiling_parser import ProfilingParser

logger = get_logger()

AICPU_TASK_TYPE = "AI_CPU"
AICORE_TASK_TYPE = "AI_CORE"


class TaskTime(ProfilingParser):
    """
    task time info
    """
    FILE_PATTERN_MSG = "task_time*.json"
    FILE_INFO = "task time"

    file_pattern_list = [r"^task_time_[_\d]+\.json$"]

    def __init__(self, path: str) -> None:
        super().__init__(path)
        self._tasks: List[TaskInfo] = []
        self._aicore_tasks: List[TaskInfo] = []
        self._aicpu_tasks: List[TaskInfo] = []
        self._process_map: Dict[str, str] = {}
        self._pid_map: Dict[str, str] = {}

    def get_aicpu_tasks(self):
        """
        get aicpu tasks
        :return: aicpu tasks
        """
        return self._aicpu_tasks

    def get_aicore_tasks(self):
        """
        get aicore tasks
        :return: aicore tasks
        """
        return self._aicore_tasks

    def parse_from_file(self, file: str):
        if not self._parse_json(file):
            return False
        for item in self._raw_data:
            if item.get("ph") != "M":  # header
                continue
            if item.get("name") != "process_name":
                continue
            pid = item.get("pid")
            pname = item["args"]["name"]
            self._process_map[pid] = pname
            self._pid_map[pname] = pid
        for item in self._raw_data:
            if item.get("ph") == "M":  # header
                continue
            task = TaskInfo(item)
            self._tasks.append(task)
            if task.pid != self._pid_map.get("Task Scheduler"):
                continue
            if task.task_type == AICORE_TASK_TYPE:
                self._aicore_tasks.append(task)
            elif task.task_type == AICPU_TASK_TYPE:
                self._aicpu_tasks.append(task)
        self._aicore_tasks.sort(key=lambda x: x.start_time)
        self._aicpu_tasks.sort(key=lambda x: x.start_time)
        if not self._tasks:
            logger.error("No valid task info in %s", file)
            return False
        return True
