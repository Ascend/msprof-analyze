# Copyright (c) 2024, Huawei Technologies Co., Ltd.
# All rights reserved.
#
# Licensed under the Apache License, Version 2.0  (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
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

    def optimize(self, compare_profiling_list, **kwargs):
        for compare_profiling_path in compare_profiling_list:
            self._optimize(**compare_profiling_path)
        return self.result

    def get_priority(self, max_mem_op_dur=None):
        pass

    def _optimize(self, profiling_path, benchmark_profiling_path, **kwargs):
        comparison_checker = ComparisonChecker(profiling_path,
                                               benchmark_profiling_path,
                                               step=kwargs.get("step"),
                                               benchmark_step=kwargs.get("benchmark_step"),
                                               rank=kwargs.get("rank"),
                                               benchmark_rank=kwargs.get("benchmark_rank"))
        comparison_checker.compare(kwargs.get("compare_mode"))
        comparison_checker.make_record(self.result)
        comparison_checker.make_render(self.html_render)
