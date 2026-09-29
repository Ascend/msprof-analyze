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
from msprof_analyze.compare_tools.compare_backend.generator.base_generator import BaseGenerator
from msprof_analyze.compare_tools.compare_backend.view.screen_view import ScreenView
from msprof_analyze.prof_common.logger import get_logger

logger = get_logger()


class OverallPerformanceGenerator(BaseGenerator):
    def compare(self):
        if not self._args.enable_profiling_compare:
            return
        self._result_data = OverallPerformanceComparator(self._profiling_data_dict, ProfilingInfo).generate_data()

    def generate_view(self):
        if not self._result_data:
            return
        ScreenView(self._result_data).generate_view()
        logger.info(
            "The OverallMetrics sheet page is more comprehensive for the disaggregate of performance data, "
            "and it is recommended to view the overall performance comparison results from "
            "the performance_comparison_result_*.xlsx."
        )
