# Copyright (c) 2023, Huawei Technologies Co., Ltd.
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

from msprof_analyze.advisor.analyzer.base_analyzer import BaseAnalyzer
from msprof_analyze.prof_common.constant import Constant
from msprof_analyze.advisor.result.result import OptimizeResult
from msprof_analyze.advisor.result.item import OptimizeItem, OptimizeRecord
from msprof_analyze.advisor.dataset.cluster.cluster_dataset import ClusterStepTraceTimeDataset
from msprof_analyze.advisor.utils.utils import safe_index_value, safe_division, convert_to_int, safe_index, \
    convert_to_float
from msprof_analyze.prof_common.additional_args_manager import AdditionalArgsManager

logger = get_logger()


class SlowRankAnalyzer(BaseAnalyzer):
    SLOW_RANK_ANALYSIS = "slow rank"
    SLOW_RANK_ANALYSIS_CN = "慢卡分析"
    RANK = "rank"
    RATIO_THRESHOLD = 0.05
    BOTTLENECK_LIST = ['Computing', 'Communication', "Free"]
    BOTTLENECK_LIST_CN = ['计算', '通信', "空闲"]
    dataset_cls_list = [ClusterStepTraceTimeDataset]
    COMPUTE = "compute(us)"
    FREE = "free(us)"
    COMMUNICATION = "communication(us)"

    def __init__(self, collection_path, n_processes: int = 1, **kwargs):
        super().__init__(collection_path, n_processes, **kwargs)
        key = ClusterStepTraceTimeDataset.get_key()
        self.step_trace_class = self.get_first_data_by_key(self.dataset_list, key)
        self.step_trace_dict = self.step_trace_class.get_data()
        self.stages = self.step_trace_class.get_stages()
        self.result = OptimizeResult()
        self.bottelneck = ''
        self.suggestion = ''
        self._steps = set()
        self.format_datas = {}
        if self.step_trace_dict is not None:
            self.format_datas = self.format_details()

    @property
    def steps(self):
        return sorted(list(self._steps))

    @staticmethod
    def compute_max_gap_ratio(data: list, mean: float):
        if mean == 0:
            return 0
        else:
            return (max(data) - min(data)) / mean

    def optimize(self, **kwargs):
        if self.step_trace_dict is None:
            logger.error(
                "Slow rank analysis failed, "
                "please ensure file 'step_trace_time.csv' exists in your profiling directory %s",
                Constant.ASCEND_PROFILER_OUTPUT)
            return self.result
        self.process()
        self.make_record()
        self.make_render(kwargs.get("template_key"))
        return self.result

    def process(self):
        total_time_list = [sum(data_tuple) for rank_id, data_tuple in self.step_trace_dict.items()]
        if total_time_list:
            mean_total_time = sum(total_time_list) / len(total_time_list)
            for i in range(len(self.BOTTLENECK_LIST)):
                self.produce_bottleneck(self.step_trace_dict, i, mean_total_time)

        if not self.bottelneck:
            language = AdditionalArgsManager().language
            if language == "en":
                self.bottelneck = "There is no slow rank issues"
            else:
                self.bottelneck = "没有慢节点问题"

    def produce_bottleneck(self, step_dict: dict, produce_type: int, mean_total_time: float):
        data_list = [data_tuple[produce_type] for rank_id, data_tuple in step_dict.items()]
        max_ratio = self.compute_max_gap_ratio(data_list, mean_total_time)
        if max_ratio > self.RATIO_THRESHOLD:
            language = AdditionalArgsManager().language
            if language == "en":
                self.bottelneck += f'{self.BOTTLENECK_LIST[produce_type]} \n' \
                                   f'    has some issues in the cluster, \n' \
                                   f'    because the max difference of {self.BOTTLENECK_LIST[produce_type]} time \n' \
                                   f'    has reached {round(max_ratio * mean_total_time / 1000, 3)}ms. \n'
            else:
                self.bottelneck += f'集群中的{self.BOTTLENECK_LIST_CN[produce_type]}有问题， \n' \
                                   f'因为{self.BOTTLENECK_LIST_CN[produce_type]}时间的最大差距已经达到 \n' \
                                   f'{round(max_ratio * mean_total_time / 1000, 3)}ms。 \n'

    def make_record(self):
        """
        make record for what and how to optimize
        """
        title = self.SLOW_RANK_ANALYSIS_CN
        if AdditionalArgsManager().language == "en":
            title = self.SLOW_RANK_ANALYSIS
        optimization_item = OptimizeItem(
            title,
            self.bottelneck,
            self.suggestion
        )
        self.result.add(OptimizeRecord(optimization_item))

        data_list = self.format_datas.get("data", [])
        headers = self.format_datas.get("headers", [])
        for data in data_list:
            self.result.add_detail(title, headers, data)

    def format_details(self):
        details_dict = {}
        headers = ["step", "rank_id", "compute(us)", "communication(us)", "free(us)"]
        data_list = []
        for key, value in self.step_trace_dict.items():
            step, rank_id = key.split(Constant.STEP_RANK_SEP)
            data_list.append([convert_to_int(step), convert_to_int(rank_id)] + value)
            if step and step not in self._steps:
                self._steps.add(step)

        details_dict["headers"] = headers
        details_dict["data"] = sorted(data_list, key=lambda x: (x[0], x[1]))
        return details_dict

    def make_render(self, template_key="cluster"):
        result_for_html = {
            "Description": self.bottelneck,
            "suggestion": self.suggestion,
            "details": [self.format_datas]
        }

        self.html_render.render_template(key=template_key,
                                         title=SlowRankAnalyzer.SLOW_RANK_ANALYSIS,
                                         template_dir="templates",
                                         template_name="cluster_analysis.html",
                                         cann_version=self.cann_version,
                                         profiling_type=self.profiling_type,
                                         profiling_version=self.profiling_version,
                                         result=result_for_html)

    def get_global_step_rank(self, dimension):
        global_step_rank = {}
        if not self.format_datas:
            return global_step_rank

        headers = self.format_datas.get("headers")

        dimension_index = safe_index_value(headers, dimension)
        rank_id_index = safe_index_value(headers, "rank_id")
        step_index = safe_index_value(headers, "step")
        if dimension_index is None or rank_id_index is None:
            return global_step_rank

        data_list = [tuple_list[dimension_index] for tuple_list in self.format_datas.get("data", [])]
        if not data_list:
            return global_step_rank
        max_time, min_time = max(data_list), min(data_list)

        if self.compute_max_gap_ratio(data_list, sum(data_list) / len(
                data_list)) < self.RATIO_THRESHOLD:
            logger.info("There is no significant difference in computation time among all ranks")
            return global_step_rank
        max_time_index = data_list.index(max_time)
        min_time_index = data_list.index(min_time)

        max_time_rank_id = self.format_datas.get("data")[max_time_index][rank_id_index]
        min_time_rank_id = self.format_datas.get("data")[min_time_index][rank_id_index]

        if step_index is not None:
            max_time_step = self.format_datas.get("data")[max_time_index][step_index]
            min_time_step = self.format_datas.get("data")[min_time_index][step_index]
        else:
            max_time_step, min_time_step = Constant.DEFAULT_STEP, Constant.DEFAULT_STEP

        global_step_rank["maximum"] = {"rank_id": max_time_rank_id, "step": max_time_step}
        global_step_rank["minimum"] = {"rank_id": min_time_rank_id, "step": min_time_step}

        return global_step_rank

    def get_stage_step_rank(self, dimension):
        stage_step_rank = {}
        if not self.format_datas:
            return stage_step_rank

        headers = self.format_datas.get("headers")
        dimension_index = safe_index_value(headers, dimension)
        rank_id_index = safe_index_value(headers, "rank_id")
        step_index = safe_index_value(headers, "step")
        if dimension_index is None or rank_id_index is None:
            return stage_step_rank

        rank_list = [tuple_list[rank_id_index] for tuple_list in self.format_datas.get("data")]
        cost_time_list = [tuple_list[dimension_index] for tuple_list in self.format_datas.get("data")]

        if step_index is not None:
            step_list = [tuple_list[step_index] for tuple_list in self.format_datas.get("data")]
        else:
            step_list = [Constant.DEFAULT_STEP] * len(rank_list)

        for index, stage in enumerate(self.stages):
            tmp_step_list, tmp_rank_list, tmp_time_list = [], [], []
            for step, rank_id, time in zip(step_list, rank_list, cost_time_list):
                if rank_id not in stage:
                    continue

                tmp_step_list.append(step)
                tmp_rank_list.append(rank_id)
                tmp_time_list.append(time)

            if self.compute_max_gap_ratio(tmp_time_list, safe_division(sum(tmp_time_list), len(
                    tmp_time_list))) < self.RATIO_THRESHOLD:
                continue

            max_time, min_time = max(tmp_time_list), min(tmp_time_list)
            max_time_index, min_time_index = tmp_time_list.index(max_time), tmp_time_list.index(min_time)

            stage_key = f"stage-{index}"
            stage_step_rank[stage_key] = {}
            stage_step_rank[stage_key]["maximum"] = {
                "rank_id": tmp_rank_list[max_time_index],
                "step": tmp_step_list[max_time_index],
            }
            stage_step_rank[stage_key]["minimum"] = {
                "rank_id": tmp_rank_list[min_time_index],
                "step": tmp_step_list[min_time_index],
            }

        return stage_step_rank

    def get_step_duration(self, rank_id, step=None):
        # 根据指定rank和step，计算compute, communication, free三个维度之和作为单步耗时，用于计算优先级
        headers = self.format_datas.get("headers")
        default_step_duration = 0.0

        free_col_index = safe_index_value(headers, SlowRankAnalyzer.FREE)
        compute_col_index = safe_index_value(headers, SlowRankAnalyzer.COMPUTE)
        communicate_col_index = safe_index_value(headers, SlowRankAnalyzer.COMMUNICATION)
        rank_id_index = safe_index_value(headers, "rank_id")
        step_index = safe_index_value(headers, "step")
        if rank_id_index is None:
            return default_step_duration

        # 获取目标rank_id和step的行索引
        if step is None or step_index is None:
            row_index = safe_index_value(
                [tuple_list[rank_id_index] == rank_id for tuple_list in self.format_datas.get("data")],
                True
            )
        else:
            index_match_list = []
            for tuple_list in self.format_datas.get("data"):
                index_match_list.append(tuple_list[rank_id_index] == rank_id and tuple_list[step_index] == step)
            row_index = safe_index_value(
                index_match_list,
                True
            )
        if row_index is None:
            return default_step_duration

        compute_time = safe_index(safe_index(self.format_datas.get("data"), row_index, []), compute_col_index, 0)
        communicate_time = safe_index(safe_index(self.format_datas.get("data"), row_index, []), communicate_col_index,
                                      0)
        free_time = safe_index(safe_index(self.format_datas.get("data"), row_index, []), free_col_index, 0)
        return convert_to_float(compute_time) + convert_to_float(communicate_time) + convert_to_float(free_time)

    def get_priority(self, max_mem_op_dur=None):
        pass
