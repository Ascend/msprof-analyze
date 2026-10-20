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

import os
from abc import abstractmethod
from collections import defaultdict
from multiprocessing import Pool
import pandas as pd
from msprof_analyze.cluster_analyse.recipes.communication_group_map.communication_group_map import CommunicationGroupMap

from msprof_analyze.cluster_analyse.cluster_utils.data_transfer_adapter import DataTransferAdapter
from msprof_analyze.cluster_analyse.common_func.utils import double_hash
from msprof_analyze.prof_common.constant import Constant
from msprof_analyze.prof_common.logger import get_logger
from msprof_analyze.prof_common.file_manager import FileManager

logger = get_logger()


class BaseCommunicationGroup:
    KEY_PARALLEL_GROUP_INFO = "parallel_group_info"
    KEY_COMM_GROUP_PARALLEL_INFO = "comm_group_parallel_info"

    def __init__(self, params: dict):
        self.collection_path = params.get(Constant.COLLECTION_PATH)
        self.cluster_analysis_output_path = params.get(Constant.CLUSTER_ANALYSIS_OUTPUT_PATH)
        self.data_map = params.get(Constant.DATA_MAP)
        self.data_type = params.get(Constant.DATA_TYPE)
        self.analysis_mode = params.get(Constant.ANALYSIS_MODE)
        self.is_msprof = params.get(Constant.IS_MSPROF)
        self.rank_comm_dir_dict = {}
        self.collective_group_dict = defaultdict(set)
        self.p2p_group_dict = defaultdict(set)
        self.communication_group = {}
        self.parallel_group_info = {}
        self.communication_ops = []
        self.matrix_ops = []
        self.adapter = DataTransferAdapter()
        self.comm_group_parallel_info_df = None

    def load_communication_data(self):
        comm_op_dirs = []
        for rank_id, profiling_dir_path in self.data_map.items():
            if self.data_type == Constant.TEXT:
                output_dir = "analyze" if self.is_msprof else Constant.SINGLE_OUTPUT
                comm_dir = os.path.join(profiling_dir_path, output_dir, Constant.COMM_JSON)
                matrix_dir = os.path.join(profiling_dir_path, output_dir, Constant.COMM_MATRIX_JSON)
            else:
                comm_dir = os.path.join(profiling_dir_path, Constant.SINGLE_OUTPUT, Constant.DB_COMMUNICATION_ANALYZER)
                matrix_dir = comm_dir
            if os.path.exists(comm_dir) or os.path.exists(matrix_dir):
                comm_op_dirs.append((rank_id, comm_dir, matrix_dir))
            else:
                logger.warning("Rank %s does not have valid communication data and communication_matrix data.", rank_id)
        max_processes = int(os.cpu_count() / 2)
        with Pool(processes=max_processes) as p:
            self.rank_comm_dir_dict = p.map(self.read_communication_func, comm_op_dirs)

    def generate_communication_group(self):
        self.communication_group[Constant.COLLECTIVE] = [list(group) for _, group in self.collective_group_dict.items()]
        self.communication_group[Constant.P2P] = [list(group) for _, group in self.p2p_group_dict.items()]

    @abstractmethod
    def read_communication_func(self, params: tuple):
        pass

    def read_parallel_group_info(self):
        for _, profiling_dir_path in self.data_map.items():
            meta_file = os.path.join(profiling_dir_path, Constant.PROFILER_METADATA)
            if not os.path.exists(meta_file):
                continue
            meta_data = FileManager.read_json_file(meta_file)
            if self.KEY_PARALLEL_GROUP_INFO not in meta_data:
                continue
            for group_id, group_info in meta_data[self.KEY_PARALLEL_GROUP_INFO].items():
                if group_id not in self.parallel_group_info:
                    self.parallel_group_info[group_id] = group_info

    def analyze_communication_data(self):
        for rank_id, rank_id_comm_dict, rank_id_matrix_dict in self.rank_comm_dir_dict:
            for step_id, step_id_dict in rank_id_comm_dict.items():
                if not isinstance(step_id_dict, dict):
                    logger.warning("rank%s's communication.json has a wrong data struct.", rank_id)
                    continue
                self.add_collective_group_rank_map(rank_id, step_id_dict.get(Constant.COLLECTIVE, {}))
                self.add_p2p_group_rank_map(rank_id, step_id_dict.get(Constant.P2P, {}))
                for comm_op_type, comm_op_dict in step_id_dict.items():
                    self.add_communication_ops(rank_id, step_id, comm_op_type, comm_op_dict)

            for step_id, step_id_dict in rank_id_matrix_dict.items():
                if not isinstance(step_id_dict, dict):
                    logger.warning("rank%s's communication_matrix.json has a wrong data struct.", rank_id)
                    continue
                self.add_matrix_ops(rank_id, step_id, step_id_dict)
                self.add_collective_group_rank_map(rank_id, step_id_dict.get(Constant.COLLECTIVE, {}))
                self.add_p2p_group_rank_map(rank_id, step_id_dict.get(Constant.P2P, {}))

    @abstractmethod
    def dump_data(self):
        pass

    def collect_comm_data(self):
        comm_data_dict = {
            Constant.P2P_GROUP: self.p2p_group_dict,
            Constant.COLLECTIVE_GROUP: self.collective_group_dict,
            Constant.COMMUNICATION_OPS: self.communication_ops,
            Constant.MATRIX_OPS: self.matrix_ops,
            Constant.COMMUNICATION_GROUP: self.communication_group,
        }
        return comm_data_dict

    def generate(self):
        self.load_communication_data()
        self.analyze_communication_data()
        self.read_parallel_group_info()
        self.generate_communication_group()
        self.analyze_parallel_group_info()
        self.dump_data()
        return self.collect_comm_data()

    def add_collective_group_rank_map(self, rank_id: int, comm_op_dict: dict):
        for comm_op in comm_op_dict:
            if comm_op.startswith('Total'):
                continue
            group_name = comm_op.split('@')[-1]
            self.collective_group_dict[group_name].add(rank_id)

    def add_p2p_group_rank_map(self, rank_id: int, comm_op_dict: dict):
        for comm_op in comm_op_dict:
            if comm_op.startswith('Total'):
                continue
            group_name = comm_op.split('@')[-1]
            self.p2p_group_dict[group_name].add(rank_id)

    def add_communication_ops(self, rank_id: str, step_id: str, comm_op_type: str, comm_op_dict: dict):
        for comm_op in comm_op_dict:
            if comm_op.startswith('Total'):
                continue
            group_name = comm_op.split('@')[-1]
            self.communication_ops.append(
                {
                    Constant.RANK_ID: rank_id,
                    Constant.STEP_ID: step_id,
                    Constant.COMM_OP_TYPE: comm_op_type,
                    Constant.COMM_OP_NAME: comm_op,
                    Constant.GROUP_NAME: group_name,
                    Constant.COMM_OP_INFO: comm_op_dict.get(comm_op),
                }
            )

    def add_matrix_ops(self, rank_id: int, step_id: str, step_id_dict: dict):
        for comm_op_type, comm_dict in step_id_dict.items():
            if comm_op_type not in (Constant.COLLECTIVE, Constant.P2P):
                logger.warning("Unknown communication operators type!")
                continue
            for op_name, op_link_info in comm_dict.items():
                if op_name.startswith('Total'):
                    continue
                group_name = op_name.split('@')[-1]
                self.matrix_ops.append(
                    {
                        Constant.RANK_ID: rank_id,
                        Constant.STEP_ID: step_id,
                        Constant.COMM_OP_TYPE: comm_op_type,
                        Constant.COMM_OP_NAME: op_name,
                        Constant.GROUP_NAME: group_name,
                        Constant.COMM_OP_INFO: op_link_info,
                    }
                )

    def analyze_parallel_group_info(self):
        # create comm group dataframe
        comm_group_cols = ["type", "rank_set", "group_name"]
        comm_group_df = pd.DataFrame(columns=comm_group_cols)
        for group_name, rank_set in self.collective_group_dict.items():
            comm_group_df.loc[comm_group_df.shape[0]] = [Constant.COLLECTIVE, sorted(list(rank_set)), group_name]
        for group_name, rank_set in self.p2p_group_dict.items():
            comm_group_df.loc[comm_group_df.shape[0]] = [Constant.P2P, sorted(list(rank_set)), group_name]

        # create parallel group dataframe
        parallel_group_cols = ["group_name", "group_id", "pg_name", "global_ranks"]
        parallel_group_df = pd.DataFrame(columns=parallel_group_cols)
        for group_id, parallel_info in self.parallel_group_info.items():
            group_name = str(double_hash(group_id))  # group_name is hashed group_id
            pg_name = parallel_info.get("group_name", "")
            global_ranks = sorted(parallel_info.get("global_ranks", []))
            parallel_group_df.loc[parallel_group_df.shape[0]] = [group_name, group_id, pg_name, global_ranks]

        # merge by group_name
        df = pd.merge(comm_group_df, parallel_group_df, on='group_name', how='left')
        df.fillna("", inplace=True)
        if not parallel_group_df.empty:
            df = CommunicationGroupMap.update_rank_set(df)

        df = df.drop(columns=["global_ranks"])
        self.comm_group_parallel_info_df = df
