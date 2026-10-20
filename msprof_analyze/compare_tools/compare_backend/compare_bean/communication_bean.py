# -------------------------------------------------------------------------
# This file is part of the MindStudio project.
# Copyright (c) 2024 Huawei Technologies Co.,Ltd.
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
from msprof_analyze.compare_tools.compare_backend.utils.excel_config import ExcelConfig
from msprof_analyze.compare_tools.compare_backend.utils.common_func import calculate_diff_ratio
from msprof_analyze.prof_common.constant import Constant


class CommunicationInfo:
    __slots__ = ['comm_op_name', 'task_name', 'calls', 'total_duration', 'avg_duration', 'max_duration', 'min_duration']

    def __init__(self, name: str, data_list: list, is_task: bool):
        self.comm_op_name = None
        self.task_name = None
        self.calls = None
        self.total_duration = 0
        self.avg_duration = None
        self.max_duration = None
        self.min_duration = None
        if data_list:
            self.comm_op_name = "|" if is_task else name
            self.task_name = name if is_task else None
            self.calls = len(data_list)
            self.total_duration = sum(data_list)
            self.avg_duration = sum(data_list) / len(data_list)
            self.max_duration = max(data_list)
            self.min_duration = min(data_list)


class CommunicationBean:
    __slots__ = ['_name', '_base_comm', '_comparison_comm']
    TABLE_NAME = Constant.COMMUNICATION_TABLE
    HEADERS = ExcelConfig.HEADERS.get(TABLE_NAME)
    OVERHEAD = ExcelConfig.OVERHEAD.get(TABLE_NAME)

    def __init__(self, name: str, base_comm_data: dict, comparison_comm_data: dict):
        self._name = name
        self._base_comm = base_comm_data
        self._comparison_comm = comparison_comm_data

    @property
    def rows(self):
        rows = []
        base_comm = CommunicationInfo(self._name, self._base_comm.get("comm_list", []), is_task=False)
        comparison_comm = CommunicationInfo(self._name, self._comparison_comm.get("comm_list", []), is_task=False)
        rows.append(self._get_row(base_comm, comparison_comm, is_task=False))

        base_task = self._base_comm.get("comm_task", {})
        comparison_task = self._comparison_comm.get("comm_task", {})
        if not base_task and not comparison_task:
            return rows

        for task_name, task_list in base_task.items():
            base_task_info = CommunicationInfo(task_name, task_list, is_task=True)
            comparison_task_info = CommunicationInfo("", [], is_task=True)
            for _task_name, _task_list in comparison_task.items():
                comparison_task_info = CommunicationInfo(_task_name, _task_list, is_task=True)
                comparison_task.pop(_task_name, None)
                break
            rows.append(self._get_row(base_task_info, comparison_task_info, is_task=True))
        for task_name, task_list in comparison_task.items():
            base_task_info = CommunicationInfo("", [], is_task=True)
            comparison_task_info = CommunicationInfo(task_name, task_list, is_task=True)
            rows.append(self._get_row(base_task_info, comparison_task_info, is_task=True))

        return rows

    @classmethod
    def _get_row(cls, base_info: CommunicationInfo, comparison_info: CommunicationInfo, is_task: bool) -> list:
        row = [
            None,
            base_info.comm_op_name,
            base_info.task_name,
            base_info.calls,
            base_info.total_duration,
            base_info.avg_duration,
            base_info.max_duration,
            base_info.min_duration,
            comparison_info.comm_op_name,
            comparison_info.task_name,
            comparison_info.calls,
            comparison_info.total_duration,
            comparison_info.avg_duration,
            comparison_info.max_duration,
            comparison_info.min_duration,
        ]
        diff_fields = (
            [None, None] if is_task else calculate_diff_ratio(base_info.total_duration, comparison_info.total_duration)
        )
        row.extend(diff_fields)
        return row
