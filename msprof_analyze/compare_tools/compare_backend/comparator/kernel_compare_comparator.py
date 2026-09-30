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
from msprof_analyze.compare_tools.compare_backend.comparator.base_comparator import BaseComparator
from msprof_analyze.compare_tools.compare_backend.utils.common_func import update_order_id
from msprof_analyze.prof_common.constant import Constant


class KernelCompareComparator(BaseComparator):
    def __init__(self, origin_data: list, bean: any):
        super().__init__(origin_data, bean)

    @classmethod
    def _aggregated_kernel_by_type_and_shape(cls, kernels: dict):
        result_dict = {}
        for type_shape, shape_values in kernels.items():
            for shape, kernel_data in shape_values.items():
                kernel = [single[1] for single in kernel_data]
                result_list = [type_shape, shape, sum(kernel), len(kernel), max(kernel), min(kernel)]
                result_dict.setdefault(f"{type_shape}{shape}", []).extend(result_list)
        return result_dict

    def _compare(self):
        if not self._origin_data:
            return
        base_kernels = self._origin_data.get(Constant.BASE_DATA, {})
        comparison_kernels = self._origin_data.get(Constant.COMPARISON_DATA, {})
        if not base_kernels or not comparison_kernels:
            return
        base_aggregated_kernels = self._aggregated_kernel_by_type_and_shape(base_kernels)
        comparison_aggregated_kernels = self._aggregated_kernel_by_type_and_shape(comparison_kernels)
        for type_shape, base_data in base_aggregated_kernels.items():
            comparsion_data = comparison_aggregated_kernels.pop(type_shape, [])
            self._rows.append(self._bean(base_data, comparsion_data).row)
        if comparison_aggregated_kernels:
            for _, comparison_data in comparison_aggregated_kernels.items():
                self._rows.append(self._bean([], comparison_data).row)
        update_order_id(self._rows)
