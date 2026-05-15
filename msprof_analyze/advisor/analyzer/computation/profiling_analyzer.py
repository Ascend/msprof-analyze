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
from abc import ABC

from msprof_analyze.advisor.analyzer.base_analyzer import BaseAnalyzer
from msprof_analyze.advisor.result.result import OptimizeResult
from msprof_analyze.advisor.analyzer.computation.aicpu.aicpu_checker import AicpuChecker
from msprof_analyze.advisor.analyzer.computation.bound.block_dim_checker import BlockDimChecker
from msprof_analyze.advisor.analyzer.computation.bound.operator_bound_checker import OperatorBoundChecker
from msprof_analyze.advisor.analyzer.computation.op_compile.dynamic_shape_checker import DynamicShapeChecker
from msprof_analyze.advisor.analyzer.computation.operator_checker import OperatorChecker
from msprof_analyze.advisor.display.html.priority_background_color import PriorityBackgroundColor
from msprof_analyze.advisor.display.html.render import HTMLRender
from msprof_analyze.advisor.dataset.profiling.profiling_dataset import ProfilingDataset

logger = get_logger()


class ProfilingAnalyzer(BaseAnalyzer, ABC):
    dataset_cls_list = [ProfilingDataset]

    def __init__(self, collection_path, **kwargs) -> None:
        super().__init__(collection_path, **kwargs)
        self.checker = OperatorChecker(self.cann_version)
        self.html_render = HTMLRender()
        self.result = OptimizeResult()
        self.html = None

    @BaseAnalyzer.check_data((ProfilingDataset.get_key(),))
    def optimize(self, **kwargs) -> OptimizeResult:
        """
        optimize operator
        :param data: input datasets
        :return: result
        """
        profiling_data = self.get_first_data_by_key(self.dataset_list, ProfilingDataset.get_key())
        checker = self.checker
        rank = kwargs.get("rank")

        add_render_list = kwargs.get("add_render_list", True)

        if not checker.pre_check(profiling_data):
            return self.result
        if checker.check(profiling_data):
            # add record
            record = checker.make_record(profiling_data, rank)
            self.html = checker.make_render(self.html_render, record, add_render_list,
                                            priority=self.get_priority(checker), rank=kwargs.get("rank"))
            self.result.add(record)
            # add details
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

    def get_priority(self, max_mem_op_dur):
        if "aicpu" not in max_mem_op_dur.__class__.__name__.lower():
            return PriorityBackgroundColor.low

        aicpu_duration = getattr(max_mem_op_dur, "aicpu_task_duration", 0.0)
        total_duration = getattr(max_mem_op_dur, "total_task_duration", 0.0)
        return self.get_priority_by_time_ratio(aicpu_duration, total_duration)


class DynamicShapeAnalyzer(ProfilingAnalyzer):
    def __init__(self, collection_path, **kwargs) -> None:
        super().__init__(collection_path, **kwargs)
        self.checker = DynamicShapeChecker(self.cann_version)

    @BaseAnalyzer.check_data((ProfilingDataset.get_key(),))
    def optimize(self, **kwargs) -> OptimizeResult:
        if "mindspore" in self.profiling_type:
            logger.info("The analyzer %s does not support MindSpore.", self.__class__.__name__)
            return self.result
        return super().optimize.__wrapped__(self, **kwargs)


class BlockDimAnalyzer(ProfilingAnalyzer):
    def __init__(self, collection_path, **kwargs) -> None:
        super().__init__(collection_path, **kwargs)
        self.checker = BlockDimChecker(self.cann_version)


class OperatorBoundAnalyzer(ProfilingAnalyzer):
    def __init__(self, collection_path, **kwargs) -> None:
        super().__init__(collection_path, **kwargs)
        self.checker = OperatorBoundChecker(self.cann_version)


class AicpuAnalyzer(ProfilingAnalyzer):
    def __init__(self, collection_path, **kwargs) -> None:
        super().__init__(collection_path, **kwargs)
        self.checker = AicpuChecker(self.cann_version)
