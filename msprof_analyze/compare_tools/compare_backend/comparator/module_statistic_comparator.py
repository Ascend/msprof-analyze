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
from collections import OrderedDict

from msprof_analyze.compare_tools.compare_backend.comparator.base_comparator import BaseComparator
from msprof_analyze.compare_tools.compare_backend.utils.common_func import update_order_id


class ModuleStatisticComparator(BaseComparator):
    def __init__(self, origin_data: list, bean: any):
        super().__init__(origin_data, bean)

    def _compare(self):
        if not self._origin_data:
            return
        base_module_dict, comparison_module_dict = self._group_by_module_name()
        for module_name, base_data in base_module_dict.items():
            comparison_data = comparison_module_dict.pop(module_name, [])
            self._rows.extend(self._bean(module_name, base_data, comparison_data).rows)
        for module_name, comparison_data in comparison_module_dict.items():
            self._rows.extend(self._bean(module_name, [], comparison_data).rows)
        update_order_id(self._rows)

    def _group_by_module_name(self):
        base_module_dict, comparison_module_dict = OrderedDict(), OrderedDict()
        base_all_data = [data for data in self._origin_data if data[0]]  # index 0 for base module
        base_all_data.sort(key=lambda x: x[0].start_time)
        base_none_data = [data for data in self._origin_data if not data[0]]  # index 0 for base module
        base_none_data.sort(key=lambda x: x[1].start_time)
        index = 0
        for base_module, comparison_module in base_all_data:
            base_module_dict.setdefault(base_module.module_name, []).append(base_module)
            if not comparison_module:
                continue
            while index < len(base_none_data):
                module = base_none_data[index][1]  # index 1 for comparison module
                if module.start_time < comparison_module.start_time:
                    comparison_module_dict.setdefault(module.module_name, []).append(module)
                    index += 1
                else:
                    break
            comparison_module_dict.setdefault(comparison_module.module_name, []).append(comparison_module)
        while index < len(base_none_data):
            module = base_none_data[index][1]  # index 1 for comparison module
            comparison_module_dict.setdefault(module.module_name, []).append(module)
            index += 1
        return base_module_dict, comparison_module_dict
