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
import copy
import os
from functools import partial
from typing import List, Dict, Optional

from msprof_analyze.advisor.dataset.stack.db_stack_finder import DBStackFinder
from msprof_analyze.advisor.analyzer.computation.operator_checker import OperatorChecker, logger
from msprof_analyze.advisor.dataset.stack.timeline_stack_finder import TimelineOpStackFinder
from msprof_analyze.advisor.dataset.dataset import Dataset
from msprof_analyze.advisor.dataset.profiling.profiling_dataset import ProfilingDataset
from msprof_analyze.advisor.dataset.timeline_event_dataset import ComputationAnalysisDataset
from msprof_analyze.prof_common.additional_args_manager import AdditionalArgsManager
from msprof_analyze.prof_common.file_manager import FileManager
from msprof_analyze.prof_common.constant import Constant


class AicpuChecker(OperatorChecker):
    _CHECKER = "aicpu operator"
    _MIN_TASK_DURATION = 20
    STACK_INFO_ITEMS = "stack_info"
    SUGGESTION_INFO_ITEMS = "suggestions"
    _ITEMS = [
        "op_name",
        "op_type",
        "task_duration",
        "input_shapes",
        "input_data_types",
        "input_formats",
        "output_shapes",
        "output_data_types",
        "output_formats",
    ]

    def __init__(self, cann_version):
        super().__init__(cann_version=cann_version)
        self.aicpu_rules: Dict = {}
        self.aicpu_checker: Dict = {}
        self.total_task_duration = 0.0
        self.aicpu_task_duration = 0.0
        self.double_suggestion = None
        self.load_aicpu_rules()

    def load_aicpu_rules(self):
        language = AdditionalArgsManager().language
        rule_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))),
            "rules",
            language,
            "aicpu_rules.yaml",
        )

        if not os.path.exists(rule_path):
            logger.warning("Skip analyze aicpu issues, because %s does not exist.", rule_path)

        self.aicpu_rules = FileManager.read_yaml_file(rule_path)
        self._problem = self.aicpu_rules.get("problem")
        self._description = self.aicpu_rules.get("description").format(self._MIN_TASK_DURATION)
        self._suggestion = [self.aicpu_rules.get("suggestion")]
        self.double_suggestion = self.aicpu_rules.get("double_suggestion")
        self.filter_aicpu_rules(self.aicpu_rules)
        for checker_name, check_rule in self.aicpu_rules.items():
            if not isinstance(
                check_rule,
                (
                    list,
                    dict,
                ),
            ):
                continue

            if checker_name not in AICPU_CHECKER:
                logger.warning("Skip %s, which is not support now.", checker_name)
                continue

            self.aicpu_checker[checker_name] = AICPU_CHECKER[checker_name](check_rule)

    def filter_aicpu_rules(self, aicpu_rules):
        support_checkers = []
        for checkers in aicpu_rules['CommonChecker']:
            for key, value in checkers.items():
                if key == 'DataTypeChecker' and self.cann_version in value['cann_version']:
                    support_checkers.append(checkers)
        aicpu_rules['CommonChecker'] = support_checkers

    def check_aicpu_attr(self, op_info) -> List[str]:
        suggestions = []
        for _, checker in self.aicpu_checker.items():
            suggestions.extend(checker.check(op_info))
        return suggestions

    def check(self, profiling_data: ProfilingDataset) -> bool:
        """
        check if any operator need optimize
        :param profiling_data: profiling datasest
        :return: true or false
        """

        if not self._check_data(profiling_data):
            return False
        op_summary = profiling_data.op_summary

        self._op_list = []

        max_task_duration = 0.0
        for op_info in op_summary.op_list:
            task_duration = float(op_info.task_duration)

            if self._check_operator(op_info):
                self._op_list.append(op_info)
                self.aicpu_task_duration += task_duration

            self.total_task_duration += task_duration
            max_task_duration = max(max_task_duration, task_duration)
        if (not self._op_list) or (max_task_duration < self._MIN_TASK_DURATION):
            return False

        # 获取所有算子堆栈的信息
        op_name_list = []
        for op in self._op_list:
            if op.op_name not in op_name_list:
                op_name_list.append(op.op_name)
        stack_record = self.get_operator_stack_info(profiling_data, op_name_list)

        # task_id 到 stack 信息的对应
        self._op_list.sort(key=lambda x: int(x.task_id))
        stack_record.sort(key=lambda x: x[0])
        task_id_to_stack = dict()
        for stack in stack_record:
            task_id_to_stack[stack[0]] = stack[-1]

        # 算子追加堆栈属性
        for op in self._op_list:
            stack = task_id_to_stack.get(int(op.task_id))
            op.add_attr(self.STACK_INFO_ITEMS, stack)
            suggestions = self.check_aicpu_attr(op)
            op.add_attr(self.SUGGESTION_INFO_ITEMS, suggestions)

        # double 类型算子判断
        double_type_ai_cpu_operator = []
        for op in self._op_list:
            if not op.has_attr("input_data_types"):
                logger.warning(
                    "Skip checking of input data in AICPU checker "
                    "because of not containing input_data_dtypes in op summary"
                )
                break
            if (
                op.has_attr("input_data_types")
                and "DOUBLE" in op.input_data_types
                and op.op_name not in double_type_ai_cpu_operator
            ):
                double_type_ai_cpu_operator.append(op.op_name)
        if bool(double_type_ai_cpu_operator):
            self._suggestion.append(self.double_suggestion.format(",".join(double_type_ai_cpu_operator)))
        return True

    def get_operator_stack_info(self, profiling_dataset: ProfilingDataset, op_name_list: List[str]):
        if not op_name_list:
            return []
        if profiling_dataset.data_type == Constant.TEXT:
            return self.query_stack_from_timeline_json(
                collection_path=profiling_dataset.collection_path, op_name_list=op_name_list, task_type=Constant.AI_CPU
            )
        elif profiling_dataset.data_type == Constant.DB and hasattr(profiling_dataset, "op_summary"):
            db_path = profiling_dataset.op_summary.file_path
            return self.query_stack_from_db(db_path, op_name_list, Constant.AI_CPU)
        return []

    def query_stack_from_timeline_json(self, collection_path, op_name_list, task_type):
        data: Dict[str, Dataset] = {}
        event_dataset = ComputationAnalysisDataset(collection_path=collection_path, data=data, task_type=task_type)

        # disable multiprocessing, avoid cost time of enable new process for light task
        api_stack_finder = TimelineOpStackFinder()
        api_stack_finder.get_api_stack_by_op_name(
            event_dataset, op_name_list, Constant.AI_CPU, disable_multiprocess=True
        )
        return api_stack_finder.get_stack_record()

    def query_stack_from_db(self, db_path, op_name_list, task_type):
        stack_helper = DBStackFinder(db_path)
        return stack_helper.get_task_stack_by_op_name(op_name_list, task_type)

    def make_render(self, html_render, record, add_render_list=True, **kwargs):
        priority = kwargs.get("priority")
        return html_render.render_template(
            key="computation",
            template_dir="templates",
            template_name="operator_ai_cpu.html",
            format_result=self.format_operator_result(record, Constant.OPERATOR_LIST_UNLIMIT),
            add_render_list=add_render_list,
            priority_background_color=priority,
            rank=kwargs.get("rank"),
        )

    def format_operator_result(self, record, limit):
        """
        Format operator result to html
        :param record: profiling check record
        :param limit: Limit number of operator statistics lists.
        :return:
        """
        optimization_item = record.optimization_item
        release_suggestion_list = []
        for suggestion in optimization_item.suggestion:
            release_suggestion_list.append(suggestion.replace('\n', '<br>'))
        logger.debug("suggestion list is %s", release_suggestion_list)
        format_result = {
            "record": record.__dict__,
            "suggestion": '<br> '.join(release_suggestion_list),
            "task_duration": round(record.statistics_item.task_duration, 2),
        }

        statistic = self.group_by(copy.deepcopy(self._op_list), op_key='op_type', limit=limit)
        format_result["statistic"] = statistic
        stack_key_list = ["stack_info", "input_data_types", "output_data_types"]
        if statistic:
            for _, info in statistic:
                op_info_list = self.group_by_list(info.get("op_info_list"), stack_key_list, limit)
                info["op_info_list"] = op_info_list
        return format_result

    def group_by_list(self, op_list, op_key_list: List = None, limit: int = Constant.OPERATOR_LIST_UNLIMIT):
        if op_list is None:
            op_list = []
        if op_key_list is None:
            op_key_list = ["stack_info", "input_data_types", "output_data_types"]

        # op_key_list 合并添加合并的属性，作为 groupby 的 key value
        op_key = '+'.join(op_key_list)  # str, json
        for op_info in op_list:
            attribute = ""
            for _op in op_key_list:
                if op_info.get_attr(_op):
                    attribute += op_info.get_attr(_op)
            op_info.add_attr(op_key, attribute)

        return self.group_by(op_list, op_key=op_key, limit=limit)

    def _check_data(self, profiling_data: ProfilingDataset) -> bool:
        if not self._check_summary(profiling_data):
            return False
        return True

    def _check_operator(self, op_info) -> bool:
        return op_info.task_type == Constant.AI_CPU


class BaserChecker:
    def __init__(self, *args, **kwargs):
        self.checker_list = []

    def build(self):
        raise NotImplementedError

    def check(self, op_info) -> List[str]:
        suggestions = []
        for checker in self.checker_list:
            suggestion = checker(op_info)
            if suggestion is not None:
                suggestions.append(suggestion)
        return suggestions


class CommonChecker(BaserChecker):
    def __init__(self, check_rules: List[Dict] = None):
        super().__init__()
        self.check_rules = check_rules if check_rules is not None else []
        self.supported_checker = dict(DataTypeChecker=self.datatype_checker)
        self.build()

    @staticmethod
    def datatype_checker(check_item: Dict, op_info) -> Optional[str]:
        supported_op_type = check_item.get('op_type', [])
        suggestion = check_item.get('suggestion', "")
        valid_inputs = check_item.get('input', [])
        valid_outputs = check_item.get('output', [])
        ignore_type = check_item.get('ignore_type', [])
        op_type = getattr(op_info, 'op_type', "UNKNOWN")
        if "__ALL__" in supported_op_type or op_type.lower() in supported_op_type:
            if op_type.lower() in ignore_type:
                return None

            op_input_dtype = getattr(op_info, 'input_data_types', "").split(";")
            op_input_dtype = [item.lower() for item in op_input_dtype]
            op_output_dtype = getattr(op_info, 'output_data_types', "").split(";")
            op_output_dtype = [item.lower() for item in op_output_dtype]
            input_dtype_diff = set(op_input_dtype).difference(set(valid_inputs))
            output_dtype_diff = set(op_output_dtype).difference(set(valid_outputs))
            unsupported_dtype_diff = input_dtype_diff.union(output_dtype_diff)
            if not unsupported_dtype_diff:
                return None

            return suggestion.format(",".join(unsupported_dtype_diff).upper(), op_type, ",".join(valid_inputs).upper())
        return None

    def build(self):
        for check in self.check_rules:
            ((check_func, check_rule),) = check.items()
            if check_func not in self.supported_checker:
                logger.warning("Skip %s, which has not been implemented.", check_func)
                continue
            self.checker_list.append(partial(self.supported_checker.get(check_func), check_rule))


class ExampleGuideChecker(BaserChecker):
    def __init__(self, check_rules: List[Dict] = None):
        super().__init__()
        self.check_rules = check_rules if check_rules is not None else []
        self.build()

    def build(self):
        def _guide_url(check_item: Dict, op_info) -> Optional[str]:
            supported_op_type = check_item.get('op_type', [])
            url = check_item.get('url', "")
            suggestion = check_item.get('suggestion', "")

            if getattr(op_info, 'op_type', "UNKNOWN").lower() in supported_op_type:
                return suggestion if "{}" not in suggestion else suggestion.format(url)
            return None

        for check in self.check_rules:
            ((_, check_rule),) = check.items()
            self.checker_list.append(partial(_guide_url, check_rule))


AICPU_CHECKER = {"CommonChecker": CommonChecker, "ExampleGuideChecker": ExampleGuideChecker}
