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
from msprof_analyze.compare_tools.compare_backend.utils.common_func import (
    longest_common_subsequence_matching,
    calculate_diff_ratio,
)
from msprof_analyze.compare_tools.compare_backend.utils.excel_config import ExcelConfig
from msprof_analyze.compare_tools.compare_backend.utils.module_node import ModuleNode
from msprof_analyze.compare_tools.compare_backend.utils.name_function import NameFunction
from msprof_analyze.compare_tools.compare_backend.utils.torch_op_node import TorchOpNode
from msprof_analyze.prof_common.constant import Constant


class ModuleCompareBean:
    __slots__ = ['_base_module', '_comparison_module', 'module_class', 'module_level', 'module_name']
    TABLE_NAME = Constant.MODULE_TABLE
    HEADERS = ExcelConfig.HEADERS.get(TABLE_NAME)
    OVERHEAD = ExcelConfig.OVERHEAD.get(TABLE_NAME)

    def __init__(self, base_module: ModuleNode, comparison_module: ModuleNode):
        self._base_module = ModuleInfo(base_module)
        self._comparison_module = ModuleInfo(comparison_module)
        self.module_class = self._base_module.module_class if base_module else self._comparison_module.module_class
        self.module_level = self._base_module.module_level if base_module else self._comparison_module.module_level
        self.module_name = self._base_module.module_name if base_module else self._comparison_module.module_name

    @property
    def rows(self):
        return [self.get_total_row(), *self.get_detail_rows()]

    def get_total_row(self):
        total_diff, total_ratio = calculate_diff_ratio(
            self._base_module.device_total_time, self._comparison_module.device_total_time
        )
        self_diff, _ = calculate_diff_ratio(
            self._base_module.device_self_time, self._comparison_module.device_self_time
        )
        return [
            None,
            self.module_class,
            self.module_level,
            self.module_name,
            "TOTAL",
            None,
            self._base_module.device_self_time,
            self._base_module.device_total_time,
            "TOTAL",
            None,
            self._comparison_module.device_self_time,
            self._comparison_module.device_total_time,
            total_diff,
            self_diff,
            total_ratio,
            self._base_module.call_stack,
            self._comparison_module.call_stack,
        ]

    def get_detail_rows(self):
        rows = []
        matched_ops = longest_common_subsequence_matching(
            self._base_module.top_layer_ops, self._comparison_module.top_layer_ops, NameFunction.get_name
        )
        for base_op, comparison_op in matched_ops:
            base_op = OpInfo(base_op)
            comparison_op = OpInfo(comparison_op)
            self_diff, self_ratio = calculate_diff_ratio(base_op.device_self_time, comparison_op.device_self_time)
            base_call_stack = base_op.call_stack if self_diff > 0 else None
            comparison_call_stack = comparison_op.call_stack if self_diff > 0 else None
            rows.append(
                [
                    None,
                    self.module_class,
                    self.module_level,
                    self.module_name,
                    base_op.operator_name,
                    base_op.kernel_details,
                    base_op.device_self_time,
                    None,
                    comparison_op.operator_name,
                    comparison_op.kernel_details,
                    comparison_op.device_self_time,
                    None,
                    None,
                    self_diff,
                    self_ratio,
                    base_call_stack,
                    comparison_call_stack,
                ]
            )
        return rows


class ModuleInfo:
    __slots__ = [
        'module_class',
        'module_level',
        'module_name',
        'device_self_time',
        'device_total_time',
        'top_layer_ops',
        'call_stack',
    ]

    def __init__(self, module: ModuleNode):
        self.module_class = ""
        self.module_level = ""
        self.module_name = ""
        self.device_self_time = 0
        self.device_total_time = 0
        self.top_layer_ops = []
        self.call_stack = ""
        if module:
            self.module_class = module.module_class
            self.module_level = module.module_level
            self.module_name = module.module_name.replace("nn.Module:", "")
            self.device_self_time = module.device_self_dur
            self.device_total_time = module.device_total_dur
            self.top_layer_ops = module.toy_layer_api_list
            self.call_stack = module.call_stack


class OpInfo:
    __slots__ = ['operator_name', 'kernel_details', 'device_self_time', 'call_stack']

    def __init__(self, operator: TorchOpNode):
        self.operator_name = ""
        self.kernel_details = ""
        self.device_self_time = 0
        self.call_stack = ""
        if operator:
            self.operator_name = operator.name
            for kernel in operator.kernel_list:
                self.device_self_time += kernel.device_dur
                self.kernel_details += kernel.kernel_details
            self.call_stack = operator.call_stack
