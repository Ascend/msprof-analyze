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
from collections import defaultdict

from msprof_analyze.cluster_analyse.analysis.base_analysis import BaseAnalysis
from msprof_analyze.cluster_analyse.common_func.utils import increase_shared_value
from msprof_analyze.prof_common.constant import Constant
from msprof_analyze.prof_common.logger import get_logger

logger = get_logger()


class CommunicationAnalysis(BaseAnalysis):
    SAVED_JSON = "cluster_communication.json"

    def __init__(self, param: dict):
        super().__init__(param)
        self.communication_ops = param.get(Constant.COMM_DATA_DICT, {}).get(Constant.COMMUNICATION_OPS)

    @staticmethod
    def combine_size_distribution(op_dict: dict, total_dict: dict):
        for size, size_info in op_dict.items():
            total_dict[size][0] += size_info[0]
            total_dict[size][1] += size_info[1]

    def run(self, completed_processes, lock):  # pylint: disable=arguments-differ
        if not self.communication_ops:
            increase_shared_value(completed_processes, lock)
            logger.info("CommunicationAnalysis completed")
            return
        self.split_op_by_group()
        self.combine_ops_total_info()
        self.dump_data()
        increase_shared_value(completed_processes, lock)
        logger.info("CommunicationAnalysis completed")

    def dump_db(self):
        raise RuntimeError("CommunicationAnalysis only supports text-mode output.")

    def compute_total_info(self, communication_ops: dict):
        if not communication_ops:
            return
        default_value = {
            Constant.COMMUNICATION_TIME_INFO: defaultdict(float),
            Constant.COMMUNICATION_BANDWIDTH_INFO: {},
        }
        total_rank_dict = defaultdict(lambda: copy.deepcopy(default_value))
        total_group_rank_dict = defaultdict(lambda: copy.deepcopy(total_rank_dict))
        for op_name, rank_dict in communication_ops.items():
            group_name = op_name.split("@")[-1]
            for rank_id, communication_op_info in rank_dict.items():
                for com_info, com_info_dict in communication_op_info.items():
                    if com_info == Constant.COMMUNICATION_TIME_INFO:
                        self.combine_time_info(com_info_dict, total_group_rank_dict[group_name][rank_id][com_info])
                    if com_info == Constant.COMMUNICATION_BANDWIDTH_INFO:
                        self.combine_bandwidth_info(com_info_dict, total_group_rank_dict[group_name][rank_id][com_info])
        for group_name, total_rank_dict in total_group_rank_dict.items():
            for rank_id in total_rank_dict:
                self.compute_time_ratio(total_rank_dict[rank_id][Constant.COMMUNICATION_TIME_INFO])
                self.compute_bandwidth_ratio(total_rank_dict[rank_id][Constant.COMMUNICATION_BANDWIDTH_INFO])
            communication_ops[f"{Constant.TOTAL_OP_INFO}@{group_name}"] = total_rank_dict

    def combine_time_info(self, com_info_dict: dict, total_time_info_dict: dict):
        ratio_list = [Constant.WAIT_TIME_RATIO, Constant.SYNCHRONIZATION_TIME_RATIO]
        for time_info in com_info_dict:
            if time_info not in ratio_list and time_info != Constant.START_TIMESTAMP:
                total_time_info_dict[time_info] += com_info_dict.get(time_info)

    def combine_bandwidth_info(self, com_info_dict: dict, total_bandwidth_info_dict: dict):
        add_list = [Constant.TRANSIT_TIME_MS, Constant.TRANSIT_SIZE_MB]
        dict_list = [Constant.SIZE_DISTRIBUTION]
        for transport_type, part_transport_dict in com_info_dict.items():
            if transport_type not in total_bandwidth_info_dict:
                total_bandwidth_info_dict[transport_type] = {
                    Constant.TRANSIT_TIME_MS: 0,
                    Constant.TRANSIT_SIZE_MB: 0,
                    Constant.SIZE_DISTRIBUTION: defaultdict(lambda: [0, 0]),
                }
            for bandwidth_msg, value in part_transport_dict.items():
                if bandwidth_msg in add_list:
                    total_bandwidth_info_dict[transport_type][bandwidth_msg] += value
                if bandwidth_msg in dict_list:
                    self.combine_size_distribution(value, total_bandwidth_info_dict[transport_type].get(bandwidth_msg))

    def compute_time_ratio(self, total_time_info_dict: dict):
        total_time_info_dict[Constant.WAIT_TIME_RATIO] = self.compute_ratio(
            total_time_info_dict.get(Constant.WAIT_TIME_MS, 0),
            total_time_info_dict.get(Constant.WAIT_TIME_MS, 0) + total_time_info_dict.get(Constant.TRANSIT_TIME_MS, 0),
        )
        total_time_info_dict[Constant.SYNCHRONIZATION_TIME_RATIO] = self.compute_ratio(
            total_time_info_dict.get(Constant.SYNCHRONIZATION_TIME_MS, 0),
            total_time_info_dict.get(Constant.SYNCHRONIZATION_TIME_MS, 0)
            + total_time_info_dict.get(Constant.TRANSIT_TIME_MS, 0),
        )

    def compute_bandwidth_ratio(self, total_bandwidth_info_dict: dict):
        for _, bandwidth_dict in total_bandwidth_info_dict.items():
            bandwidth_dict[Constant.BANDWIDTH_GB_S] = self.compute_ratio(
                bandwidth_dict.get(Constant.TRANSIT_SIZE_MB, 0), bandwidth_dict.get(Constant.TRANSIT_TIME_MS, 0)
            )
