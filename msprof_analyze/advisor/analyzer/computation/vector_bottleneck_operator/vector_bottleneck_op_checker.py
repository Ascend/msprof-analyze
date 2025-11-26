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
import os
import copy
from typing import List, Dict
from enum import Enum
import collections

from msprof_analyze.advisor.dataset.stack.db_stack_finder import DBStackFinder
from msprof_analyze.advisor.analyzer.computation.operator_checker import logger, OperatorChecker
from msprof_analyze.advisor.dataset.stack.timeline_stack_finder import TimelineOpStackFinder
from msprof_analyze.advisor.dataset.dataset import Dataset
from msprof_analyze.advisor.dataset.profiling.profiling_dataset import ProfilingDataset
from msprof_analyze.advisor.dataset.profiling.db_step_time_finder import DBStepTimeFinder
from msprof_analyze.advisor.dataset.timeline_event_dataset import ComputationAnalysisDataset
from msprof_analyze.prof_common.additional_args_manager import AdditionalArgsManager
from msprof_analyze.prof_common.file_manager import FileManager
from msprof_analyze.prof_common.constant import Constant
from msprof_analyze.prof_common.path_manager import PathManager
from msprof_analyze.advisor.config.config import Config
from msprof_analyze.advisor.display.html.priority_background_color import PriorityBackgroundColor
from msprof_analyze.advisor.utils.utils import convert_to_float


class VectorBottleneckOPChecker(OperatorChecker):
    PROBLEM = "problem"
    DESCRIPTION = "description"
    SUGGESTION = "suggestion"
    RULES = "rules"
    YAML_RULES_PATH = "vector_bottleneck_op_rules.yaml"
    HTML_TEMPLATE = "operator_bottleneck.html"
    _MAX_THRESHOLD = 0.2
    _MIN_THRESHOLD = 0.05
    SUGGESTION_INFO_ITEMS = "suggestions"
    STACK_INFO_ITEMS = "stack_info"
    OP_INFO_LIST = "op_info_list"
    FLOAT_ZERO = 1e-9

    def __init__(self, cann_version: str, collection_path: str = ""):
        super().__init__(cann_version)
        self.language = 'cn'
        self.rules: Dict = {}
        self.op_checker = None
        self.total_task_time: float = 0.0
        self.step_time: float = 0.0
        self.collection_path = collection_path
        self.op_computation_time: Dict = {}
        self.load_threshold_op_rules()
        self._priority = OperatorPriority.LOW

    @property
    def priority(self):
        return self._priority

    @staticmethod
    def get_op_priority_color(priority):
        if priority == OperatorPriority.HIGH:
            return PriorityBackgroundColor.high
        elif priority in (OperatorPriority.MEDIUM_LOW, OperatorPriority.MEDIUM_HIGH):
            return PriorityBackgroundColor.medium
        else:
            return PriorityBackgroundColor.low

    @staticmethod
    def get_profile_path(collection_path):
        for root, _, files in PathManager.limited_depth_walk(collection_path):
            for file in files:
                if file.startswith("profiler_info"):
                    return root
        return ""

    def load_threshold_op_rules(self):
        language = AdditionalArgsManager().language
        self.language = language
        rule_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))),
            self.RULES,
            language,
            self.YAML_RULES_PATH
        )
        if not os.path.exists(rule_path):
            logger.warning("Skip analyze threashold issues, because %s does not exist.", rule_path)
        self.rules = FileManager.read_yaml_file(rule_path)
        self._problem = self.rules.get(self.PROBLEM)
        self._description = self.rules.get(self.DESCRIPTION)
        self._suggestion = [self.rules.get(self.SUGGESTION)]
        for _, checker_rule in self.rules.items():
            if not isinstance(checker_rule, (list, dict)):
                continue
            self.op_checker = ExampleSuggestionChecker(checker_rule)

    def check(self, profiling_data: ProfilingDataset) -> bool:
        if not self._check_summary(profiling_data):
            return False
        op_summary = profiling_data.op_summary
        self.total_task_time = op_summary.get_total_task_duration()
        self.step_time = self.get_step_time(profiling_data)
        op_time_duration = collections.defaultdict(float)
        self._op_list = []
        for op_info in op_summary.op_list:
            task_duration = convert_to_float(op_info.get_attr("task_duration", Constant.DEFAULT_DURATION_ZERO))
            if self.op_checker.contains(op_info.op_type, op_info.input_shapes):
                self._op_list.append(op_info)
                op_time_duration[op_info.op_type] += task_duration

        self._check_operator_priority(op_time_duration)
        self._op_list = list(filter(lambda op: op.op_type in self.op_computation_time, self._op_list))
        if not self._op_list:
            return False
        op_name_list = {}
        for op in self._op_list:
            op_name_list[op.op_name] = op.task_type
        self._get_stack_record(profiling_data, op_name_list)
        return True

    def get_step_time(self, profiling_dataset: ProfilingDataset) -> float:
        if profiling_dataset.data_type == Constant.TEXT:
            return self.step_trace_time_avg_step_time()
        elif profiling_dataset.data_type == Constant.DB:
            return DBStepTimeFinder(profiling_dataset.op_summary.file_path).get_avg_step_time()
        return 0.0

    def get_operator_stack_info(self, profiling_dataset: ProfilingDataset, op_name_list: dict):
        if not op_name_list:
            return []
        if profiling_dataset.data_type == Constant.TEXT:
            return self.query_stack_from_timeline_json(collection_path=profiling_dataset.collection_path,
                                                       op_name_list=list(op_name_list.keys()))
        elif profiling_dataset.data_type == Constant.DB and hasattr(profiling_dataset, "op_summary"):
            db_path = profiling_dataset.op_summary.file_path
            return self.query_stack_from_db(db_path, op_name_list)
        return []

    def query_stack_from_timeline_json(self, collection_path, op_name_list):
        data: Dict[str, Dataset] = {}
        event_dataset = ComputationAnalysisDataset(collection_path=collection_path,
                                                   data=data)
        api_stack_finder = TimelineOpStackFinder()
        api_stack_finder.get_api_stack_by_op_name(event_dataset, op_name_list,
                                                  disable_multiprocess=True)
        return api_stack_finder.get_stack_record()

    def query_stack_from_db(self, db_path, op_name_list):
        stack_helper = DBStackFinder(db_path)
        stack_list = []
        for op_name, task_type in op_name_list.items():
            stack = stack_helper.get_task_stack_by_op_name([op_name], task_type)
            for stack_info in stack:
                stack_info[-1] = stack_info[-1].replace(';\n', ';\r\n')
            stack_list.extend(stack)
        return stack_list

    def make_render(self, html_render, add_render_list=True, **kwargs):
        priority = kwargs.get("priority")
        return html_render.render_template(
            key="computation",
            template_dir="templates",
            template_name=self.HTML_TEMPLATE,
            format_result=self.format_operator_result(),
            add_render_list=add_render_list,
            priority_background_color=priority,
            with_stack_doc_url=Config().timeline_with_stack_doc_url,
            language=self.language,
            rank=kwargs.get("rank")
        )

    def format_operator_result(self, rank=None):
        if rank is not None:
            self._problem = self.rank_id.format(rank) + self._problem.lower()
        suggestion_list = []
        for suggestion in self._suggestion:
            suggestion_list.append(suggestion.replace('\n', '<br>'))
        logger.debug("suggestion list is %s", suggestion_list)
        format_result = {
            self.SUGGESTION: '<br>'.join(suggestion_list),
            self.DESCRIPTION: self._get_description(
                self._description,
                self.get_op_type_list(self._op_list)[:self._MAX_TUNE_OP_NUM]
            ),
            self.PROBLEM: self._problem
        }
        statistic = self.group_op_by_key(copy.deepcopy(self._op_list), op_key='op_type')
        format_result["statistic"] = statistic
        stack_key_list = ["stack_info", "input_data_types", "output_data_types"]
        if not statistic:
            return format_result
        for _, info in statistic:
            op_info_list = self.group_op_info_by_stack(info.get(self.OP_INFO_LIST), stack_key_list)
            info[self.OP_INFO_LIST] = op_info_list
        return format_result

    def group_op_by_key(
            self,
            op_list,
            op_key='op_type',
    ):
        if not op_list:
            op_list = []
        statistic = {}
        for op_info in op_list:
            op_type = op_info.get_attr(op_key)
            statistic_op_key = statistic.get(op_type, {})
            summary = statistic_op_key.get("summary", {})
            if summary:
                if summary.get("counts"):
                    summary["counts"] += 1
                stack_info = op_info.get_attr("stack_info")
                if stack_info:
                    op_info.stack_info = stack_info.replace('\r\n', '<br/>')
                if statistic_op_key.get(self.OP_INFO_LIST) is None:
                    statistic_op_key[self.OP_INFO_LIST] = []
                statistic_op_key[self.OP_INFO_LIST].append(op_info)
            else:
                statistic[op_type] = {"summary": {}, self.OP_INFO_LIST: []}
                summary_item = statistic[op_type]["summary"]
                summary_item["op_type"] = op_info.get_attr(
                    "op_type",
                    Constant.DEFAULT_OPERATOR_TYPE
                )
                if op_type in self.op_computation_time:
                    op_property = self.op_computation_time[op_type]
                    op_computation_duration = op_property.get("op_time", 0.0)
                    op_computation_ratio = op_property.get("computation_time_ratio", 0.0)
                    op_step_time_ratio = op_property.get("step_time_ratio", 0.0)
                    op_priority = op_property.get("priority", OperatorPriority.LOW)
                    summary_item["total_duration"] = op_computation_duration
                    summary_item["op_computation_ratio"] = op_computation_ratio
                    summary_item["op_step_time_ratio"] = op_step_time_ratio
                    summary_item["op_priority"] = op_priority.value
                    summary_item["op_color"] = self.get_op_priority_color(op_priority)
                    summary_item["suggestion"] = self.op_checker.get_suggestion_by_type(op_type)
                summary_item["counts"] = 1
                stack_info = op_info.get_attr("stack_info")
                if stack_info:
                    op_info.stack_info = stack_info.replace('\r\n', '<br/>')
                statistic[op_type]["op_info_list"] = [op_info]
        if not statistic:
            logger.warning("%s checker do not has results to format html", str(self.__class__.__name__))
            return None
        is_sort = False
        for op_type in statistic.keys():
            if "total_duration" in statistic[op_type]["summary"]:
                is_sort = True
                statistic[op_type]["summary"]["total_duration"] = round(
                    statistic[op_type]["summary"]["total_duration"],
                    2
                )
        if is_sort:
            statistic = sorted(
                statistic.items(),
                key=lambda kv: kv[1]["summary"]["total_duration"],
                reverse=True
            )
        return statistic

    def group_op_info_by_stack(
            self,
            op_info_list,
            op_key_list: List = None,
    ):
        if not op_info_list:
            op_info_list = []
        if not op_key_list:
            op_key_list = ["stack_info", "input_data_types", "output_data_types"]
        op_key = '+'.join(op_key_list)
        for op_info in op_info_list:
            attribute = ""
            for _op in op_key_list:
                if op_info.get_attr(_op):
                    attribute += op_info.get_attr(_op)
            op_info.add_attr(op_key, attribute)
        return self.group_op_by_key(op_info_list, op_key)

    def check_op_attr(self, op_info) -> List[str]:
        suggestions = []
        for _, checker in self.op_checker.items():
            suggestions.extend(checker.check(op_info))
        return suggestions

    def step_trace_time_avg_step_time(self) -> float:
        profile_path = self.get_profile_path(self.collection_path)
        step_trace_time_path = os.path.join(profile_path, Constant.SINGLE_OUTPUT, Constant.STEP_TIME_CSV)
        csv_data = FileManager.read_csv_file(step_trace_time_path, StepTraceBean)
        if not csv_data:
            logger.info("step_trace_time.csv is empty:%s", step_trace_time_path)
            return 0.0
        valid_times = [
            step.step_time
            for step in csv_data
            if step.step_time is not None and isinstance(step.step_time, (int, float)) and step.step_time >= 0
        ]
        if valid_times:
            total_time = sum(valid_times)
            avg_time = total_time / len(valid_times)
        else:
            avg_time = 0.0
        return avg_time

    def _check_operator_priority(self, op_time_duration):
        for op, op_time in op_time_duration.items():
            if self.total_task_time < self.FLOAT_ZERO or self.step_time < self.FLOAT_ZERO:
                return
            computation_time_ratio = op_time / self.total_task_time
            step_time_ratio = op_time / self.step_time

            if (computation_time_ratio >= self._MIN_THRESHOLD
                    and step_time_ratio <= computation_time_ratio):
                self._priority = OperatorPriority.MEDIUM_LOW  # 总体优先级，决定最外部的优先级颜色
                self.op_computation_time[op] = {
                    "op_time": op_time,
                    "computation_time_ratio": computation_time_ratio * 100,
                    "step_time_ratio": step_time_ratio * 100,
                    "priority": OperatorPriority.MEDIUM_LOW  # 单个算子优先级，决定给出不同优先级建议
                }
                if computation_time_ratio >= self._MAX_THRESHOLD and step_time_ratio >= self._MIN_THRESHOLD:
                    self.op_computation_time[op]['priority'] = OperatorPriority.HIGH
                    self._priority = OperatorPriority.HIGH
                if computation_time_ratio >= self._MAX_THRESHOLD and step_time_ratio < self._MIN_THRESHOLD:
                    self.op_computation_time[op]['priority'] = OperatorPriority.MEDIUM_HIGH
                    self._priority = OperatorPriority.MEDIUM_HIGH

    def _get_stack_record(self, profiling_data: ProfilingDataset, op_name_list: dict):
        stack_record = self.get_operator_stack_info(profiling_data, op_name_list)
        self._op_list.sort(key=lambda x: int(x.task_id))
        stack_record.sort(key=lambda x: x[0])
        task_id_to_stack = dict()
        for stack in stack_record:
            task_id_to_stack[stack[0]] = stack[-1]

        for op in self._op_list:
            stack = task_id_to_stack.get(int(op.task_id))
            op.add_attr(self.STACK_INFO_ITEMS, stack)


class ExampleSuggestionChecker:
    _INPUT_SHAPE_LIMIT = "input_shape_limit"

    def __init__(self, check_rules: List[Dict]) -> None:
        self.check_rules = check_rules if check_rules is not None else []
        self.op_list = None
        if self.check_rules:
            self.op_list = self.check_rules[0]['op_list']

    def contains(self, op_type: str, input_shape_str: str) -> bool:
        if not self.op_list:
            return False
        if not self.op_list or op_type not in self.op_list:
            return False
        index = self.op_list.index(op_type) + 1
        rule_item = self.check_rules[index].get(op_type, {})
        if not rule_item:
            return False
        if self._INPUT_SHAPE_LIMIT not in rule_item:
            return True
        input_shape_part = input_shape_str.strip('"').split(';')
        input_shapes = [tuple(map(int, part.split(','))) for part in input_shape_part]
        for shape_limit in rule_item[self._INPUT_SHAPE_LIMIT]:
            is_shape_limit = True  # 存在input shape依赖
            for i, shape in enumerate(shape_limit):
                try:
                    if input_shapes[i][shape[0]] != shape[1]:
                        is_shape_limit = False
                        break
                except IndexError:
                    logger.info('index out of range.')
                    is_shape_limit = False
                    break
            if is_shape_limit:
                return True
        return False

    def get_suggestion_by_type(self, op_type) -> str:
        if op_type not in self.op_list:
            logger.info("op_type is not supported %s", op_type)
            return ""
        index = self.op_list.index(op_type) + 1
        check_item = self.check_rules[index][op_type]
        url = check_item.get('url', "")
        suggestion = check_item.get('suggestion', "").format(url)
        return suggestion


class StepTraceBean:
    ZERO_VALUE = 0.0
    COMPUTING = "Computing"
    COMMUNICATION_NOT_OVERLAPPED = "Communication(Not Overlapped)"
    FREE = 'Free'

    def __init__(self, data: Dict) -> None:
        self._data = data

    @property
    def step_time(self):
        if not self._data:
            return self.ZERO_VALUE
        computation_time = convert_to_float(self._data.get(self.COMPUTING, 0))
        step_time = (computation_time
                     + convert_to_float(self._data.get(self.COMMUNICATION_NOT_OVERLAPPED, 0))
                     + convert_to_float(self._data.get(self.FREE, 0)))
        return step_time


class OperatorPriority(Enum):
    HIGH = 3  # 高优先级算子
    MEDIUM_HIGH = 2  # 中高优先级算子
    MEDIUM_LOW = 1  # 中低优先级算子
    LOW = 0  # 低优先级算子