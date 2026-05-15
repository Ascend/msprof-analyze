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
import os

from msprof_analyze.advisor.analyzer.schedule.timeline_base_checker import TimelineBaseChecker
from msprof_analyze.prof_common.additional_args_manager import AdditionalArgsManager
from msprof_analyze.prof_common.constant import Constant
from msprof_analyze.advisor.config.config import Config
from msprof_analyze.advisor.dataset.timeline_event_dataset import ScheduleAnalysisDataset
from msprof_analyze.advisor.display.html.priority_background_color import PriorityBackgroundColor
from msprof_analyze.advisor.result.result import OptimizeResult
from msprof_analyze.advisor.result.item import OptimizeItem, OptimizeRecord
from msprof_analyze.advisor.utils.utils import format_timeline_result, safe_division
from msprof_analyze.prof_common.file_manager import FileManager

logger = get_logger()


class SynchronizeStreamChecker(TimelineBaseChecker):

    def __init__(self):
        super().__init__(n_processes=1)
        self.optimization_item = []
        self.synchronize_issues = False
        self.desc = ""
        self.suggestions = []
        self.solutions = []
        self.min_co_occurrence_ratio = 0
        self.priority = None
        self._init_rule()

    def check_synchronize(self, event_dataset: ScheduleAnalysisDataset):
        if not hasattr(event_dataset, "synchronize_stream") or not getattr(event_dataset, "synchronize_stream"):
            logger.info("Skip synchronize stream checker, because no synchronize stream found")
            return

        node_launch_num = 0
        co_occurrence_num = 0
        synchronize_num = 0
        synchronize_stream = event_dataset.synchronize_stream
        for index, op in enumerate(synchronize_stream):
            if op.name.startswith(Constant.NODE_LAUNCH):
                node_launch_num += 1
            if op.name.startswith(Constant.SYNC_STREAM):
                synchronize_num += 1

                # 统计nodeLaunch 和 synchronizeStream 一前一后连续出现次数
                if index > 0 and synchronize_stream[index - 1].name.startswith(Constant.NODE_LAUNCH):
                    co_occurrence_num += 1

        # 当共现次数很多时，则大概率设置了ASCEND_LAUNCH_BLOCKING环境变量
        co_occurrence_ratio = round(safe_division(co_occurrence_num, node_launch_num), 4)
        if co_occurrence_ratio > self.min_co_occurrence_ratio:
            self.synchronize_issues = True

        self.priority = self.get_priority()

        self.desc = self.desc.format(synchronize_num=synchronize_num,
                                     node_launch_num=node_launch_num,
                                     co_occur_ratio=co_occurrence_ratio)

        solutions = []
        for solution in solutions:
            renderer_solution = {}
            for key, val in solution.items():
                self.suggestions.append(f"{key}, {val.get('desc')}")
                renderer_solution.update({key: val})
            self.solutions.append(renderer_solution)

    def make_record(self, result: OptimizeResult):
        """
        make record for what and how to optimize
        """
        if not self.synchronize_issues:
            return

        self.optimization_item.append(OptimizeItem("Synchronize Stream Issues", self.desc, self.suggestions))
        for optimization in self.optimization_item:
            result.add(OptimizeRecord(optimization))

    def make_render(self, html_render, **kwargs):
        if not self.synchronize_issues:
            return
        priority = kwargs.get("priority")
        rank = kwargs.get("rank")
        format_result_for_html = format_timeline_result(dict(self.matched_op_stacks), dump_html=True)
        html_render.render_template(key="schedule",
                                    template_dir="templates",
                                    template_name="synchronize_stream.html",
                                    desc=self.desc,
                                    solutions=self.solutions,
                                    result=format_result_for_html,
                                    with_stack_doc_url=Config().timeline_with_stack_doc_url,
                                    empty_stacks=self.empty_stacks,
                                    framework_black_list=self.framework_black_list,
                                    priority_background_color=priority,
                                    rank=rank)

    def get_priority(self):
        return PriorityBackgroundColor.high

    def _init_rule(self):
        language = AdditionalArgsManager().language
        synchronize_rule_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))),
            "rules",
            language,
            "synchronize.yaml"
        )

        synchronize_rule = FileManager.read_yaml_file(synchronize_rule_path)

        self.min_co_occurrence_ratio = synchronize_rule.get("min_co_occurrence_ratio")
        self.desc = synchronize_rule.get("problem")

        self.solutions = synchronize_rule.get("solutions")
        for solution in self.solutions:
            for key, val in solution.items():
                self.suggestions.append(f"{key}, {val.get('desc')}")
