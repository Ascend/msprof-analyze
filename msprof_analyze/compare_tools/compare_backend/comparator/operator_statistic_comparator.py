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


class OperatorStatisticComparator(BaseComparator):
    def __init__(self, origin_data: list, bean: any):
        super().__init__(origin_data, bean)

    def _compare(self):
        if not self._origin_data:
            return
        base_op_dict, comparison_op_dict = self._group_by_op_name()
        for op_name, base_data in base_op_dict.items():
            comparison_data = comparison_op_dict.pop(op_name, [])
            self._rows.append(self._bean(op_name, base_data, comparison_data).row)
        for op_name, comparison_data in comparison_op_dict.items():
            self._rows.append(self._bean(op_name, [], comparison_data).row)
        self._rows.sort(key=lambda x: x[-2], reverse=True)  # order by diff column
        update_order_id(self._rows)

    def _group_by_op_name(self):
        base_op_dict, comparison_op_dict = {}, {}
        for base_op, comparison_op in self._origin_data:
            if base_op:
                base_op_dict.setdefault(base_op.name, []).append(base_op)
            if comparison_op:
                comparison_op_dict.setdefault(comparison_op.name, []).append(comparison_op)
        return base_op_dict, comparison_op_dict
