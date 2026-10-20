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
from abc import abstractmethod

from msprof_analyze.cluster_analyse.cluster_utils.data_transfer_adapter import DataTransferAdapter
from msprof_analyze.prof_common.constant import Constant
from msprof_analyze.prof_common.file_manager import FileManager
from msprof_analyze.prof_common.logger import get_logger

logger = get_logger()


class BaseAnalysis:
    SAVED_JSON = ""

    def __init__(self, param: dict):
        self.collection_path = param.get(Constant.COLLECTION_PATH)
        self.cluster_analysis_output_path = param.get(Constant.CLUSTER_ANALYSIS_OUTPUT_PATH)
        self.data_map = param.get(Constant.DATA_MAP)
        self.data_type = param.get(Constant.DATA_TYPE)
        self.prof_type = param.get(Constant.PROFILING_TYPE)
        self.communication_ops = []
        self.p2p_group_dict = param.get(Constant.COMM_DATA_DICT, {}).get(Constant.P2P_GROUP)
        self.collective_group_dict = param.get(Constant.COMM_DATA_DICT, {}).get(Constant.COLLECTIVE_GROUP)
        self.comm_ops_struct = {}
        self.adapter = DataTransferAdapter()

    @staticmethod
    def compute_ratio(dividend: float, divisor: float):
        if abs(divisor) < Constant.EPS:
            return 0
        else:
            return round(dividend / divisor, 4)

    @staticmethod
    def check_add_op(op_name: str):
        """
        兼容2个版本，判断是否需要将此算子信息相加
        """
        stat_list = ["middle", "top", "bottom", "total"]
        total = "total"
        for stat_name in stat_list:
            if stat_name in op_name:
                if stat_name != total:
                    return False
        return True

    @abstractmethod
    def run(self):
        pass

    def dump_data(self):
        if not self.comm_ops_struct:
            logger.warning("There is no final comm ops data generated.")
            return
        if self.data_type == Constant.TEXT:
            self.dump_json()
        else:
            self.dump_db()

    @abstractmethod
    def dump_db(self):
        pass

    def compute_total_info(self, communication_ops):
        """compute total info of communication ops, implemented in subclasses"""

    def dump_json(self):
        output_comm_data = {}
        for key in self.comm_ops_struct:
            output_comm_data[str(key)] = self.comm_ops_struct.get(key)
        FileManager.create_json_file(self.cluster_analysis_output_path, output_comm_data, self.SAVED_JSON)

    def split_op_by_group(self):
        for single_op in self.communication_ops:
            if single_op.get(Constant.COMM_OP_TYPE) == Constant.P2P:
                rank_tup = tuple(self.p2p_group_dict.get(single_op.get(Constant.GROUP_NAME), []))
            else:
                rank_tup = tuple(self.collective_group_dict.get(single_op.get(Constant.GROUP_NAME), []))
            rank_id = single_op.get(Constant.RANK_ID, 'N/A')
            step_id = single_op.get(Constant.STEP_ID, 'N/A')
            op_name = single_op.get(Constant.COMM_OP_NAME, 'N/A')
            op_info = single_op.get(Constant.COMM_OP_INFO)
            self.comm_ops_struct.setdefault(rank_tup, {}).setdefault(step_id, {}).setdefault(op_name, {}).setdefault(
                rank_id, op_info
            )

    def combine_ops_total_info(self):
        for _, group_dict in self.comm_ops_struct.items():
            for _, communication_ops in group_dict.items():
                self.compute_total_info(communication_ops)
