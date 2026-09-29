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
from msprof_analyze.compare_tools.compare_backend.comparator.overall_performance_comparator import (
    OverallPerformanceComparator,
)
from msprof_analyze.compare_tools.compare_backend.compare_bean.profiling_info import ProfilingInfo
from msprof_analyze.prof_common.constant import Constant


class OverallInterface:
    def __init__(self, overall_data: dict):
        self._overall_data = overall_data

    def run(self):
        data = {
            Constant.BASE_DATA: self._overall_data.get(Constant.BASE_DATA).overall_metrics,
            Constant.COMPARISON_DATA: self._overall_data.get(Constant.COMPARISON_DATA).overall_metrics,
        }
        return OverallPerformanceComparator(data, ProfilingInfo).generate_data()
