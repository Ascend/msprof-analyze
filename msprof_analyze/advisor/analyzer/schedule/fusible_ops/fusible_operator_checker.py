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
import os
from typing import List
from collections import OrderedDict
from msprof_analyze.prof_common.constant import Constant
from msprof_analyze.advisor.dataset.profiling.profiling_dataset import ProfilingDataset
from msprof_analyze.advisor.display.prompt.base_prompt import BasePrompt
from msprof_analyze.advisor.dataset.profiling.info_collection import OpInfo
from msprof_analyze.advisor.result.result import OptimizeResult
from msprof_analyze.advisor.result.item import OptimizeItem, OptimizeRecord
from msprof_analyze.prof_common.additional_args_manager import AdditionalArgsManager
from msprof_analyze.prof_common.file_manager import FileManager
from msprof_analyze.advisor.utils.utils import convert_to_float_with_warning, safe_division
from msprof_analyze.advisor.display.html.priority_background_color import PriorityBackgroundColor

logger = get_logger()


class FusibleOperatorChecker:
    _CHECKER = "FusibleOperatorChecker"
    _KEYS = ['Name', 'Input Shapes', 'Output Shapes']
    _RATIO_COLUMN = ['aic_mte2_ratio', 'aiv_mte2_ratio', 'aic_fixpipe_ratio', 'aiv_mte3_ratio']
    _TOTAL_TIME_INDEX = 0
    _NPU_TIME_INDEX = 1
    _MTE_TIME_INDEX = 2
    _COUNT_INDEX = 3
    _MTE_FLAG_INDEX = 4
    _HOST_FLAG_INDEX = 5
    _HIGH_PRIORITY = 0.7
    _LOW_PRIORITY = 0.3
    _SPLITTER = '-'

    def __init__(self, **kwargs):
        self.fusion_issues = False
        self.desc = ""
        self.table_desc = ""
        self.host_desc = ""
        self.mte_desc = ""
        self.problem = ""
        self.mte_problem = ""
        self.host_problem = ""
        self.solutions = ""
        self.min_length = 0
        self.max_length = 0
        self.host_threshold = 0
        self.mte_threshold = 0
        self.sequence_duration_threshold = 0
        self.sequence_count_threshold = 0
        self.topk = 0
        self.step_duration = 0
        self.step_id = kwargs.get("step")
        self.stage = None
        self.task_list = []
        self.suggestions = []
        self._init_rule()
        self.headers = [
            "start index", "end index", "total time(us)", "execution time(us)", "mte time(us)", "occurrences",
            "mte bound", "host bound"
        ]
        self.index_dict: OrderedDict = OrderedDict()
        self.host_details = []
        self.mte_details = []

    @staticmethod
    def make_render(self, html_render, add_render_list=True, **kwargs):
        return

    @staticmethod
    def get_mte_time(task: OpInfo):
        return max(convert_to_float_with_warning(task.aic_mte2_time),
                   convert_to_float_with_warning(task.aiv_mte2_time)) + max(
            convert_to_float_with_warning(task.aic_fixpipe_time),
            convert_to_float_with_warning(task.aiv_mte3_time))

    @staticmethod
    def check_hccl(task: OpInfo):
        return (task.task_type in ["COMMUNICATION", "HCCL"] or
                any(task.op_name.lower().startswith(item) for item in ["hcom", "lccl", "lcoc"]))

    @staticmethod
    def check_aicpu(task: OpInfo):
        return task.task_type == Constant.AI_CPU

    @staticmethod
    def calculate_total_time(pre_timestamp, timestamp, duration):
        total_time = (convert_to_float_with_warning(timestamp) + convert_to_float_with_warning(duration) -
                      convert_to_float_with_warning(pre_timestamp))
        if not total_time:
            logger.warning("Total duration is zero.")
            return 0, False
        return total_time, True

    def check_fusible_operator(self, profiling_dataset: ProfilingDataset):
        if not self.check_tasks(profiling_dataset):
            return
        tasks = profiling_dataset.op_summary.op_list
        result_dict = OrderedDict()
        self.step_duration, _ = self.calculate_total_time(tasks[0].task_start_time, tasks[-1].task_start_time,
                                                             tasks[-1].task_duration)
        length = len(profiling_dataset.op_summary.op_list)
        for index, task in enumerate(tasks):
            if self.check_hccl(task) or self.check_aicpu(task):
                continue
            start_time = convert_to_float_with_warning(task.task_start_time)
            key = self.generate_key(task)
            duration = convert_to_float_with_warning(task.task_duration)
            mte_time = self.get_mte_time(task)
            aicore_time = convert_to_float_with_warning(task.aicore_time)
            for i in range(1, self.max_length):
                if i + index >= length:
                    break
                new_task = tasks[i + index]
                if self.check_hccl(new_task) or self.check_aicpu(new_task):
                    break
                key = key + self._SPLITTER + self.generate_key(new_task)
                duration = duration + convert_to_float_with_warning(new_task.task_duration)
                mte_time += self.get_mte_time(new_task)
                aicore_time += convert_to_float_with_warning(new_task.aicore_time)
                total_time, _ = self.calculate_total_time(start_time, new_task.task_start_time, new_task.task_duration)
                host_flag = duration / total_time < self.host_threshold if total_time else False
                mte_flag = mte_time / aicore_time > self.mte_threshold if aicore_time else False
                if not mte_flag and not host_flag or i < self.min_length:
                    continue
                result = result_dict.get(key, (0, 0, 0, 0, False, False))
                result_dict[key] = (
                    result[self._TOTAL_TIME_INDEX] + total_time,
                    result[self._NPU_TIME_INDEX] + duration, result[self._MTE_TIME_INDEX] + mte_time,
                    result[self._COUNT_INDEX] + 1, mte_flag, host_flag
                )
                if key not in self.index_dict:
                    self.index_dict[key] = (index, i + index)
        if result_dict:
            self.post_processing(result_dict)

    def check_sequence_ratio(self, detail: List):
        return safe_division(detail[self._TOTAL_TIME_INDEX], self.step_duration) > self.sequence_duration_threshold

    def check_sequence_num(self, detail: List):
        return detail[self._COUNT_INDEX] > self.sequence_count_threshold

    def check_bound(self, detail: List):
        return self.check_sequence_ratio(detail) or detail[self._MTE_FLAG_INDEX]

    def post_processing(self, result_dict: OrderedDict):
        result = OrderedDict()
        base_sequence = None
        record_task_name = None
        for task_name, detail in result_dict.items():
            if self.check_sequence_num(detail) and (self.check_sequence_ratio(detail) or detail[self._MTE_FLAG_INDEX]):
                if not base_sequence:
                    record_task_name = task_name
                elif task_name.startswith(base_sequence) and detail[self._TOTAL_TIME_INDEX] > \
                        result_dict[record_task_name][self._TOTAL_TIME_INDEX]:
                    record_task_name = task_name
                else:
                    result[record_task_name] = result_dict[record_task_name]
                    record_task_name = task_name
                base_sequence = task_name
        if task_name not in result and self.check_sequence_num(detail) and self.check_bound(detail):
            result[task_name] = result_dict[task_name]
        wall_duration = 0
        npu_time = 0
        host_time = 0
        mte_time = 0
        result = OrderedDict(sorted(result.items(), key=lambda x: -x[1][self._TOTAL_TIME_INDEX]))
        for task_name, detail in result.items():
            wall_duration += detail[0]
            npu_time += detail[1]
            host_time += detail[0] - detail[1]
            mte_time += detail[2]
            if not wall_duration:
                continue
            if detail[self._MTE_FLAG_INDEX]:
                self.add_detail(task_name, self.mte_details, detail)
            if detail[self._HOST_FLAG_INDEX]:
                self.add_detail(task_name, self.host_details, detail)
        if result:
            self.fusion_issues = True
            self.desc = self.desc.format(count=len(self.mte_details + self.host_details),
                                         wall_duration=round(wall_duration / Constant.US_TO_MS, 3),
                                         npu_time=round(npu_time / Constant.US_TO_MS, 3),
                                         host_threshold=round(host_time / wall_duration, 3),
                                         mte_threshold=round(mte_time / wall_duration, 3))

    def add_detail(self, task_name: str, details: List, detail: List):
        details.append([
            self.index_dict.get(task_name, (0, 0))[0], self.index_dict.get(task_name, (0, 0))[1],
            round(detail[0], 2), round(detail[1], 2), round(detail[2], 2), detail[3], detail[4], detail[5]
        ])

    def generate_key(self, task):
        return self._SPLITTER.join([task.op_name, task.input_shapes, task.output_shapes])

    def compute_priority(self):
        sequence_total_time = sum(detail[self._TOTAL_TIME_INDEX] for detail in self.host_details + self.mte_details)
        if safe_division(sequence_total_time, self.step_duration) > self._HIGH_PRIORITY:
            return PriorityBackgroundColor.high
        elif safe_division(sequence_total_time, self.step_duration) < self._LOW_PRIORITY:
            return PriorityBackgroundColor.low
        else:
            return PriorityBackgroundColor.medium

    def check_tasks(self, profiling_dataset: ProfilingDataset):
        if not hasattr(profiling_dataset, "op_summary"):
            logger.warning("Skip %s checker because of not containing %s", self._CHECKER, "op summary")
            return False
        elif not hasattr(profiling_dataset.op_summary, "op_list"):
            logger.warning("Skip %s checker because of not containing %s", self._CHECKER, "op summary")
            return False
        elif not profiling_dataset.op_summary.op_list:
            logger.warning("Skip %s checker because not containing tasks", self._CHECKER)
            return False
        tasks = profiling_dataset.op_summary.op_list
        task = tasks[0]
        step_duration, flag = self.calculate_total_time(tasks[0].task_start_time, tasks[-1].task_start_time,
                                                        tasks[-1].task_duration)
        if not flag:
            return False
        for item in ["aic_mte2_time", "aiv_mte2_time", "aic_fixpipe_time", "aiv_mte3_time", "task_type"]:
            if not hasattr(task, item):
                logger.warning("kenel_details.csv(op_summary.csv) not contain %s, skip operator sequence analysis.",
                               item)
                return False
        return True

    def make_record(self, result: OptimizeResult):
        """
        make record for what and how to optimize
        """
        optimization_item = OptimizeItem(self.problem, self.desc, self.suggestions)
        result.add(OptimizeRecord(optimization_item))

        sub_table_name = BasePrompt.get_sub_table_name(self.host_problem, self.stage)
        annotation = self.table_desc.split("\n")
        result.add_detail(sub_table_name, headers=self.headers)
        result.add_detail(sub_table_name, detail=annotation)
        for detail in self.host_details:
            result.add_detail(sub_table_name, detail=detail)

        sub_table_name = BasePrompt.get_sub_table_name(self.mte_problem, self.stage)
        result.add_detail(sub_table_name, headers=self.headers)
        result.add_detail(sub_table_name, detail=annotation)
        for detail in self.mte_details:
            result.add_detail(sub_table_name, detail=detail)

    def _init_rule(self):
        language = AdditionalArgsManager().language
        contention_rule_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))),
            "rules",
            language,
            "fusible_operator.yaml"
        )

        fusion_rule = FileManager.read_yaml_file(contention_rule_path)
        self.problem = fusion_rule.get("problem")
        self.mte_problem = fusion_rule.get("mte_problem")
        self.host_problem = fusion_rule.get("host_problem")
        self.desc = fusion_rule.get("description")
        self.table_desc = fusion_rule.get("table_description")
        self.mte_desc = fusion_rule.get("mte_description")
        self.host_desc = fusion_rule.get("host_description")
        self.solutions = fusion_rule.get("solutions")
        self.min_length = fusion_rule.get("min_length")
        self.max_length = fusion_rule.get("max_length")
        self.host_threshold = fusion_rule.get("host_threshold")
        self.mte_threshold = fusion_rule.get("mte_threshold")
        self.sequence_duration_threshold = fusion_rule.get("sequence_duration_threshold")
        self.sequence_count_threshold = fusion_rule.get("sequence_count_threshold")
        self.topk = fusion_rule.get("top_num")
        if not self.desc or not self.solutions or not isinstance(self.solutions, list):
            raise RuntimeError("The configuration file of the fusible operator analyzer is abnormal. Please check.")
        for solution in self.solutions:
            for _, val in solution.items():
                self.suggestions.append(f"{val.get('desc')}")
