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
from msprof_analyze.prof_common.logger import get_logger

logger = get_logger()


class ModuleComparator(BaseComparator):
    def _compare(self):
        if not self._origin_data:
            return
        base_all_data = [data for data in self._origin_data if data[0]]  # index 0 for base module
        base_all_data.sort(key=lambda x: x[0].start_time)
        base_none_data = [data for data in self._origin_data if not data[0]]  # index 0 for base module
        base_none_data.sort(key=lambda x: x[1].start_time)
        index = 0
        for base_module, comparison_module in base_all_data:
            if not comparison_module:
                self._rows.extend(self._bean(base_module, comparison_module).rows)
                continue
            while index < len(base_none_data):
                module = base_none_data[index][1]  # index 1 for comparison module
                if module.start_time < comparison_module.start_time:
                    self._rows.extend(self._bean(None, module).rows)
                    index += 1
                else:
                    break
            self._rows.extend(self._bean(base_module, comparison_module).rows)
        while index < len(base_none_data):
            module = base_none_data[index][1]  # index 1 for comparison module
            self._rows.extend(self._bean(None, module).rows)
            index += 1
        update_order_id(self._rows)
        if not any(row[-1] != Constant.NA for row in self._rows):
            logger.warning("If you want to see the operator's call stack, you must enable with_stack switch.")
