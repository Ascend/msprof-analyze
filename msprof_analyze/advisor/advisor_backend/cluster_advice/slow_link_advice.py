# -------------------------------------------------------------------------
# This file is part of the MindStudio project.
# Copyright (c) 2023 Huawei Technologies Co.,Ltd.
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
from collections import defaultdict
from msprof_analyze.advisor.advisor_backend.common_func_advisor.constant import Constant
from msprof_analyze.advisor.advisor_backend.cluster_advice.cluster_advice_base import ClusterAdviceBase
from msprof_analyze.prof_common.file_manager import FileManager


class SlowLinkAdvice(ClusterAdviceBase):
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

    def __init__(self, collection_path: str, kwargs: dict = None):
        super().__init__(collection_path)
        default_value = {
            self.RDMA_TIME_MS: 0,
            self.RDMA_SIZE_MB: 0,
            self.SDMA_TIME_MS: 0,
            self.SDMA_SIZE_MB: 0,
        }
        self.rank_bw_dict = defaultdict(lambda: copy.deepcopy(default_value))

    @staticmethod
    def compute_ratio(dividend: float, divisor: float):
        if abs(divisor) < 1e-15:
            return 0
        else:
            return round(dividend / divisor, 4)

    def load_communication_json(self):
        json_path = os.path.join(self.collection_path, Constant.CLUSTER_ANALYSIS_OUTPUT, Constant.CLUSTER_COMM_JSON)
        if not os.path.exists(json_path):
            msg = "[ERROR] cluster_communication.json doesn't exist, terminate analysis."
            raise RuntimeError(msg)
        communication_json = FileManager.read_json_file(json_path)
        return communication_json

    def run(self):
        self.path_check()
        communication_json = self.load_communication_json()
        self.process(communication_json)
        self.output()
        return self.output_format_data

    def process(self, communication_json: dict):
        for _, group_dict in communication_json.items():
            for _, step_dict in group_dict.items():
                for _, op_dict in step_dict.items():
                    self.compute_bandwidth(op_dict)
        if self.rank_bw_dict:
            self.produce_bottleneck(self.RDMA_BANDWIDTH)
            self.produce_bottleneck(self.SDMA_BANDWIDTH)

    def compute_bandwidth(self, op_dict: dict):
        for rank_id, rank_dict in op_dict.items():
            try:
                rank = int(rank_id)
            except ValueError as e:
                msg = "[ERROR] Cluster_communication.json has invalid structure."
                raise ValueError(msg) from e
            for comm_type, bw_dict in rank_dict.get(self.COMMUNICATION_BANDWIDTH_INFO, {}).items():
                if comm_type == self.SDMA:
                    self.rank_bw_dict[rank][self.SDMA_SIZE_MB] += bw_dict.get(self.TRANSIT_SIZE)
                    self.rank_bw_dict[rank][self.SDMA_TIME_MS] += bw_dict.get(self.TRANSIT_TIME)
                if comm_type == self.RDMA:
                    self.rank_bw_dict[rank][self.RDMA_SIZE_MB] += bw_dict.get(self.TRANSIT_SIZE)
                    self.rank_bw_dict[rank][self.RDMA_TIME_MS] += bw_dict.get(self.TRANSIT_TIME)

        for rank_info in self.rank_bw_dict.values():
            rank_info[self.RDMA_BANDWIDTH] = self.compute_ratio(
                rank_info[self.RDMA_SIZE_MB], rank_info[self.RDMA_TIME_MS]
            )
            rank_info[self.SDMA_BANDWIDTH] = self.compute_ratio(
                rank_info[self.SDMA_SIZE_MB], rank_info[self.SDMA_TIME_MS]
            )

    def produce_bottleneck(self, link_type: str):
        data_list = [rank_dict.get(link_type, 0) for rank_id, rank_dict in self.rank_bw_dict.items()]
        if len(data_list) == 0:
            raise ValueError("Cannot calculate avg_bw, data_list is empty!")
        avg_bw = round(sum(data_list) / len(data_list), 3)
        if avg_bw == 0:
            return
        self.bottelneck += (
            f'{link_type}: \n'
            f'The average is {avg_bw}, '
            f'while the maximum  is {round(max(data_list), 3)}GB/s and '
            f'the minimum is {round(min(data_list), 3)}GB/s. '
            f'the difference is {round(max(data_list) - min(data_list), 3)}GB/s. \n'
        )

    def output(self):
        self.output_format_data[self.DATA] = self.rank_bw_dict
        self.output_format_data[self.BOTTLENECK] = self.bottelneck
