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
from msprof_analyze.prof_common.logger import get_logger

from msprof_analyze.advisor.analyzer.base_analyzer import BaseAnalyzer
from msprof_analyze.advisor.analyzer.comparison.comparison_checker import ComparisonChecker
from msprof_analyze.advisor.display.html.render import HTMLRender
from msprof_analyze.advisor.result.result import OptimizeResult

logger = get_logger()


class ComparisonAnalyzer(BaseAnalyzer):
    def __init__(self, collection_path, n_processes: int = 1, **kwargs) -> None:
        super().__init__(collection_path, n_processes, **kwargs)
        self.result = OptimizeResult()
        self.html_render = HTMLRender()

    def optimize(self, compare_profiling_list, **kwargs):  # pylint: disable=arguments-differ
        for compare_profiling_path in compare_profiling_list:
            self._optimize(**compare_profiling_path)
        return self.result

    def get_priority(self, max_mem_op_dur=None):
        pass

    def _optimize(self, profiling_path, benchmark_profiling_path, **kwargs):
        comparison_checker = ComparisonChecker(
            profiling_path,
            benchmark_profiling_path,
            step=kwargs.get("step"),
            benchmark_step=kwargs.get("benchmark_step"),
            rank=kwargs.get("rank"),
            benchmark_rank=kwargs.get("benchmark_rank"),
        )
        comparison_checker.compare(kwargs.get("compare_mode"))
        comparison_checker.make_record(self.result)
        comparison_checker.make_render(self.html_render)
