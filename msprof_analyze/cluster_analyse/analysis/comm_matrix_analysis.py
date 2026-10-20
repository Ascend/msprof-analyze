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
from collections import defaultdict

from msprof_analyze.cluster_analyse.analysis.base_analysis import BaseAnalysis
from msprof_analyze.cluster_analyse.common_func.utils import increase_shared_value
from msprof_analyze.prof_common.constant import Constant
from msprof_analyze.prof_common.logger import get_logger
from msprof_analyze.cluster_analyse.common_func.utils import double_hash
from msprof_analyze.prof_common.file_manager import FileManager

logger = get_logger()


class CommMatrixAnalysis(BaseAnalysis):
    SAVED_JSON = "cluster_communication_matrix.json"

    def __init__(self, param: dict):
        super().__init__(param)
        self.communication_ops = param.get(Constant.COMM_DATA_DICT, {}).get(Constant.MATRIX_OPS)

    @staticmethod
    def combine_link(link_info_dict: dict, single_link_dict: dict):
        link_info_dict[Constant.TRANSPORT_TYPE] = single_link_dict.get(Constant.TRANSPORT_TYPE)
        link_info_dict[Constant.OP_NAME] = single_link_dict.get(Constant.OP_NAME, '')
        link_info_dict[Constant.TRANSIT_TIME_MS] += single_link_dict.get(Constant.TRANSIT_TIME_MS, 0)
        link_info_dict[Constant.TRANSIT_SIZE_MB] += single_link_dict.get(Constant.TRANSIT_SIZE_MB, 0)

    def run(self, completed_processes, lock):  # pylint: disable=arguments-differ
        if not self.communication_ops:
            increase_shared_value(completed_processes, lock)
            logger.info("CommMatrixAnalysis completed")
            return
        self.split_op_by_group()
        self.combine_ops_total_info()
        self.dump_data()
        increase_shared_value(completed_processes, lock)
        logger.info("CommMatrixAnalysis completed")

    def dump_db(self):
        raise RuntimeError("CommMatrixAnalysis only supports text-mode output.")

    def compute_total_info(self, communication_ops: dict):
        self.merge_same_links(communication_ops)
        self.combine_link_info(communication_ops)

    def merge_same_links(self, step_dict: dict):
        def update_rank_map(step_dict):
            for op_name, op_dict in step_dict.items():
                group_name = op_name.split("@")[-1]
                for rank_id, rank_dict in op_dict.items():
                    for link_key in rank_dict:
                        if '-' not in link_key:
                            logger.warning("%s has an invalid link key %s!", str(op_name), str(link_key))
                            break
                        src_rank = link_key.split('-')[0]
                        dst_rank = link_key.split('-')[1]
                        if src_rank == dst_rank:
                            if src_rank not in project_local_global_rank_map.get(group_name, {}):
                                project_local_global_rank_map.setdefault(group_name, {})[src_rank] = rank_id
                            elif project_local_global_rank_map.get(group_name, {}).get(src_rank) != rank_id:
                                logger.warning(
                                    "In the same communication group %s, global rank %s and %s "
                                    "get the same local rank %s!",
                                    group_name,
                                    rank_id,
                                    project_local_global_rank_map.get(group_name, {}).get(src_rank),
                                    src_rank,
                                )

        def process_link_key(rank_dict):
            for link_key in rank_dict:
                if '-' not in link_key:
                    logger.warning("%s has an invalid link key %s!", str(op_name), str(link_key))
                    break
                self.combine_link(link_info[link_key], rank_dict[link_key])

        def convert_local_to_global_rank(rank_map):
            tmp_link = {}
            for link_key, link_dict in link_info.items():
                src_rank = link_key.split('-')[0]
                dst_rank = link_key.split('-')[1]
                if src_rank not in rank_map:
                    logger.warning(
                        "The src local rank %s of the operator %s cannot be mapped to the global rank.",
                        src_rank,
                        op_name,
                    )
                    continue
                if dst_rank not in rank_map:
                    logger.warning(
                        "The dst local rank %s of the operator %s cannot be mapped to the global rank.",
                        dst_rank,
                        op_name,
                    )
                    continue
                src_rank = rank_map[src_rank]
                dst_rank = rank_map[dst_rank]
                link_dict[Constant.BANDWIDTH_GB_S] = self.compute_ratio(
                    link_dict.get(Constant.TRANSIT_SIZE_MB, 0), link_dict.get(Constant.TRANSIT_TIME_MS, 0)
                )
                tmp_link[f"{src_rank}-{dst_rank}"] = link_dict
            return tmp_link

        default_value = {
            Constant.TRANSPORT_TYPE: '',
            Constant.TRANSIT_TIME_MS: 0,
            Constant.TRANSIT_SIZE_MB: 0,
            Constant.OP_NAME: '',
        }
        project_local_global_rank_map = self.get_parallel_group_info()
        update_rank_map(step_dict)
        for op_name, op_dict in step_dict.items():
            link_info = defaultdict(lambda: copy.deepcopy(default_value))
            group_name = op_name.split("@")[-1]
            for rank_dict in op_dict.values():
                process_link_key(rank_dict)
            step_dict[op_name] = convert_local_to_global_rank(project_local_global_rank_map.get(group_name, {}))

    def combine_link_info(self, step_dict: dict):
        default_value = {
            Constant.TRANSPORT_TYPE: '',
            Constant.TRANSIT_TIME_MS: 0,
            Constant.TRANSIT_SIZE_MB: 0,
            Constant.OP_NAME: '',
        }
        total_op_info = defaultdict(lambda: copy.deepcopy(default_value))
        total_group_op_info = defaultdict(lambda: copy.deepcopy(total_op_info))
        for op_name, op_dict in step_dict.items():
            group_name = op_name.split("@")[-1]
            if self.check_add_op(op_name):
                for link_key, link_dict in op_dict.items():
                    self.combine_link(total_group_op_info[group_name][link_key], link_dict)
        for group_name, total_op_info in total_group_op_info.items():
            for _, link_dict in total_op_info.items():
                link_dict[Constant.BANDWIDTH_GB_S] = self.compute_ratio(
                    link_dict.get(Constant.TRANSIT_SIZE_MB, 0), link_dict.get(Constant.TRANSIT_TIME_MS, 0)
                )
            step_dict[f"{Constant.TOTAL_OP_INFO}@{group_name}"] = total_op_info

    def get_parallel_group_info(self):
        parallel_group_info = {}
        for profiler_path in self.data_map.values():
            meta_json = os.path.join(profiler_path, "profiler_metadata.json")
            if os.path.exists(meta_json):
                meta_data = FileManager.read_json_file(meta_json)
                for group_name, group_info in meta_data.get("parallel_group_info", {}).items():
                    global_ranks = group_info.get("global_ranks")
                    if isinstance(global_ranks, list) and global_ranks:
                        global_ranks.sort()
                        parallel_group_info[double_hash(group_name)] = dict(enumerate(global_ranks))
        return parallel_group_info
