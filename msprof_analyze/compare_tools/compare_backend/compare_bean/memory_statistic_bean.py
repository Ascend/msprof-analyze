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
from msprof_analyze.compare_tools.compare_backend.utils.common_func import calculate_diff_ratio
from msprof_analyze.compare_tools.compare_backend.utils.tree_builder import TreeBuilder
from msprof_analyze.compare_tools.compare_backend.utils.excel_config import ExcelConfig
from msprof_analyze.prof_common.constant import Constant


class MemoryStatisticBean:
    __slots__ = ['_name', '_base_info', '_comparison_info']
    TABLE_NAME = Constant.MEMORY_TOP_TABLE
    HEADERS = ExcelConfig.HEADERS.get(TABLE_NAME)
    OVERHEAD = ExcelConfig.OVERHEAD.get(TABLE_NAME)

    def __init__(self, name: str, base_data: list, comparison_data: list):
        self._name = name
        self._base_info = MemoryStatisticInfo(base_data)
        self._comparison_info = MemoryStatisticInfo(comparison_data)

    @property
    def row(self):
        row = [
            None,
            self._name,
            self._base_info.duration_ms,
            self._base_info.size_mb,
            self._base_info.number,
            self._comparison_info.duration_ms,
            self._comparison_info.size_mb,
            self._comparison_info.number,
        ]
        diff_fields = calculate_diff_ratio(self._base_info.size_mb, self._comparison_info.size_mb)
        row.extend(diff_fields)
        return row


class MemoryStatisticInfo:
    __slots__ = ['_data_list', 'duration_ms', 'size_mb', 'number']

    def __init__(self, data_list: list):
        self._data_list = data_list
        self.duration_ms = 0
        self.size_mb = 0
        self.number = len(data_list)
        self._get_info()

    def _get_info(self):
        for op_data in self._data_list:
            memory_list = TreeBuilder.get_total_memory(op_data)
            self.duration_ms += sum(memory.duration / Constant.US_TO_MS for memory in memory_list)
            self.size_mb += sum(memory.size / Constant.KB_TO_MB for memory in memory_list)
