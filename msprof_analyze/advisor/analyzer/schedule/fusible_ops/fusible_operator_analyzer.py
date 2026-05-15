# Copyright (c) 2025, Huawei Technologies Co., Ltd.
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
from msprof_analyze.advisor.analyzer.schedule.fusible_ops.fusible_operator_checker import FusibleOperatorChecker
from msprof_analyze.advisor.display.html.priority_background_color import PriorityBackgroundColor
from msprof_analyze.advisor.display.html.render import HTMLRender
from msprof_analyze.advisor.dataset.profiling.profiling_dataset import ProfilingDataset
from msprof_analyze.advisor.result.result import OptimizeResult

logger = get_logger()


class FusibleOperatorAnalyzer(BaseAnalyzer):
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
        fusible_operator_checker = FusibleOperatorChecker(**kwargs)
        fusible_operator_checker.check_fusible_operator(self.profiling_dataset)
        if not fusible_operator_checker.fusion_issues:
            return self.result
        fusible_operator_checker.make_record(self.result)
        return self.result

    def get_priority(self, max_mem_op_dur=None):
        # 提升1% ~ 3%
        return PriorityBackgroundColor.low
