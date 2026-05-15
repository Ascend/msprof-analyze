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
import os

from msprof_analyze.advisor.analyzer.base_analyzer import BaseAnalyzer
from msprof_analyze.advisor.display.html.render import HTMLRender
from msprof_analyze.advisor.display.prompt.base_prompt import BasePrompt
from msprof_analyze.advisor.result.item import OptimizeItem, OptimizeRecord
from msprof_analyze.advisor.result.result import OptimizeResult
from msprof_analyze.compare_tools.compare_interface.comparison_interface import ComparisonInterface
from msprof_analyze.prof_common.additional_args_manager import AdditionalArgsManager
from msprof_analyze.prof_common.constant import Constant
from msprof_analyze.prof_common.logger import get_logger
from msprof_analyze.prof_common.path_manager import PathManager

logger = get_logger()


class OverallSummaryAnalyzer(BaseAnalyzer):

    def __init__(self, collection_path: str, n_processes: int = 1, **kwargs):
        profile_path = get_profile_path(collection_path)
        super().__init__(profile_path, n_processes, **kwargs)
        self.benchmark_profiling_path = kwargs.get("benchmark_profiling_path", "")
        self._has_benchmark_profiling = False
        self._is_minimal_profiling = False
        self.cur_data = {}
        self.cur_bottleneck = {}
        self._disaggregate_perf = {}
        self._disaggregate_benchmark_perf = {}
        self.cur_advices = ""
        self.html_render = HTMLRender()
        self.result = OptimizeResult()
        self.bottleneck_str = ""
        self.over_summary_analysis = {}

        self.prompt_class = BasePrompt.get_prompt_class(self.__class__.__name__)
        self.over_summary_analyzer = self.prompt_class.OVERALL_SUMMARY_ANALYZER
        self.advice_map = self.prompt_class.PERFORMANCE_TIME_DICT
        self.time_name_map = self.prompt_class.TIME_NAME_MAP
        self.performance_time_dict = self.prompt_class.PERFORMANCE_TIME_DICT

    @staticmethod
    def calculate_ratio(dividend, divisor):
        if not divisor:
            return float("inf")
        return dividend / divisor

    @staticmethod
    def get_time_category_dict(overall_dict: dict):
        language = AdditionalArgsManager().language
        if language == "en":
            time_category_dict = {
                "Computing Time": round(overall_dict.get('computing_time_ms', 0.0), 3),
                "Uncovered Communication Time": round(overall_dict.get('uncovered_communication_time_ms', 0.0), 3),
                "Free Time": round(overall_dict.get('free_time_ms', 0.0), 3)
            }
        else:
            time_category_dict = {
                "计算时长": round(overall_dict.get('computing_time_ms', 0.0), 3),
                "未被掩盖的通信时长": round(overall_dict.get('uncovered_communication_time_ms', 0.0), 3),
                "空闲时长": round(overall_dict.get('free_time_ms', 0.0), 3)
            }
        return time_category_dict

    def path_check(self):
        if self.benchmark_profiling_path:
            if os.path.exists(self.benchmark_profiling_path):
                self._has_benchmark_profiling = True
            else:
                logger.warning("Invalid path which not exists: %s.", self.benchmark_profiling_path)
        return os.path.exists(self.collection_path)

    def process(self):
        self._disaggregate_perf = ComparisonInterface(self.collection_path).disaggregate_perf(Constant.OVERALL_COMPARE)
        if not self._disaggregate_perf:
            return
        self._is_minimal_profiling = self._disaggregate_perf.get("minimal_profiling", False)
        self.cur_data["overall_data"] = self.get_time_category_dict(self._disaggregate_perf.get('overall', {}))
        if self._has_benchmark_profiling:
            self._disaggregate_benchmark_perf = ComparisonInterface(
                self.benchmark_profiling_path).disaggregate_perf(Constant.OVERALL_COMPARE)

    def identify_bottleneck(self):
        overall_data = self.cur_data.get("overall_data")
        if not overall_data:
            return
        e2e_time = round(sum([data for data in overall_data.values()]), 3)

        language = AdditionalArgsManager().language
        if language == "en":
            overall_bottleneck = f"The Model E2E Time is {e2e_time}ms.\n"
        else:
            overall_bottleneck = f"模型E2E的时间是{e2e_time}ms。\n"
        comparison_bottleneck = ""
        for time_type, time_value in overall_data.items():
            # add overall bottleneck
            if language == "en":
                overall_bottleneck += f"    -- {time_type} is {time_value}ms\n"
            else:
                overall_bottleneck += f"    -- {time_type}是{time_value}ms\n"
            if time_type == "Free Time" and self._is_minimal_profiling and self.calculate_ratio(time_value,
                                                                                                e2e_time) > 0.1:
                if language == "en":
                    overall_bottleneck += "percentage of free time exceed the threshold 10%."
                else:
                    overall_bottleneck += "空闲时间的百分比超过了阈值的10%。"
            if not self._has_benchmark_profiling:
                continue
            # add comparison bottleneck
            base_duration = self.get_time_category_dict(
                self._disaggregate_benchmark_perf.get('overall', {})
            ).get(time_type)
            if time_value > base_duration:
                ratio = "{:.2%}".format(self.calculate_ratio(time_value - base_duration, base_duration))
                if language == "en":
                    comparison_bottleneck += f"{time_type} exceeds the benchmark by {ratio}\n"
                else:
                    comparison_bottleneck += f"{time_type}超过了基线{ratio}。\n"
        self.cur_bottleneck["overall_data"] = overall_bottleneck
        if comparison_bottleneck:
            self.cur_bottleneck["comparison_result"] = comparison_bottleneck

    def optimize(self, **kwargs):
        if self.path_check():
            self.process()
        self.identify_bottleneck()
        self.format_bottleneck()
        self.format_over_summary_analysis()
        self.make_record()
        self.make_render()
        return self.result

    def format_bottleneck(self):
        result = ''
        for _, value in self.cur_bottleneck.items():
            if not value:
                continue
            result += f'{value} \n'
        self.bottleneck_str = result

    def format_over_summary_analysis(self):
        headers = ['Performance Index', 'Duration(ms)', 'Duration Ratio']
        performance_data = self.get_analysis_data(self._disaggregate_perf)
        benchmark_data = self.get_analysis_data(self._disaggregate_benchmark_perf)
        if self._has_benchmark_profiling:
            headers.append('Diff Duration(ms)')
            self.format_analysis_with_benchmark(performance_data, benchmark_data, headers)
        else:
            self.format_analysis_only(performance_data, headers)

    def get_analysis_data(self, data_dict: dict):
        if not data_dict:
            return {}
        return {
            **data_dict.get("overall"),
            **data_dict.get("computing_time_disaggregate"),
            **data_dict.get("communication_time_disaggregate"),
            **data_dict.get("free_time_disaggregate"),
        }

    def format_analysis_only(self, performance_data: dict, headers: list):
        res = []
        total_duration = performance_data.get('e2e_time_ms', 0.0)
        for time_name, time_key in self.performance_time_dict.items():
            row = [time_name]
            duration = performance_data.get(time_key, 0.0)
            row.append("{:.3f}".format(duration))
            row.append("{:.2%}".format(self.calculate_ratio(duration, total_duration)))
            res.append(row)
        self.over_summary_analysis["headers"] = headers
        self.over_summary_analysis["data"] = res

    def format_analysis_with_benchmark(self, performance_data: dict, benchmark_data: dict, headers: list):
        res = []
        total_duration = performance_data.get('e2e_time_ms', 0.0)
        for time_name, time_key in self.performance_time_dict.items():
            row = [time_name]
            duration = performance_data.get(time_key, 0.0)
            row.append("{:.3f}".format(duration))
            row.append("{:.2%}".format(self.calculate_ratio(duration, total_duration)))
            row.append("{:.3f}".format(duration - benchmark_data.get(time_key, 0.0)))
            res.append(row)
        self.over_summary_analysis["headers"] = headers
        self.over_summary_analysis["data"] = res

    def make_record(self):
        """
        make record for what and how to optimize
        """
        if not self.bottleneck_str and not self.cur_advices:
            return
        optimization_item = OptimizeItem(
            self.over_summary_analyzer,
            self.bottleneck_str,
            self.cur_advices
        )
        self.result.add(OptimizeRecord(optimization_item))

        self.result.add_detail(
            self.over_summary_analyzer,
            headers=self.over_summary_analysis["headers"]
        )
        for data in self.over_summary_analysis["data"]:
            self.result.add_detail(self.over_summary_analyzer, detail=data)

    def make_render(self):
        if not self.bottleneck_str and not self.cur_advices:
            return
        # 将\n替换为html换行
        bottleneck_str = self.bottleneck_str.replace('\n', '<br />')
        result_for_html = {
            "Description": bottleneck_str,
            "suggestion": self.cur_advices,
            "details": [self.over_summary_analysis]
        }
        self.html_render.render_template(key="overall",
                                         title="Overall Summary",
                                         template_dir="templates",
                                         template_name="cluster_analysis.html",
                                         cann_version=self.cann_version,
                                         profiling_type=self.profiling_type,
                                         profiling_version=self.profiling_version,
                                         result=result_for_html)

    def get_priority(self, max_mem_op_dur=None):
        pass


def get_profile_path(collection_path):
    for root, _, files in PathManager.limited_depth_walk(collection_path):
        for file in files:
            if file.startswith("profiler_info"):
                return root
    return ""
