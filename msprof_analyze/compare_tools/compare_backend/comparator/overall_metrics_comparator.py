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
from math import isclose

from msprof_analyze.compare_tools.compare_backend.comparator.base_comparator import BaseComparator
from msprof_analyze.compare_tools.compare_backend.utils.excel_config import ExcelConfig

from msprof_analyze.prof_common.constant import Constant


class OverallMetricsComparator(BaseComparator):
    def __init__(self, origin_data: dict, bean: any):
        super().__init__(origin_data, bean)
        self._row_style = []

    @property
    def base_info(self):
        return self._origin_data.get(Constant.BASE_DATA)

    @property
    def comp_info(self):
        return self._origin_data.get(Constant.COMPARISON_DATA)

    def generate_data(self) -> dict:
        self._compare()
        return {
            self._sheet_name: {
                "headers": self._headers,
                "rows": self._rows,
                "overhead": self._overhead,
                "row_style": self._row_style,
            }
        }

    def _compare(self):
        if isclose(self.base_info.e2e_time_ms, 0) or isclose(self.comp_info.e2e_time_ms, 0):
            return
        self._rows.extend(self._bean(self.base_info, self.comp_info).rows)
        for row in self._rows:
            self._row_style.append(ExcelConfig.ROW_STYLE_MAP.get(row[0], {}))  # index 0 for metric index name
