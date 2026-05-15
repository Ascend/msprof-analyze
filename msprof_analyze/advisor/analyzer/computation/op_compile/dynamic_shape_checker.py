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
import copy
from msprof_analyze.prof_common.logger import get_logger
from typing import List

from msprof_analyze.advisor.analyzer.computation.operator_checker import OperatorChecker
from msprof_analyze.advisor.config.config import Config
from msprof_analyze.advisor.dataset.profiling.info_collection import OpInfo
from msprof_analyze.advisor.display.prompt.base_prompt import BasePrompt
from msprof_analyze.advisor.result.item import OptimizeItem, StatisticsItem, OptimizeRecord
from msprof_analyze.prof_common.additional_args_manager import AdditionalArgsManager
from msprof_analyze.prof_common.file_manager import FileManager

logger = get_logger()


class DynamicShapeChecker(OperatorChecker):
    _CHECKER = "dynamic shape operator"
    _op_list: List[OpInfo] = []
    _tune_op_list: List[str] = []  # record op name to be tuned, and save to tune_ops_file.cfg
    _op_views: List = []

    def __init__(self, cann_version) -> None:
        super().__init__(cann_version=cann_version)
        self.prompt_class = BasePrompt.get_prompt_class(self.__class__.__name__)
        self._problem = self.prompt_class.PROBLEM
        self._description = self.prompt_class.DESCRIPTION
        self.enable_compiled_suggestion = self.prompt_class.ENABLE_COMPILED_SUGGESTION
        self._suggestion = [self.prompt_class.ENABLE_COMPILED_SUGGESTION]
        self.release_suggestion = self.prompt_class.RELEASE_SUGGESTION

    def check(self, profiling_data) -> bool:
        return self.is_dynamic_shape(profiling_data)

    def make_record(self, profiling_data, rank=None) -> OptimizeRecord:
        """
        make record for what and how to optimize
        """
        if rank is not None:
            self._problem = self.prompt_class.RANK_ID.format(rank) + self._problem.lower()
        optimization_item = OptimizeItem(
            self._problem,
            self._description,
            self._suggestion
        )
        statistics_item = StatisticsItem("", "", 1)
        return OptimizeRecord(optimization_item, statistics_item)

    def format_operator_result(self, record, limit=-1):
        """
        Format operator result to html
        :param record: profiling check record
        :param limit: Limit number of operator statistics lists.
        :return:
        """
        optimization_item = record.optimization_item
        release_suggestion_list = []
        for suggestion in optimization_item.suggestion:
            release_suggestion = copy.deepcopy(suggestion)
            if release_suggestion == self.enable_compiled_suggestion:
                release_suggestion += self.release_suggestion.format(Config().enable_compiled_tune_url)
            release_suggestion_list.append(release_suggestion.replace('\n', '<br>'))
        format_result = {"record": record.__dict__, "suggestion": '<br> '.join(release_suggestion_list)}
        return format_result

    def make_render(self, html_render, record, add_render_list=True, **kwargs):
        priority = kwargs.get("priority")
        return html_render.render_template(key="computation",
                                           template_dir="templates",
                                           template_name="operator_dynamic_shape.html",
                                           format_result=self.format_operator_result(record),
                                           add_render_list=add_render_list,
                                           priority_background_color=priority,
                                           rank=kwargs.get("rank"))
