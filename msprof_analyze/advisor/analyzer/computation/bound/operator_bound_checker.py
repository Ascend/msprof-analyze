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
from typing import List

from msprof_analyze.advisor.analyzer.computation.operator_checker import OperatorChecker
from msprof_analyze.advisor.display.prompt.base_prompt import BasePrompt
from msprof_analyze.prof_common.additional_args_manager import AdditionalArgsManager
from msprof_analyze.prof_common.constant import Constant
from msprof_analyze.advisor.config.config import Config
from msprof_analyze.advisor.dataset.profiling.profiling_dataset import ProfilingDataset
from msprof_analyze.advisor.utils.utils import to_percent

logger = get_logger()


class OperatorBoundChecker(OperatorChecker):
    _MIN_TASK_DURATION = 20  # min task duration 20us
    _CHECKER = "operator no bound"
    _SUGGESTION: List[str] = []
    _ITEMS = [
        "op_name", "op_type", "task_type", "task_duration", "vec_ratio", "mac_ratio", "scalar_ratio", "mte1_ratio",
        "mte2_ratio", "mte3_ratio", "block_dim", "input_shapes", "input_data_types", "input_formats", "output_shapes",
        "output_data_types", "output_formats"
    ]

    def __init__(self, cann_version) -> None:
        super().__init__(cann_version=cann_version)
        self.prompt_class = BasePrompt.get_prompt_class(self.__class__.__name__)
        self._problem = self.prompt_class.PROBLEM
        self._description = self.prompt_class.DESCRIPTION.format(to_percent(Config().operator_bound_ratio))

    def pre_check(self, profiling_data) -> bool:
        return not self.is_dynamic_shape(profiling_data)

    def make_render(self, html_render, record, add_render_list=True, **kwargs):
        priority = kwargs.get("priority")
        return html_render.render_template(key="computation",
                                           template_dir="templates",
                                           template_name="operator_no_bound.html",
                                           format_result=self.format_operator_result(record,
                                                                                     Constant.OPERATOR_OUT_TOPK),
                                           add_render_list=add_render_list,
                                           priority_background_color=priority,
                                           rank=kwargs.get("rank"))

    def _check_data(self, profiling_data):
        self.format_suggestion_content(profiling_data)
        if not self._check_summary(profiling_data):
            return False
        for op_info in profiling_data.op_summary.op_list:
            return self._check_operator(op_info)

        logger.warning(self.SKIP_CHECK_MSG, self._CHECKER, "ratio in op summary")
        return False

    def _check_operator(self, op_info) -> bool:
        bound_list = ["vec_ratio", "mac_ratio", "scalar_ratio", "mte1_ratio", "mte2_ratio", "mte3_ratio"]
        ratio_list = [self.get_ratio(op_info, attr) for attr in bound_list]
        if not any(ratio_list):
            return False  # no data, skip check
        if any(ratio and ratio > Config().operator_bound_ratio for ratio in ratio_list):
            return False
        return True
