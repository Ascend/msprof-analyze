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
from msprof_analyze.prof_common.constant import Constant


class KernelTypeCompareBean:
    TABLE_NAME = Constant.KERNEL_TYPE_TABLE
    HEADERS = ExcelConfig.HEADERS.get(TABLE_NAME)
    OVERHEAD = ExcelConfig.OVERHEAD.get(TABLE_NAME)

    def __init__(self, base_kernel, comparison_kernel):
        self._base_kernel = base_kernel
        self._comparison_kernel = comparison_kernel

    @property
    def row(self):
        kernel_type = self._base_kernel.kernel_type or self._comparison_kernel.kernel_type
        core_type = self._base_kernel.core_type or self._comparison_kernel.core_type
        return [
            None,
            kernel_type,
            core_type,
            self._base_kernel.total_dur,
            self._base_kernel.avg_dur,
            self._base_kernel.max_dur,
            self._base_kernel.min_dur,
            self._base_kernel.calls,
            self._comparison_kernel.total_dur,
            self._comparison_kernel.avg_dur,
            self._comparison_kernel.max_dur,
            self._comparison_kernel.min_dur,
            self._comparison_kernel.calls,
            calculate_diff_ratio(self._base_kernel.total_dur, self._comparison_kernel.total_dur)[1],
            calculate_diff_ratio(self._base_kernel.avg_dur, self._comparison_kernel.avg_dur)[1],
        ]
