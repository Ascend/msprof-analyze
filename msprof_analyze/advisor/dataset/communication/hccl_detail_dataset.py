# Copyright (c) 2024, Huawei Technologies Co., Ltd.
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
from msprof_analyze.prof_common.logger import get_logger
from typing import List
from msprof_analyze.prof_common.singleton import singleton
from msprof_analyze.advisor.common.profiling.msprof import Msprof
from msprof_analyze.advisor.dataset.profiling.info_collection import TaskInfo, HcclOp, HcclTask

logger = get_logger()


@singleton
class HcclDetailDataset:
    RANK = "rank"

    def __init__(self, timeline_dataset: Msprof, **kwargs) -> None:
        self.step = kwargs.get("step")
        self._hccl_pid = -1
        self._current_hccl_op = None
        self._hccl_ops: List[HcclOp] = []
        self._parse(timeline_dataset)

    @property
    def hccl_ops(self):
        return self._hccl_ops

    @staticmethod
    def _get_hccl_pid(tasks: List[TaskInfo]):
        for task in tasks:
            if task.name == "process_name" and hasattr(task, "args") \
                    and task.args.get("name", None) in ["Communication", "HCCL"]:
                return task.pid
        return -1

    @staticmethod
    def _get_tasks(timeline_dataset: Msprof):
        if hasattr(timeline_dataset, 'tasks'):
            return timeline_dataset.tasks
        return []

    @classmethod
    def get_key(cls):
        """
        get key of dataset
        :return: key
        """
        return cls.__module__.rsplit('.', maxsplit=1)[-1]

    def _parse(self, timeline_dataset: Msprof):
        hccl_tasks = self._get_hccl_tasks(timeline_dataset)
        if not hccl_tasks:
            return
        self._process(hccl_tasks)

    def _get_hccl_tasks(self, timeline_dataset: Msprof):
        if timeline_dataset.hccl_tasks:
            return timeline_dataset.hccl_tasks
        tasks = self._get_tasks(timeline_dataset)
        self._hccl_pid = self._get_hccl_pid(tasks)
        if self._hccl_pid == -1:
            return []
        return [task for task in tasks if task.pid == self._hccl_pid]

    def _process(self, hccl_tasks: List[TaskInfo]):
        task_handlers = {
            "hcom": lambda sub_task: self._start_new_hccl_op(sub_task),
            "Reduce": lambda sub_task: self._add_reduce_inline(sub_task),
            "Memcpy": lambda sub_task: self._add_memcpy(sub_task)
        }

        for task in hccl_tasks:
            handler = task_handlers.get(task.name.split('_')[0])
            result = handler(task) if handler else None
            if result is not None:
                self._current_hccl_op = result

        if self._current_hccl_op:
            self._hccl_ops.append(self._current_hccl_op)

    def _start_new_hccl_op(self, task: TaskInfo):
        if self._current_hccl_op:
            self._hccl_ops.append(self._current_hccl_op)
        return HcclOp(task)

    def _add_reduce_inline(self, task: TaskInfo):
        if self._current_hccl_op:
            self._current_hccl_op.reduce_inline_tasks.append(HcclTask(task))

    def _add_memcpy(self, task: TaskInfo):
        if self._current_hccl_op:
            self._current_hccl_op.memcpy_tasks.append(HcclTask(task))
