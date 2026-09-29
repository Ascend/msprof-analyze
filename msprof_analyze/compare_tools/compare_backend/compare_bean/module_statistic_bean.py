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
import re

from msprof_analyze.compare_tools.compare_backend.utils.common_func import calculate_diff_ratio
from msprof_analyze.compare_tools.compare_backend.utils.excel_config import ExcelConfig
from msprof_analyze.prof_common.constant import Constant


class ModuleStatisticBean:
    __slots__ = ['_module_name', '_module_class', '_module_level', '_base_info', '_comparison_info']
    TABLE_NAME = Constant.MODULE_TOP_TABLE
    HEADERS = ExcelConfig.HEADERS.get(TABLE_NAME)
    OVERHEAD = ExcelConfig.OVERHEAD.get(TABLE_NAME)

    def __init__(self, name: str, base_data: list, comparison_data: list):
        self._module_name = name.replace("nn.Module:", "")
        pattern = re.compile('_[0-9]+$')
        self._module_class = pattern.sub('', name.split("/")[-1])
        self._module_level = name.count("/")
        self._base_info = ModuleStatisticInfo(base_data)
        self._comparison_info = ModuleStatisticInfo(comparison_data)

    @property
    def rows(self):
        rows = [self.get_total_row()]
        rows.extend(self.get_detail_rows())
        return rows

    @staticmethod
    def _get_kernel_detail_rows(base_kernel_dict, com_kernel_dict):
        base_kernel_detals = ""
        com_kernel_details = ""
        for kernel_name, base_dur_list in base_kernel_dict.items():
            base_dur = "%.3f" % sum(base_dur_list)
            base_kernel_detals += f"{kernel_name}, [number: {len(base_dur_list)}], [duration_ms: {base_dur}]\n"
        for kernel_name, com_dur_list in com_kernel_dict.items():
            com_dur = "%.3f" % sum(com_dur_list)
            com_kernel_details += f"{kernel_name}, [number: {len(com_dur_list)}], [duration_ms: {com_dur}]\n"
        return [base_kernel_detals, com_kernel_details]

    def get_total_row(self):
        total_diff, total_ratio = calculate_diff_ratio(
            self._base_info.device_total_dur_ms, self._comparison_info.device_total_dur_ms
        )
        self_diff, _ = calculate_diff_ratio(
            self._base_info.device_self_dur_ms, self._comparison_info.device_self_dur_ms
        )
        row = [
            None,
            self._module_class,
            self._module_level,
            self._module_name,
            "[ TOTAL ]",
            None,
            self._base_info.device_self_dur_ms,
            self._base_info.number,
            self._base_info.device_total_dur_ms,
            None,
            self._comparison_info.device_self_dur_ms,
            self._comparison_info.number,
            self._comparison_info.device_total_dur_ms,
            total_diff,
            self_diff,
            total_ratio,
            self._base_info.call_stack,
            self._comparison_info.call_stack,
        ]
        return row

    def get_detail_rows(self):
        rows = []
        for op_name, base_dur_dict in self._base_info.api_dict.items():
            base_dur_list = base_dur_dict.get("total", [])
            com_dur_dict = self._comparison_info.api_dict.pop(op_name, {})
            com_dur_list = com_dur_dict.get("total", [])
            base_kernel_detals, com_kernel_details = self._get_kernel_detail_rows(
                base_dur_dict.get("detail", {}), com_dur_dict.get("detail", {})
            )
            self_diff, self_ratio = calculate_diff_ratio(sum(base_dur_list), sum(com_dur_list))
            row = [
                None,
                self._module_class,
                self._module_level,
                self._module_name,
                op_name,
                base_kernel_detals,
                sum(base_dur_list),
                len(base_dur_list),
                None,
                com_kernel_details,
                sum(com_dur_list),
                len(com_dur_list),
                None,
                None,
                self_diff,
                self_ratio,
                None,
                None,
            ]
            rows.append(row)

        for op_name, com_dur_dict in self._comparison_info.api_dict.items():
            com_dur_list = com_dur_dict.get("total", [])
            base_kernel_detals, com_kernel_details = self._get_kernel_detail_rows({}, com_dur_dict.get("detail", {}))
            self_diff, self_ratio = calculate_diff_ratio(0, sum(com_dur_list))
            row = [
                None,
                self._module_class,
                self._module_level,
                self._module_name,
                op_name,
                base_kernel_detals,
                0,
                0,
                None,
                com_kernel_details,
                sum(com_dur_list),
                len(com_dur_list),
                None,
                None,
                self_diff,
                self_ratio,
                None,
                None,
            ]
            rows.append(row)
        return rows


class ModuleStatisticInfo:
    __slots__ = ['_data_list', 'device_self_dur_ms', 'device_total_dur_ms', 'call_stack', 'number', 'api_dict']

    def __init__(self, data_list: list):
        self._data_list = data_list
        self.device_self_dur_ms = 0
        self.device_total_dur_ms = 0
        self.call_stack = ""
        self.number = len(data_list)
        self.api_dict = {}
        self._get_info()

    def _get_info(self):
        if self._data_list:
            self.call_stack = self._data_list[0].call_stack
        for module in self._data_list:
            self.device_self_dur_ms += module.device_self_dur / Constant.US_TO_MS
            self.device_total_dur_ms += module.device_total_dur / Constant.US_TO_MS
            for torch_op in module.toy_layer_api_list:
                self.api_dict.setdefault(torch_op.name, {}).setdefault("total", []).append(
                    torch_op.device_dur / Constant.US_TO_MS
                )
                for kernel in torch_op.kernel_list:
                    self.api_dict.setdefault(torch_op.name, {}).setdefault("detail", {}).setdefault(
                        kernel.kernel_name, []
                    ).append(kernel.device_dur / Constant.US_TO_MS)
