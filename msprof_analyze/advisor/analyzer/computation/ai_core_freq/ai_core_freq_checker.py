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

from msprof_analyze.advisor.config.config import Config
from msprof_analyze.advisor.dataset.timeline_event_dataset import ComputationAnalysisDataset
from msprof_analyze.advisor.display.prompt.base_prompt import BasePrompt
from msprof_analyze.advisor.result.item import OptimizeItem, OptimizeRecord
from msprof_analyze.advisor.result.result import OptimizeResult
from msprof_analyze.advisor.utils.utils import convert_to_float
from msprof_analyze.prof_common.additional_args_manager import AdditionalArgsManager

logger = get_logger()


class AICoreFreqChecker:
    DECREASE_FREQ_RATIO = 0.05
    SHOW_TOPK_OPS = 10
    TOTAL_DURATION_INDEX = 2
    DECREASE_FREQ_RATIO_INDEX = 3

    def __init__(self):

        self.ai_core_freq_issues = False
        self.desc = ""
        self.suggestions = ""
        self.decrease_freq_ops = []
        self.headers = []
        self.op_freq = None
        self.rank = None
        self.stage = None

    def check_ai_core_freq(self, event_dataset: ComputationAnalysisDataset, rank=None, stage=None):
        """
        :Param event_dataset: dataset of timeline event
        """
        if not hasattr(event_dataset, "op_freq") or not getattr(event_dataset, "op_freq"):
            logger.debug("Skip slow ai core frequency checker, "
                         "because no ai core frequency were recorded in trace_view.json")
            return

        self.rank = rank
        self.stage = stage
        self.op_freq = event_dataset.op_freq
        for op_name, op_info in self.op_freq.items():
            freq_list = op_info.get("freq_list", [])
            if not freq_list:
                continue

            op_count = op_info.get("count", 0)
            op_total_duration = round(op_info.get("dur", 0), 2)
            max_freq = convert_to_float(Config().get_config("aic_frequency"))

            if max_freq == 0:
                raise ValueError("max_freq cannot be zero.")
            decrease_freq_ratio = sum(max_freq - freq for freq in freq_list) / (max_freq * len(freq_list))
            if decrease_freq_ratio >= Config().get_config("frequency_threshold"):
                self.ai_core_freq_issues = True
                self.decrease_freq_ops.append([op_name, op_count, op_total_duration,
                                               f"{round(decrease_freq_ratio, 4):.2%}",
                                               round(sum(freq_list) / len(freq_list), 2),
                                               max(freq_list), min(freq_list)])

        if self.decrease_freq_ops:
            # 按算子总耗时和降频比率 降序排列
            self.decrease_freq_ops.sort(
                key=lambda x: (x[self.TOTAL_DURATION_INDEX], x[self.DECREASE_FREQ_RATIO_INDEX]), reverse=True)
        if not self.ai_core_freq_issues:
            return

    def make_record(self, result: OptimizeResult):
        """
        make record for what and how to optimize
        """
        if not self.ai_core_freq_issues:
            return self.ai_core_freq_issues

        prompt_class = BasePrompt.get_prompt_class(self.__class__.__name__)

        problem = prompt_class.PROBLEM
        if self.rank is not None:
            problem += prompt_class.RANK_ID.format(self.rank)

        self.desc = prompt_class.DESCRIPTION.format(len(self.decrease_freq_ops), self.DECREASE_FREQ_RATIO)
        if self.rank:
            self.desc = prompt_class.RANK_DESCRIPTION.format(self.rank) + self.desc.lower()

        optimization_item = OptimizeItem(problem, self.desc, [prompt_class.SUGGESTION])
        result.add(OptimizeRecord(optimization_item))

        self.headers = [
            "Operator name",
            "Count",
            "Total duration(us)",
            "AI CORE frequency decreased ratio",
            "Average frequency",
            "Max frequency",
            "Min frequency",
        ]
        result.add_detail(problem, headers=self.headers)

        for row in self.decrease_freq_ops:
            result.add_detail(problem, detail=row)
        return True

    def make_render(self, html_render, add_render_list=True, **kwargs):
        if not self.ai_core_freq_issues:
            return self.ai_core_freq_issues

        priority = kwargs.get("priority")
        if self.SHOW_TOPK_OPS:
            self.desc += f" Only show {self.SHOW_TOPK_OPS} operators here, see latest mstt_advisor.xlsx for details."
        return html_render.render_template(key="computation",
                                           template_dir="templates",
                                           template_name="ai_core_frequency.html",
                                           desc=self.desc,
                                           suggestion=self.suggestions,
                                           headers=self.headers,
                                           data=self.decrease_freq_ops[:self.SHOW_TOPK_OPS],
                                           add_render_list=add_render_list,
                                           priority_background_color=priority,
                                           rank=kwargs.get("rank"))
