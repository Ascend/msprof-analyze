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
from msprof_analyze.compare_tools.compare_backend.utils.excel_config import ExcelConfig
from msprof_analyze.compare_tools.compare_backend.utils.torch_op_node import TorchOpNode
from msprof_analyze.compare_tools.compare_backend.utils.tree_builder import TreeBuilder
from msprof_analyze.prof_common.constant import Constant


class MemoryCompareBean:
    __slots__ = ['_index', '_base_op', '_comparison_op']
    TABLE_NAME = Constant.MEMORY_TABLE
    HEADERS = ExcelConfig.HEADERS.get(TABLE_NAME)
    OVERHEAD = ExcelConfig.OVERHEAD.get(TABLE_NAME)

    def __init__(self, index: int, base_op: TorchOpNode, comparison_op: TorchOpNode):
        self._index = index
        self._base_op = MemoryInfo(base_op)
        self._comparison_op = MemoryInfo(comparison_op)

    @property
    def row(self):
        row = [
            self._index + 1,
            self._base_op.operator_name,
            self._base_op.input_shape,
            self._base_op.input_type,
            self._base_op.memory_details,
            self._base_op.size,
            self._comparison_op.operator_name,
            self._comparison_op.input_shape,
            self._comparison_op.input_type,
            self._comparison_op.memory_details,
            self._comparison_op.size,
        ]
        diff_fields = calculate_diff_ratio(self._base_op.size, self._comparison_op.size)
        row.extend(diff_fields)
        return row


class MemoryInfo:
    __slots__ = ['operator_name', 'input_shape', 'input_type', 'size', 'memory_details', '_memory_list']

    def __init__(self, torch_op: TorchOpNode):
        self.operator_name = None
        self.input_shape = None
        self.input_type = None
        self.size = 0
        self.memory_details = ""
        self._memory_list = []
        if torch_op:
            self.operator_name = torch_op.name
            self.input_shape = torch_op.input_shape
            self.input_type = torch_op.input_type
            self._memory_list = TreeBuilder.get_total_memory(torch_op)
        self._update_memory_fields()

    def _update_memory_fields(self):
        for memory in self._memory_list:
            self.size += memory.size
            self.memory_details += memory.memory_details
