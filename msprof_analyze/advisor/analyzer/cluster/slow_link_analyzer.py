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

from typing import Dict, List
from msprof_analyze.prof_common.logger import get_logger

from msprof_analyze.advisor.analyzer.base_analyzer import BaseAnalyzer
from msprof_analyze.prof_common.constant import Constant
from msprof_analyze.advisor.result.result import OptimizeResult
from msprof_analyze.advisor.result.item import OptimizeItem, OptimizeRecord
from msprof_analyze.advisor.dataset.cluster.cluster_dataset import ClusterCommunicationDataset
from msprof_analyze.advisor.utils.utils import safe_index_value, convert_to_int
from msprof_analyze.prof_common.additional_args_manager import AdditionalArgsManager

logger = get_logger()


class SlowLinkAnalyzer(BaseAnalyzer):
    RDMA_TIME_MS = "RDMA time(ms)"
    RDMA_SIZE_MB = "RDMA size(mb)"
    SDMA_TIME_MS = "SDMA time(ms)"
    SDMA_SIZE_MB = "SDMA size(mb)"
    RDMA_BANDWIDTH = "RDMA bandwidth(GB/s)"
    SDMA_BANDWIDTH = "SDMA bandwidth(GB/s)"
    COMMUNICATION_BANDWIDTH_INFO = "Communication Bandwidth Info"
    TRANSIT_TIME = "Transit Time(ms)"
    TRANSIT_SIZE = "Transit Size(MB)"
    SDMA = "SDMA"
    RDMA = "RDMA"
    SLOW_LINK_ANALYSIS = "slow link"
    SLOW_LINK_ANALYSIS_CN = "慢链路分析"
    RATIO_THRESHOLD = 0.05
    dataset_cls_list = [ClusterCommunicationDataset]

    def __init__(self, collection_path, n_processes: int = 1, **kwargs):
        super().__init__(collection_path, n_processes, **kwargs)
        key = ClusterCommunicationDataset.get_key()
        self.communication_data_class = self.get_first_data_by_key(self.dataset_list, key)
        self.rank_bw_dict = self.communication_data_class.get_data()
        self.result = OptimizeResult()
        self.bottelneck = ''
        self.suggestion = ''
        self.format_datas = {}
        if self.rank_bw_dict is not None:
            self.format_datas = self.format_details()

    @staticmethod
    def compute_max_gap_ratio(data: list, mean: float):
        if mean == 0:
            return 0
        else:
            return (max(data) - min(data)) / mean

    def optimize(self, **kwargs):
        if self.rank_bw_dict is None:
            logger.error("Slow link analysis failed due to data loading failure. \
                        Please check your cluster_analysis_output folder. \
                        If you are not concerned about this type of data, please ignore this message.")
            return self.result
        self.process()
        self.make_record()
        self.make_render(kwargs.get("template_key"))
        return self.result

    def process(self):
        if self.rank_bw_dict:
            self.produce_bottleneck(self.RDMA_BANDWIDTH)
            self.produce_bottleneck(self.SDMA_BANDWIDTH)

    def produce_bottleneck(self, link_type: str):
        data_list = [rank_dict.get(link_type, 0) for rank_id, rank_dict in self.rank_bw_dict.items()]
        if len(data_list) > 0:
            avg_bw = round(sum(data_list) / len(data_list), 3)
        else:
            logger.info("The slow link (identified bottleneck) cannot provide a bottleneck \
                           because the analysis data is missing bandwidth information.")
            return
        language = AdditionalArgsManager().language
        if language == "en":
            self.bottelneck += f'{link_type}: \n' \
                               f'    The average is {avg_bw}, \n' \
                               f'    while the maximum  is {round(max(data_list), 3)}GB/s \n' \
                               f'    and the minimum is {round(min(data_list), 3)}GB/s. \n' \
                               f'    the difference is {round(max(data_list) - min(data_list), 3)}GB/s. \n'
        else:
            self.bottelneck += f'{link_type}： \n' \
                               f'    平均值是 {avg_bw}， \n' \
                               f'    但最大值是 {round(max(data_list), 3)}GB/s ，\n' \
                               f'    最小值是 {round(min(data_list), 3)}GB/s。\n' \
                               f'    差距为 {round(max(data_list) - min(data_list), 3)}GB/s。 \n'

    def format_details(self):
        if not self.rank_bw_dict:
            return {
                "headers": [],
                "data": []
            }

        details_dict = {}
        headers = list({k for rank_bw_value in self.rank_bw_dict.values() for k in rank_bw_value.keys()})
        headers.sort()

        data_list = []
        for step_rank, rank_bw in self.rank_bw_dict.items():
            step_rank_list = list(map(convert_to_int, step_rank.split(Constant.STEP_RANK_SEP)))
            value_list = [rank_bw.get(i, 0) for i in headers]
            data_list.append(step_rank_list + value_list)
        data_list.sort(key=lambda x: (x[0], x[1]))  # 按rank_id排序

        details_dict["headers"] = ["step", "rank_id"] + headers
        details_dict["data"] = data_list

        return details_dict

    def make_record(self):
        """
        make record for what and how to optimize
        """
        title = self.SLOW_LINK_ANALYSIS_CN
        if AdditionalArgsManager().language == "en":
            title = self.SLOW_LINK_ANALYSIS
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

    def make_render(self, template_key="cluster"):
        result_for_html = {
            "Description": self.bottelneck,
            "suggestion": self.suggestion,
            "details": [self.format_datas]
        }

        self.html_render.render_template(key=template_key,
                                         title=SlowLinkAnalyzer.SLOW_LINK_ANALYSIS,
                                         template_dir="templates",
                                         template_name="cluster_analysis.html",
                                         cann_version=self.cann_version,
                                         profiling_type=self.profiling_type,
                                         profiling_version=self.profiling_version,
                                         result=result_for_html)

    def get_global_step_rank(self, bindwidth_type):
        global_step_rank = {}
        if not self.format_datas:
            return global_step_rank

        bindwidth_key_map = {self.RDMA: self.RDMA_BANDWIDTH, self.SDMA: self.SDMA_BANDWIDTH}

        if bindwidth_type not in bindwidth_key_map:
            raise RuntimeError(f"Error bindwidth type {bindwidth_type}, optionals are {bindwidth_key_map.keys()}")

        headers = self.format_datas.get("headers")

        bindwidth_index = safe_index_value(headers, bindwidth_key_map.get(bindwidth_type))

        if bindwidth_index is not None:
            data_list = [tuple_list[bindwidth_index] for tuple_list in self.format_datas.get("data", [])]
            if not data_list:
                return global_step_rank
            max_bandwidth, min_bandwidth = max(data_list), min(data_list)

            if self.compute_max_gap_ratio(data_list, sum(data_list) / len(
                    data_list)) < self.RATIO_THRESHOLD:
                return global_step_rank

            max_bandwidth_index = data_list.index(max_bandwidth)
            min_bandwidth_index = data_list.index(min_bandwidth)

            rank_id_index = safe_index_value(headers, "rank_id")
            step_index = safe_index_value(headers, "step")

            if rank_id_index is None:
                return global_step_rank

            max_bandwidth_rank_id = self.format_datas.get("data")[max_bandwidth_index][rank_id_index]
            min_bandwidth_rank_id = self.format_datas.get("data")[min_bandwidth_index][rank_id_index]

            if step_index is None:
                max_bandwidth_step, min_bandwidth_step = Constant.DEFAULT_STEP, Constant.DEFAULT_STEP
            else:
                max_bandwidth_step = self.format_datas.get("data")[max_bandwidth_index][step_index]
                min_bandwidth_step = self.format_datas.get("data")[min_bandwidth_index][step_index]

            global_step_rank["maximum"] = {"rank_id": max_bandwidth_rank_id, "step": max_bandwidth_step}
            global_step_rank["minimum"] = {"rank_id": min_bandwidth_rank_id, "step": min_bandwidth_step}

        return global_step_rank

    def get_priority(self, max_mem_op_dur=None):
        pass
