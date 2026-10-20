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
from msprof_analyze.compare_tools.compare_backend.utils.common_func import calculate_diff_ratio, convert_to_float
from msprof_analyze.compare_tools.compare_backend.utils.excel_config import ExcelConfig
from msprof_analyze.prof_common.constant import Constant


class KernelCompareInfo:
    __slots__ = ['_kernel_type', '_input_shapes', '_total_dur', '_number', '_max_dur', '_min_dur']

    def __init__(self, data_list: list):
        self._kernel_type = None
        self._input_shapes = None
        self._total_dur = None
        self._number = None
        self._max_dur = None
        self._min_dur = None
        if len(data_list) < 6:
            return
        self._kernel_type = data_list[0]
        self._input_shapes = data_list[1]
        self._total_dur = round(convert_to_float(data_list[2]), 2)
        self._number = data_list[3]
        self._max_dur = round(convert_to_float(data_list[4]), 2)
        self._min_dur = round(convert_to_float(data_list[5]), 2)

    @property
    def kernel_type(self):
        return self._kernel_type

    @property
    def input_shapes(self):
        return self._input_shapes

    @property
    def total_dur(self):
        return self._total_dur if self._total_dur else 0.0

    @property
    def number(self):
        return self._number

    @property
    def max_dur(self):
        return self._max_dur

    @property
    def min_dur(self):
        return self._min_dur

    @property
    def avg_dur(self):
        return round(self._total_dur / self._number, 2) if self._total_dur and self._number else 0.0


class KernelCompareBean:
    __slots__ = ['_base_kernel', '_comparison_kernel', '_kernel_type', '_input_shapes']
    TABLE_NAME = Constant.KERNEL_TABLE
    HEADERS = ExcelConfig.HEADERS.get(TABLE_NAME)
    OVERHEAD = ExcelConfig.OVERHEAD.get(TABLE_NAME)

    def __init__(self, base_kernel: list, comparison_kernel: list):
        self._base_kernel = KernelCompareInfo(base_kernel)
        self._comparison_kernel = KernelCompareInfo(comparison_kernel)
        self._kernel_type = (
            self._base_kernel.kernel_type if self._base_kernel.kernel_type else self._comparison_kernel.kernel_type
        )
        self._input_shapes = (
            self._base_kernel.input_shapes if self._base_kernel.input_shapes else self._comparison_kernel.input_shapes
        )

    @property
    def row(self):
        row = [
            None,
            self._kernel_type,
            self._input_shapes,
            self._base_kernel.total_dur,
            self._base_kernel.avg_dur,
            self._base_kernel.max_dur,
            self._base_kernel.min_dur,
            self._base_kernel.number,
            self._comparison_kernel.total_dur,
            self._comparison_kernel.avg_dur,
            self._comparison_kernel.max_dur,
            self._comparison_kernel.min_dur,
            self._comparison_kernel.number,
        ]
        diff_fields = [
            calculate_diff_ratio(self._base_kernel.total_dur, self._comparison_kernel.total_dur)[1],
            calculate_diff_ratio(self._base_kernel.avg_dur, self._comparison_kernel.avg_dur)[1],
        ]
        row.extend(diff_fields)
        return row
