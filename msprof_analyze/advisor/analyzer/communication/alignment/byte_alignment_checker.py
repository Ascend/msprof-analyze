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
from typing import List
from msprof_analyze.advisor.dataset.communication.hccl_detail_dataset import HcclDetailDataset
from msprof_analyze.advisor.dataset.profiling.info_collection import HcclTask
from msprof_analyze.advisor.display.html.priority_background_color import PriorityBackgroundColor
from msprof_analyze.advisor.display.prompt.base_prompt import BasePrompt
from msprof_analyze.advisor.result.result import OptimizeResult
from msprof_analyze.advisor.result.item import OptimizeItem, OptimizeRecord
from msprof_analyze.prof_common.additional_args_manager import AdditionalArgsManager
from msprof_analyze.prof_common.file_manager import FileManager
from msprof_analyze.advisor.utils.utils import safe_division
from msprof_analyze.prof_common.constant import Constant

logger = get_logger()


class ByteAlignmentChecker:
    _CHECKER = "ByteAlignmentChecker"
    _BASE_SIZE = 512
    _MIN_SIZE = 512
    _LOW_PRIORITY = 0.2
    _HIGH_PRIORITY = 0.7
    _TYPE = "SDMA"

    def __init__(self, **kwargs):
        self.contention_issues = False
        self.desc = ""
        self.step_id = kwargs.get("step")
        self.stage = None
        self.byge_alignment_issue = False
        self.total_ops_dur = 0
        self.abnormal_ops_dur = 0
        self.abnormal_ops_count = 0
        self.min_size = 0
        self.topk = 0
        self.abnormal_ops = []
        self.suggestions = []
        self._init_rule()
        self.headers = [
            "op name", "total size(Byte)", "duration(us)", "abnormal duration(us)", "bandwidth(GB/s)"
        ]

    @staticmethod
    def _calculate_bandwidth_gb_s(size, duration):
        if abs(duration) < 1e-15:
            bandwidth = 0
        else:
            bandwidth = (size * Constant.COMMUNICATION_B_TO_GB) / (duration * Constant.US_TO_S)
        return round(bandwidth, 4)

    def check_alignment(self, hccl_detail_dataset: HcclDetailDataset) -> None:
        for hccl_op in hccl_detail_dataset.hccl_ops:
            size, duration, abnormal_dur, flag = self._check_op([hccl_op.memcpy_tasks, hccl_op.reduce_inline_tasks])
            if flag:
                self.abnormal_ops_count += 1
                self.abnormal_ops.append([hccl_op.op_name, size, round(duration, 4), round(abnormal_dur, 4),
                                          self._calculate_bandwidth_gb_s(size, duration)])
        if self.abnormal_ops_count:
            self.byge_alignment_issue = True
            self.desc = self.desc.format(count=self.abnormal_ops_count)

    def make_record(self, result: OptimizeResult):
        """
        make record for what and how to optimize
        """
        optimization_item = OptimizeItem(self.problem, self.desc, self.suggestions)
        result.add(OptimizeRecord(optimization_item))

        sub_table_name = BasePrompt.get_sub_table_name(self.problem, self.stage)
        result.add_detail(sub_table_name, headers=self.headers)

        for hccl_op in self.abnormal_ops:
            result.add_detail(sub_table_name, detail=hccl_op)

    def make_render(self, html_render, **kwargs):
        rank = kwargs.get("rank")
        return html_render.render_template(key="communication",
                                           template_dir="templates",
                                           template_name="byte_alignment.html",
                                           desc=self.desc,
                                           solutions=self.solutions,
                                           headers=self.headers,
                                           datas=self.abnormal_ops[:min(self.topk, len(self.abnormal_ops))],
                                           num=min(self.topk, len(self.abnormal_ops)),
                                           priority_background_color=self._get_priority(),
                                           rank=rank)

    def _pre_check(self, task: HcclTask, type_):
        """
        Check whether the operator meets the data volume alignment detection conditions.
        """
        if task.transport_type != type_ or task.link_type == "ON_CHIP" or task.size <= self.min_size:
            return False
        return True

    def _check_op(self, op: List[List[HcclTask]]):
        flag = False
        size = 0
        duration = 0
        abnormal_dur = 0
        for tasks in op:
            for task in tasks:
                if not self._pre_check(task, self._TYPE):
                    continue
                self.total_ops_dur += task.duration
                size += task.size
                duration += task.duration
                if task.size % self._BASE_SIZE:
                    self.abnormal_ops_dur += task.duration
                    abnormal_dur += task.duration
                    flag = True
        return [size, duration, abnormal_dur, flag]

    def _init_rule(self):
        language = AdditionalArgsManager().language
        rule_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))),
            "rules",
            language,
            "byte_alignment.yaml"
        )

        byte_alignment_rule = FileManager.read_yaml_file(rule_path)
        self.problem = byte_alignment_rule.get("problem")
        self.desc = byte_alignment_rule.get("description")
        self.min_size = byte_alignment_rule.get("min_size", self._MIN_SIZE)
        self.topk = byte_alignment_rule.get("top_num", 3)
        self.solutions = byte_alignment_rule.get("solutions")
        if not self.desc or not self.solutions or not isinstance(self.solutions, list):
            raise RuntimeError("The configuration file of the byte alignment analyzer is abnormal. Please check.")
        for solution in self.solutions:
            for _, val in solution.items():
                self.suggestions.append(f"{val.get('desc')}")

    def _get_priority(self):
        if safe_division(self.abnormal_ops_dur, self.total_ops_dur) < self._LOW_PRIORITY:
            return PriorityBackgroundColor.low
        elif safe_division(self.abnormal_ops_dur, self.total_ops_dur) >= self._HIGH_PRIORITY:
            return PriorityBackgroundColor.high
        else:
            return PriorityBackgroundColor.medium
