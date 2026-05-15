# Copyright (c) Huawei Technologies Co., Ltd. 2025. All rights reserved.
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
from msprof_analyze.advisor.analyzer.computation.ai_core_performance.ai_core_performance_checker import \
    AICorePerformanceChecker
from msprof_analyze.advisor.dataset.profiling.profiling_dataset import ProfilingDataset
from msprof_analyze.advisor.result.result import OptimizeResult
from msprof_analyze.advisor.display.html.priority_background_color import PriorityBackgroundColor
from msprof_analyze.advisor.display.html.render import HTMLRender

logger = get_logger()


class AICorePerformanceAnalyzer(BaseAnalyzer):
    dataset_cls_list = [ProfilingDataset]

    def __init__(self, collection_path, n_processes: int = 1, **kwargs) -> None:
        super().__init__(collection_path, n_processes, **kwargs)
        profiling_key = ProfilingDataset.get_key()
        self.profiling_dataset = self.get_first_data_by_key(self.dataset_list, profiling_key)
        self.result = OptimizeResult()
        self.html_render = HTMLRender()
        self.html = None

    def optimize(self, **kwargs):
        add_render_list = kwargs.get("add_render_list", True)
        ai_core_perf_checker = AICorePerformanceChecker()
        ai_core_perf_checker.data_filter(self.profiling_dataset)
        if not ai_core_perf_checker.ai_core_performance_issues:
            return self.result
        ai_core_perf_checker.check_ai_core_performance(self.profiling_dataset)
        ai_core_perf_checker.make_record(self.result)
        self.html = ai_core_perf_checker.make_render(self.html_render,
                                                     add_render_list,
                                                     priority=self.get_priority(),
                                                     rank=kwargs.get("rank"))
        return self.result

    def get_priority(self, max_mem_op_dur=None):
        return PriorityBackgroundColor.low