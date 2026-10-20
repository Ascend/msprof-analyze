#!/usr/bin/python
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

from msprof_analyze.advisor.display.prompt.base_prompt import BasePrompt
from msprof_analyze.prof_common.constant import Constant
from msprof_analyze.advisor.analyzer.base_analyzer import BaseAnalyzer
from msprof_analyze.advisor.dataset.timeline_event_dataset import ScheduleAnalysisDataset
from msprof_analyze.advisor.result.item import OptimizeItem, OptimizeRecord
from msprof_analyze.advisor.result.result import OptimizeResult
from msprof_analyze.advisor.display.html.render import HTMLRender
from msprof_analyze.advisor.display.html.priority_background_color import PriorityBackgroundColor

logger = get_logger()


class OpDispatchAnalyzer(BaseAnalyzer):
    dataset_cls_list = [ScheduleAnalysisDataset]
    """
    operator dispatch optimizer
    """

    def __init__(self, collection_path, n_processes: int = 1, **kwargs) -> None:
        super().__init__(collection_path, n_processes, **kwargs)
        key = ScheduleAnalysisDataset.get_key()
        self.dataset = self.get_first_data_by_key(self.dataset_list, key)
        self.result = OptimizeResult()
        self.html_render = HTMLRender()
        self._op_compile = None
        self._issues_record = []
        self.optimization_item = []

    @BaseAnalyzer.check_data((ScheduleAnalysisDataset.get_key(),))
    def optimize(self, **kwargs):
        """
        optimize operator
        :param data: input datasets
        :return: result
        """
        if "mindspore" in self.profiling_type:
            logger.info("The analyzer %s does not support MindSpore.", self.__class__.__name__)
            return self.result
        self.get_op_compile_info(self.dataset)
        self.make_record(self.result)
        self.make_render(self.html_render, rank=kwargs.get('rank'))
        return self.result

    def get_op_compile_info(self, event_dataset: ScheduleAnalysisDataset):
        """
        :Param event_dataset: dataset of timeline event
        """
        if hasattr(event_dataset, "ops_compile"):
            self._op_compile = getattr(event_dataset, "ops_compile")
            if not self._op_compile or self._op_compile.total_count < Constant.MAX_OP_COMPILE_NUM:
                return

            self._issues_record.append(
                ['operator dispatch', Constant.OP_COMPILE_ID, self._op_compile.total_count, self._op_compile.total_time]
            )
        else:
            logger.debug("Skip operator compile checker, because no op_compile attr find.")

    def make_record(self, result: OptimizeResult):
        """
        make record for what and how to optimize
        """
        if not self._op_compile or len(self._issues_record) <= 0:
            return

        prompt_class = BasePrompt.get_prompt_class(self.__class__.__name__)
        self.optimization_item.append(
            OptimizeItem(
                prompt_class.PROBLEM,
                prompt_class.DESCRIPTION.format(self._op_compile.total_count),
                [prompt_class.SUGGESTION],
            )
        )
        for optimization in self.optimization_item:
            result.add(OptimizeRecord(optimization))

        record_title = ["Issues", "op name", "counts", "total time"]
        result.add_detail(prompt_class.PROBLEM, headers=record_title)
        for op_info in self._issues_record:
            result.add_detail(prompt_class.PROBLEM, detail=op_info)

    def make_render(self, html_render, **kwargs):
        issues = []
        optimizations = []
        for optimization in self.optimization_item:
            optimizations.append(dict(description=optimization.description, suggestion=optimization.suggestion[0]))
        for record in self._issues_record:
            issues.append(dict(issue=record[0], op_name=record[1], counts=record[2], total_time=record[3]))
        html_render.render_template(
            key="schedule",
            template_dir="templates",
            template_name="operator_dispatch.html",
            issues=issues,
            optimizers=optimizations,
            priority_background_color=self.get_priority(),
            rank=kwargs.get("rank"),
        )

    def get_priority(self, max_mem_op_dur=None):
        step_duration = getattr(self.dataset, "step_duration", None)
        op_compile_total_dur = getattr(self._op_compile, "total_time", None)
        if step_duration is None or op_compile_total_dur is None:
            return PriorityBackgroundColor.low

        return self.get_priority_by_time_ratio(op_compile_total_dur, step_duration)
