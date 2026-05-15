# Copyright (c) Huawei Technologies Co., Ltd. 2025. All rights reserved.
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
from functools import reduce

from msprof_analyze.advisor.utils.utils import safe_division, convert_to_int_with_exception, \
    convert_to_float_with_warning
from msprof_analyze.advisor.dataset.profiling.profiling_dataset import ProfilingDataset
from msprof_analyze.advisor.result.item import OptimizeItem, OptimizeRecord
from msprof_analyze.advisor.result.result import OptimizeResult
from msprof_analyze.prof_common.additional_args_manager import AdditionalArgsManager
from msprof_analyze.prof_common.file_manager import FileManager

logger = get_logger()


class AICorePerformanceChecker:
    """
        operator performance checker
    """
    _CHECKER = "AICorePerformanceChecker"
    CUBE_OPERATOR_MEMORY_SIZE_MB = 100
    INNER_AXIS_256 = 256
    INNER_AXIS_128 = 128

    def __init__(self):
        self.result = dict()
        self.ai_core_performance_issues = False
        self._desc = ""
        self.cube_dict = {}
        self.fa_dict = {}
        self.fa_list = []
        self.vector_dict = {}
        self.load_aicore_perf_rules()

    @staticmethod
    def get_operator_list(cube_dict, profiling_dataset):
        operator_list = []
        for op in profiling_dataset.op_summary.op_list:
            if op.op_name in cube_dict:
                key = op.input_shapes[1:-1] + "-" + op.output_shapes[1:-1]
                if key in cube_dict[op.op_name]:
                    operator_list.append(op)
        return operator_list

    @staticmethod
    def get_vector_list(profiling_dataset, vector_dict):
        vector_list = []
        for op_name in vector_dict:
            for shape in vector_dict[op_name]:
                for operator in profiling_dataset.op_summary.op_list:
                    if operator.op_name == op_name and operator.input_shapes[1:-1] + "-" + operator.output_shapes[
                                                                                           1:-1] == shape:
                        vector_list.append(operator)
        return vector_list

    @staticmethod
    def safe_divide(numerator, denominator):
        if denominator == 0:
            logger.warning("Warning: Division by zero is not allowed.")
            return None
        return numerator / denominator

    @staticmethod
    def memory_size(operator):
        memory = 0
        input_shapes = operator.input_shapes[1:-1].split(";")
        output_shapes = operator.output_shapes[1:-1]
        for shapes in input_shapes:
            if "," not in shapes and shapes != "":
                # 多的一维是 bias ，预先乘2
                memory += convert_to_int_with_exception(shapes) * 2
                continue
            memory += reduce(lambda x, y: x * y, map(int, shapes.split(",")))
        memory += reduce(lambda x, y: x * y, map(int, output_shapes.split(",")))
        return memory * 2 / 1024 / 1024

    def load_aicore_perf_rules(self):
        language = AdditionalArgsManager().language
        rule_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))),
            "rules", language, "aicore_performance.yaml"
        )

        if not os.path.exists(rule_path):
            logger.warning("Skip analyze aicpu issues, because %s does not exist.", rule_path)

        self.language = language
        self.aicore_rules = FileManager.read_yaml_file(rule_path)
        self._cube_problem = self.aicore_rules.get("cube_problem")
        self._fa_problem = self.aicore_rules.get("fa_problem")
        self._vector_problem = self.aicore_rules.get("vector_problem")
        self._desc = self.aicore_rules.get("description")
        self._bound_desc = self.aicore_rules.get("bound_description")
        self._opti_desc = self.aicore_rules.get("optimization_description")
        self._affinity_desc = self.aicore_rules.get("affinity_description")
        self._cube_affinity_desc = self.aicore_rules.get("cube_affinity_desc")
        self._fa_affinity_desc_head_dim_128 = self.aicore_rules.get("fa_affinity_desc_head_dim_128")
        self._fa_affinity_desc_seq_len_128 = self.aicore_rules.get("fa_affinity_desc_seq_len_128")
        self._fa_affinity_desc_head_dim_seq_len_128 = self.aicore_rules.get("fa_affinity_desc_head_dim_seq_len_128")
        self._suggestion = self.aicore_rules.get("suggestion")
        self._affinity_suggestion = self.aicore_rules.get("affinity_suggestion")
        self._bound_suggestion = self.aicore_rules.get("bound_suggestion")
        self._opti_suggestion = self.aicore_rules.get("optimization_suggestion")
        self._operator_rules = {"cube_operators": self.aicore_rules.get("cube_operators"),
                                "fa_operators": self.aicore_rules.get("fa_operators"),
                                "vector_operators": self.aicore_rules.get("vector_operators")}

    def data_filter(self, profiling_dataset: ProfilingDataset):
        if not self.check_task_list(profiling_dataset):
            return

        operator_list = profiling_dataset.op_summary.op_list
        total_duration = sum(convert_to_float_with_warning(operator.task_duration) for operator in operator_list)
        if (total_duration == 0):
            return
        cube_memory_dict, vector_type_dict = {}, {}

        for op in operator_list:
            if not op.input_shapes or not op.output_shapes:
                continue
            shapes = op.input_shapes[1:-1] + "-" + op.output_shapes[1:-1]
            # preliminary filter cube operator
            if op.task_type == "AI_CORE" and "matmul" in op.op_type.lower():
                cube_memory_dict.setdefault(op.op_name, {}).setdefault(shapes, 0)
                cube_memory_dict[op.op_name][shapes] += self.memory_size(op)
                continue

            # filter fa operator
            if op.op_type == "FlashAttentionScore":
                self.fa_dict.setdefault(op.op_name, set()).add(shapes)
                self.fa_list.append(op)
            elif op.op_type == "FlashAttentionScoreGrad":
                self.fa_dict.setdefault(op.op_name, set()).add(shapes + "-grad")
                self.fa_list.append(op)

            # preliminary filter vector operator
            if op.task_type in ["AI_VECTOR_CORE", "MIX_AIV"]:
                vector_type_dict.setdefault(op.op_type, set()).add(op)

        # filter cube operator
        for op_name in cube_memory_dict:
            for shapes in cube_memory_dict[op_name]:
                if cube_memory_dict[op_name][shapes] >= self.CUBE_OPERATOR_MEMORY_SIZE_MB:
                    self.cube_dict.setdefault(op_name, set()).add(shapes)

        # filter vector operator
        for op_type in vector_type_dict:
            duration_group_by_time = sum(convert_to_float_with_warning(op.task_duration)
                                         for op in vector_type_dict[op_type])
            if (duration_group_by_time / total_duration) >= 0.01 or duration_group_by_time >= 1000000:
                for op in vector_type_dict[op_type]:
                    shapes = op.input_shapes[1:-1] + "-" + op.output_shapes[1:-1]
                    self.vector_dict.setdefault(op.op_name, set()).add(shapes)

        if any([self.cube_dict, self.fa_dict, self.vector_dict]):
            self.ai_core_performance_issues = True

    def check_ai_core_performance(self, promoting_dataset: ProfilingDataset):
        for operator_type in ["cube", "fa", "vector"]:
            try:
                self.result[operator_type] = getattr(self, f"check_{operator_type}_operator")(promoting_dataset)
            except (IndexError, ValueError, AttributeError) as e:
                logger.warning(f"Failed to check ai core performance {operator_type} operator, {e}.")
                self.result[operator_type] = []

        if not any([self.result["cube"], self.result["fa"], self.result["vector"]]):
            self.ai_core_performance_issues = False

    def check_cube_operator(self, profiling_dataset: ProfilingDataset):
        cube_dict = self.cube_dict
        suggestion = self._cube_affinity_desc
        optimization_queue, bound_queue, affinity_queue = [], [], []
        operator_list = self.get_operator_list(cube_dict, profiling_dataset)
        for op in cube_dict:
            for shape in cube_dict[op]:
                affinity_flag = self._check_cube_inner_axis(shape)
                if not affinity_flag:
                    dtype, shape_duration = None, 0.
                    for operator in operator_list:
                        if (operator.op_name == op and
                                operator.input_shapes[1:-1] + "-" + operator.output_shapes[1:-1] == shape):
                            dtype = operator.input_data_types
                            shape_duration += convert_to_float_with_warning(operator.task_duration)
                    affinity_queue.append({"op_name": op,
                                           "shape": shape.split("-")[0],
                                           "dtype": dtype,
                                           "duration": shape_duration,
                                           "suggestion": suggestion})
                else:
                    shape_list = []
                    for operator in operator_list:
                        if (operator.op_name == op and operator.input_shapes[1:-1] + "-" +
                                operator.output_shapes[1:-1] == shape):
                            shape_list.append(operator)
                    shape_duration = sum(convert_to_float_with_warning(operator.task_duration)
                                         for operator in shape_list)
                    dtype = shape_list[0].input_data_types if shape_list else None
                    bound, optimization = self.del_cube_operator_bound(shape_list)
                    if bound is None and optimization is None:
                        continue
                    if bound:
                        bound_queue.append({"op_name": op,
                                            "shape": shape.split("-")[0],
                                            "dtype": dtype,
                                            "bound": bound,
                                            "duration": shape_duration})
                    else:
                        optimization_queue.append({"op_name": op,
                                                   "shape": shape.split("-")[0],
                                                   "dtype": dtype,
                                                   "optimization": round(optimization * 100, 2)})
        return [sorted(optimization_queue, key=lambda x: x["optimization"], reverse=True)[:5],
                sorted(bound_queue, key=lambda x: x["duration"], reverse=True)[:5],
                sorted(affinity_queue, key=lambda x: x["duration"], reverse=True)[:5]]

    def del_cube_operator_bound(self, shape_list):
        bound, optimization, aic_mac_ratio, aic_mte2_ratio, length = "", 0., 0., 0., 0
        for operator in shape_list:
            try:
                aic_mac_ratio += convert_to_float_with_warning(operator.aic_mac_ratio)
                aic_mte2_ratio += convert_to_float_with_warning(operator.aic_mte2_ratio)
                length += 1
            except ValueError:
                continue
        aic_mac_ratio = self.safe_divide(aic_mac_ratio, length)
        aic_mte2_ratio = self.safe_divide(aic_mte2_ratio, length)
        if aic_mac_ratio is None or aic_mte2_ratio is None:
            return None, None
        aic_mac_ratio_rule, aic_mte2_ratio_rule = None, None
        for operator_rule in self._operator_rules["cube_operators"]:
            if operator_rule["target"] == "aic_mac_ratio":
                aic_mac_ratio_rule = operator_rule
            elif operator_rule["target"] == "aic_mte2_ratio":
                aic_mte2_ratio_rule = operator_rule
        if (aic_mac_ratio >= aic_mac_ratio_rule["threshold"]
                and aic_mte2_ratio >= aic_mte2_ratio_rule["threshold"]):
            bound = aic_mac_ratio_rule["bound"] + "_and_" + aic_mte2_ratio_rule["bound"] + "_bound"
        elif aic_mac_ratio >= aic_mte2_ratio_rule["threshold"]:
            bound = aic_mac_ratio_rule["bound"]
        elif aic_mte2_ratio >= aic_mte2_ratio_rule["threshold"]:
            bound = aic_mte2_ratio_rule["bound"]
        else:
            optimization = max(aic_mac_ratio_rule["threshold"] - aic_mac_ratio,
                               aic_mte2_ratio_rule["threshold"] - aic_mte2_ratio)
        return bound, optimization

    def check_fa_operator(self, profiling_dataset: ProfilingDataset):
        fa_list, fa_dict = self.fa_list, self.fa_dict
        optimization_queue, bound_queue, affinity_queue = [], [], []
        # 不亲和算子筛选
        for op in fa_dict:
            for shape in fa_dict[op]:
                affinity_flag, dtype, shape_duration, suggestion = self._check_fa_inner_axis(fa_list, op, shape)
                if affinity_flag:
                    # 不亲和算子 计算耗时，加入affinity_queue
                    affinity_queue.append({"op_name": op,
                                           "shape": shape.split("-")[0],
                                           "dtype": dtype,
                                           "suggestion": suggestion,
                                           "duration": shape_duration})
                else:
                    # 处理bound算子和优化算子
                    if len(shape.split("-")) > 2:
                        bound, optimization, dtype, shape_duration = self.del_fa_operator_bound_grad(op, shape, fa_list)
                    else:
                        bound, optimization, dtype, shape_duration = self.del_fa_operator_bound(op, shape, fa_list)
                    if bound is None and optimization is None:
                        continue
                    if bound:
                        bound_queue.append({"op_name": op,
                                            "shape": shape.split("-")[0],
                                            "dtype": dtype,
                                            "bound": bound,
                                            "duration": shape_duration})
                    else:
                        optimization_queue.append({"op_name": op,
                                                   "shape": shape.split("-")[0],
                                                   "dtype": dtype,
                                                   "optimization": round(optimization * 100, 2)})

        return [sorted(optimization_queue, key=lambda x: x["optimization"], reverse=True)[:5],
                sorted(bound_queue, key=lambda x: x["duration"], reverse=True)[:5],
                sorted(affinity_queue, key=lambda x: x["duration"], reverse=True)[:5]]

    def del_fa_operator_bound_grad(self, op, shape, fa_list):
        aic_fixpipe_ratio, aic_mte2_ratio, shape_duration, optimization, length = 0., 0., 0., 0., 0
        bound, dtype = "", None
        for operator in fa_list:
            if (operator.op_name == op and
                    operator.input_shapes[1:-1] + "-" +
                    operator.output_shapes[1:-1] + "-grad" == shape):
                try:
                    aic_fixpipe_ratio += convert_to_float_with_warning(operator.aic_fixpipe_ratio)
                    aic_mte2_ratio += convert_to_float_with_warning(operator.aic_mte2_ratio)
                    shape_duration += convert_to_float_with_warning(operator.task_duration)
                    dtype = operator.input_data_types
                    length += 1
                except ValueError:
                    continue
        aic_fixpipe_ratio = self.safe_divide(aic_fixpipe_ratio, length)
        aic_mte2_ratio = self.safe_divide(aic_mte2_ratio, length)
        if aic_mte2_ratio is None or aic_fixpipe_ratio is None:
            return None, None, None, None
        aic_fixpipe_ratio_rule, aic_mte2_ratio_rule = None, None
        for rule in self._operator_rules["fa_operators"]:
            if rule["target"] == "aic_fixpipe_ratio":
                aic_fixpipe_ratio_rule = rule
            elif rule["target"] == "aic_mte2_ratio":
                aic_mte2_ratio_rule = rule
        if (aic_mte2_ratio >= aic_mte2_ratio_rule["threshold"] and
                aic_fixpipe_ratio >= aic_fixpipe_ratio_rule["threshold"]):
            bound = aic_fixpipe_ratio_rule["bound"] + "_and_" + aic_mte2_ratio_rule["bound"] + "_bound"
        elif aic_mte2_ratio >= aic_mte2_ratio_rule["threshold"]:
            bound = aic_mte2_ratio_rule["bound"]
        elif aic_fixpipe_ratio >= aic_fixpipe_ratio_rule["threshold"]:
            bound = aic_fixpipe_ratio_rule["bound"]
        else:
            optimization = max(aic_fixpipe_ratio_rule["threshold"] - aic_fixpipe_ratio,
                               aic_mte2_ratio_rule["threshold"] - aic_mte2_ratio)
        return bound, optimization, dtype, shape_duration

    def del_fa_operator_bound(self, op, shape, fa_list):
        aiv_vec_ratio, aic_mte2_ratio, shape_duration, optimization, length = 0., 0., 0., 0., 0
        bound, dtype = "", None
        for operator in fa_list:
            if (operator.op_name == op and
                    operator.input_shapes[1:-1] + "-" + operator.output_shapes[1:-1] == shape):
                try:
                    aiv_vec_ratio += convert_to_float_with_warning(operator.aiv_vec_ratio)
                    aic_mte2_ratio += convert_to_float_with_warning(operator.aic_mte2_ratio)
                    shape_duration += convert_to_float_with_warning(operator.task_duration)
                    length += 1
                except ValueError:
                    continue
        aiv_vec_ratio = self.safe_divide(aiv_vec_ratio, length)
        aic_mte2_ratio = self.safe_divide(aic_mte2_ratio, length)
        if aiv_vec_ratio is None or aic_mte2_ratio is None:
            return None, None, None, None
        aiv_vec_ratio_rule, aic_mte2_ratio_rule = None, None
        for rule in self._operator_rules["fa_operators"]:
            if rule["target"] == "aiv_vec_ratio":
                aiv_vec_ratio_rule = rule
            elif rule["target"] == "aic_mte2_ratio":
                aic_mte2_ratio_rule = rule
        if (aic_mte2_ratio >= aic_mte2_ratio_rule["threshold"]
                and aiv_vec_ratio >= aiv_vec_ratio_rule["threshold"]):
            bound = aic_mte2_ratio_rule["bound"] + "_and_" + aiv_vec_ratio_rule["bound"] + "_bound"
        elif aic_mte2_ratio >= aic_mte2_ratio_rule["threshold"]:
            bound = aic_mte2_ratio_rule["bound"]
        elif aiv_vec_ratio >= aiv_vec_ratio_rule["threshold"]:
            bound = aiv_vec_ratio_rule["bound"]
        else:
            optimization = max(aiv_vec_ratio_rule["threshold"] - aiv_vec_ratio,
                               aic_mte2_ratio_rule["threshold"] - aic_mte2_ratio)
        return bound, optimization, dtype, shape_duration

    def check_vector_operator(self, profiling_dataset: ProfilingDataset):
        vector_dict = self.vector_dict
        optimization_queue, bound_queue = [], []
        vector_list = self.get_vector_list(profiling_dataset, vector_dict)
        for op_name in vector_dict:
            for shape in vector_dict[op_name]:
                aiv_vec_ratio, aiv_mte2_ratio, aiv_mte3_ratio, shape_duration = 0., 0., 0., 0.
                length, dtype = 0, ""
                for operator in vector_list:
                    if (operator.op_name == op_name and
                            operator.input_shapes[1:-1] + "-" + operator.output_shapes[1:-1] == shape):
                        try:
                            aiv_vec_ratio += convert_to_float_with_warning(operator.aiv_vec_ratio)
                            aiv_mte2_ratio += convert_to_float_with_warning(operator.aiv_mte2_ratio)
                            aiv_mte3_ratio += convert_to_float_with_warning(operator.aiv_mte3_ratio)
                            shape_duration += convert_to_float_with_warning(operator.task_duration)
                            dtype = operator.input_data_types
                            length += 1
                        except ValueError:
                            continue
                aiv_vec_ratio = self.safe_divide(aiv_vec_ratio, length)
                aiv_mte2_ratio = self.safe_divide(aiv_mte2_ratio, length)
                aiv_mte3_ratio = self.safe_divide(aiv_mte3_ratio, length)
                if aiv_vec_ratio is None or aiv_mte2_ratio is None or aiv_mte3_ratio is None:
                    continue
                bound, optimization = self.del_vector_operator_bound(aiv_mte2_ratio, aiv_mte3_ratio, aiv_vec_ratio)
                if bound:
                    bound_queue.append({"op_name": op_name,
                                        "shape": shape.split("-")[0],
                                        "bound": bound,
                                        "dtype": dtype,
                                        "duration": shape_duration})
                else:
                    optimization_queue.append({"op_name": op_name,
                                               "shape": shape.split("-")[0],
                                               "dtype": dtype,
                                               "optimization": round(optimization * 100, 2)})
        return [sorted(optimization_queue, key=lambda x: x["optimization"], reverse=True)[:5],
                sorted(bound_queue, key=lambda x: x["duration"], reverse=True)[:5]]

    def del_vector_operator_bound(self, aiv_mte2_ratio, aiv_mte3_ratio, aiv_vec_ratio):
        bound, optimization = "", 0
        aiv_vec_ratio_rule, aiv_mte2_ratio_rule, aiv_mte3_ratio_rule, total_rule = None, None, None, None
        for operator_rule in self._operator_rules["vector_operators"]:
            if operator_rule["target"] == "aiv_vec_ratio":
                aiv_vec_ratio_rule = operator_rule
            elif operator_rule["target"] == "aiv_mte2_ratio":
                aiv_mte2_ratio_rule = operator_rule
            elif operator_rule["target"] == "aiv_mte3_ratio":
                aiv_mte3_ratio_rule = operator_rule
            elif operator_rule["target"] == "total":
                total_rule = operator_rule
        if aiv_vec_ratio + aiv_mte2_ratio + aiv_mte3_ratio >= total_rule["threshold"]:
            bound = total_rule["bound"]
        elif aiv_mte2_ratio >= aiv_mte2_ratio_rule["threshold"]:
            bound = aiv_mte2_ratio_rule["bound"]
        elif aiv_mte3_ratio >= aiv_mte3_ratio_rule["threshold"]:
            bound = aiv_mte3_ratio_rule["bound"]
        elif aiv_vec_ratio >= aiv_vec_ratio_rule["threshold"]:
            bound = aiv_vec_ratio_rule["bound"]
        else:
            optimization = max(aiv_vec_ratio_rule["threshold"] - aiv_vec_ratio,
                               aiv_mte2_ratio_rule["threshold"] - aiv_mte2_ratio,
                               aiv_mte3_ratio_rule["threshold"] - aiv_mte3_ratio)
        return bound, optimization

    def draw_record(self, op_type: str, result: OptimizeResult):
        suggestion_keys = ['opti', 'bound', 'affinity']
        desc = dict.fromkeys(suggestion_keys, "")
        problem_map = {
            'cube': self._cube_problem,
            'fa': self._fa_problem,
            'vector': self._vector_problem
        }
        if op_type not in problem_map:
            return
        optimization_item = OptimizeItem(problem_map[op_type], self._desc, [self._suggestion])
        result.add(OptimizeRecord(optimization_item))
        headers = [
            "Type",
            "Description",
        ]
        result.add_detail(problem_map[op_type], headers=headers)
        for opti_issue in self.result[op_type][0]:
            opti_sugg = self._opti_suggestion.format(**opti_issue)
            desc["opti"] += opti_sugg
        if desc["opti"]:
            result.add_detail(problem_map[op_type], detail=[self._opti_desc, desc["opti"]])
        for bound_issue in self.result[op_type][1]:
            bound_sugg = self._bound_suggestion.format(**bound_issue)
            desc["bound"] += bound_sugg
        if desc["bound"]:
            result.add_detail(problem_map[op_type], detail=[self._bound_desc, desc["bound"]])
        if op_type == "vector":  # vector 类型没有亲和性建议
            return
        for affinity_issue in self.result[op_type][2]:
            affinity_sugg = self._affinity_suggestion.format(**affinity_issue)
            desc["affinity"] += affinity_sugg
        if desc["affinity"]:
            result.add_detail(problem_map[op_type], detail=[self._affinity_desc, desc["affinity"]])

    def make_record(self, result: OptimizeResult):
        """
        make record for what and how to optimize
        """
        if not self.ai_core_performance_issues:
            return self.ai_core_performance_issues
        if any(self.result["cube"]):
            self.draw_record("cube", result)
        if any(self.result["fa"]):
            self.draw_record("fa", result)
        if any(self.result["vector"]):
            self.draw_record("vector", result)

        return True

    def make_render(self, html_render, add_render_list=True, **kwargs):
        if not self.ai_core_performance_issues:
            return self.ai_core_performance_issues

        priority = kwargs.get("priority")
        return html_render.render_template(key="computation",
                                           template_dir="templates",
                                           template_name="ai_core_performance.html",
                                           format_result=self.result,
                                           language=self.language,
                                           add_render_list=add_render_list,
                                           priority_background_color=priority,
                                           rank=kwargs.get("rank"))

    def check_task_list(self, profiling_dataset: ProfilingDataset) -> bool:
        if not hasattr(profiling_dataset, "op_summary"):
            logger.warning("Skip %s checker because of not containing %s", self._CHECKER, "op summary")
            return False
        if not hasattr(profiling_dataset.op_summary, "op_list"):
            logger.warning("Skip %s checker because of not containing %s", self._CHECKER, "op_list")
            return False
        if (not hasattr(profiling_dataset.op_summary.op_list[0], "input_shapes") or
                not hasattr(profiling_dataset.op_summary.op_list[0], "input_data_types")):
            logger.warning("Skip %s checker because of not containing input datas", self._CHECKER)
            return False
        return True

    def _check_cube_inner_axis(self, shape):
        shapes = shape.split("-")[0].split(";")
        if len(shapes) < 2:
            logger.error(f"Error: Incorrect input shape, shape is {shape}.")
            return False
        # 判断输入shape内轴是否为256的倍数
        if len(shapes[0].split(",")) == 4 and len(shapes[1].split(",")) == 4:
            # NZ格式
            b_axis, c_axis = (convert_to_int_with_exception(shapes[0].split(",")[1]),
                              convert_to_int_with_exception(shapes[0].split(",")[2]))
            f_axis, g_axis = (convert_to_int_with_exception(shapes[1].split(",")[1]),
                              convert_to_int_with_exception(shapes[1].split(",")[2]))
            return (b_axis * c_axis % self.INNER_AXIS_256 == 0) and (f_axis * g_axis % self.INNER_AXIS_256 == 0)
        elif (len(shape.split("-")[0].split(";")[0].split(","))) == 2:
            # ND格式
            l_axis, k_axis = (convert_to_int_with_exception(shapes[0].split(",")[-1]),
                              convert_to_int_with_exception(shapes[1].split(",")[-1]))
            return (l_axis % self.INNER_AXIS_256 == 0) and (k_axis % self.INNER_AXIS_256 == 0)
        else:
            return False

    def _check_fa_inner_axis(self, fa_list, op, shape):
        shape_duration = 0.
        affinity_flag = False
        dtype = None
        suggestion = ""
        if "varlen" in op.lower():
            # 处理变长算子 如果不亲和则affinity_flag为False
            inner_axis = 0
            if len(shape.split("-")[0].split(";")[0].split(",")) >= 3:
                inner_axis = convert_to_int_with_exception(shape.split("-")[0].split(";")[0].split(",")[2])
            if inner_axis % self.INNER_AXIS_128 != 0:
                affinity_flag = True
                suggestion = self._fa_affinity_desc_head_dim_128
                for operator in fa_list:
                    if (operator.op_name == op and
                            operator.input_shapes[1:-1] + "-" + operator.output_shapes[1:-1] == shape):
                        shape_duration += convert_to_float_with_warning(operator.task_duration)
                        dtype = operator.input_data_types
        else:
            # 处理定长算子 如果不亲和则affinity_flag为False
            head_dim = 0
            seq_len = 0
            if len(shape.split("-")[1].split(";")[0].split(",")[2]) >= 3:
                seq_len = convert_to_int_with_exception(shape.split("-")[1].split(";")[0].split(",")[2])
            input_first_tensor = shape.split("-")[0].split(";")[0].split(",")
            if len(input_first_tensor) == 3:
                head_dim = safe_division(convert_to_int_with_exception(input_first_tensor[2]),
                                         convert_to_int_with_exception(shape.split("-")[1].split(";")[0].split(",")[1]))
            else:
                head_dim = convert_to_int_with_exception(input_first_tensor[3])
            if head_dim % self.INNER_AXIS_128 != 0 and seq_len % self.INNER_AXIS_128 != 0:
                affinity_flag = True
                suggestion = self._fa_affinity_desc_head_dim_seq_len_128
            elif head_dim % self.INNER_AXIS_128 != 0:
                affinity_flag = True
                suggestion = self._fa_affinity_desc_head_dim_128
            elif seq_len % self.INNER_AXIS_128 != 0:
                affinity_flag = True
                suggestion = self._fa_affinity_desc_seq_len_128
            if affinity_flag:
                for operator in fa_list:
                    if (operator.op_name == op and
                            operator.input_shapes[1:-1] + "-" +
                            operator.output_shapes[1:-1] == shape):
                        shape_duration += convert_to_float_with_warning(operator.task_duration)
                        dtype = operator.input_data_types
        return affinity_flag, dtype, shape_duration, suggestion
