# Copyright (c) 2025-2026, Huawei Technologies Co., Ltd.
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
import logging

from msprof_analyze.advisor.analyzer.base_analyzer import BaseAnalyzer
from msprof_analyze.advisor.dataset.profiling.profiling_dataset import ProfilingDataset
from msprof_analyze.advisor.display.html.render import HTMLRender
from msprof_analyze.advisor.result.result import OptimizeResult
from msprof_analyze.advisor.display.html.priority_background_color import PriorityBackgroundColor
from msprof_analyze.advisor.analyzer.computation.vector_bottleneck_operator.vector_bottleneck_op_checker import \
    VectorBottleneckOPChecker, OperatorPriority

logger = logging.getLogger()


class VectorBottleneckOPAnalyzer(BaseAnalyzer):
    dataset_cls_list = [ProfilingDataset]

    def __init__(self, collection_path, **kwargs) -> None:
        super().__init__(collection_path, **kwargs)
        self.html_render = HTMLRender()
        self.result = OptimizeResult()
        self.html = None

    @staticmethod
    def get_priority(checker):
        if not checker or not checker.priority:
            return PriorityBackgroundColor.low
        if checker.priority == OperatorPriority.HIGH:
            return PriorityBackgroundColor.high
        elif (checker.priority == OperatorPriority.MEDIUM_HIGH
              or checker.priority == OperatorPriority.MEDIUM_LOW):
            return PriorityBackgroundColor.medium
        else:
            return PriorityBackgroundColor.low

    @BaseAnalyzer.check_data((ProfilingDataset.get_key(),))
    def optimize(self, **kwargs) -> OptimizeResult:
        profiling_data = self.get_first_data_by_key(self.dataset_list, ProfilingDataset.get_key())
        checker = VectorBottleneckOPChecker(self.cann_version, self.collection_path)
        rank = kwargs.get("rank")
        add_render_list = kwargs.get("add_render_list", True)
        if not checker.pre_check(profiling_data):
            return self.result
        if checker.check(profiling_data):
            self.html = checker.make_render(
                self.html_render,
                add_render_list,
                priority=self.get_priority(checker),
                rank=kwargs.get("rank")
            )
        details = checker.get_details()
        if details:
            for i, detail in enumerate(details):
                sheet_name = checker.get_name() if rank is None else \
                    f"rank {rank} ".capitalize() + checker.get_name()
                if i == 0:
                    # the first row is header
                    self.result.add_detail(sheet_name, headers=detail)
                else:
                    self.result.add_detail(sheet_name, detail=detail)
        # add tune op list
        tune_op_list = checker.get_tune_op_list()
        if tune_op_list:
            self.result.add_tune_op_list(tune_op_list)

        return self.result