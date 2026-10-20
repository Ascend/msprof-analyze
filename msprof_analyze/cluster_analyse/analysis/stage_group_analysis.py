# -------------------------------------------------------------------------
# This file is part of the MindStudio project.
# Copyright (c) 2025 Huawei Technologies Co.,Ltd.
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
from copy import deepcopy

import pandas as pd

from msprof_analyze.cluster_analyse.common_func.table_constant import TableConstant
from msprof_analyze.cluster_analyse.common_func.utils import UnionFind
from msprof_analyze.prof_common.logger import get_logger
from msprof_analyze.prof_common.constant import Constant
from msprof_analyze.prof_common.database_service import DatabaseService
from msprof_analyze.prof_common.file_manager import FileManager

logger = get_logger()


class StageInfoAnalysis:
    def __init__(self, param: dict):
        self.cluster_analysis_output_path = param.get(Constant.CLUSTER_ANALYSIS_OUTPUT_PATH, "")
        self.cluster_analysis_output_dir = os.path.join(
            self.cluster_analysis_output_path, Constant.CLUSTER_ANALYSIS_OUTPUT
        )
        self.data_type = param.get(Constant.DATA_TYPE)
        self.communication_data_dict = param.get(Constant.COMM_DATA_DICT, {})
        self.collective_group_dict = {}
        self.p2p_link = []
        self.p2p_union_group = []
        self.stage_group = []

    def run(self):
        if not self.prepare_data():
            return []
        self.generate_p2p_union_group()
        self.generate_stage_group()
        return self.stage_group

    def prepare_data(self):
        if Constant.KEY_COMM_GROUP_PARALLEL_INFO in self.communication_data_dict:
            comm_group_df = pd.DataFrame(self.communication_data_dict.get(Constant.KEY_COMM_GROUP_PARALLEL_INFO))
        else:
            comm_group_df = self.load_communication_group_df()
        return self.extract_infos(comm_group_df)

    def load_communication_group_df(self):
        if not os.path.exists(self.cluster_analysis_output_path):
            logger.warning("StageInfoAnalysis: %s not exist!", self.cluster_analysis_output_path)
            return None
        return (
            self.load_communication_group_df_for_text()
            if self.data_type == Constant.TEXT
            else (self.load_communication_group_df_for_db())
        )

    def load_communication_group_df_for_text(self):
        # check file exist
        communication_group_json = os.path.join(self.cluster_analysis_output_dir, Constant.COMMUNICATION_GROUP_JSON)
        if not os.path.exists(communication_group_json):
            logger.warning("%s not exists!", communication_group_json)
            return None
        # read comm_group_parallel_info from communication_group.json
        group_data = FileManager.read_json_file(communication_group_json)
        if Constant.KEY_COMM_GROUP_PARALLEL_INFO not in group_data or not group_data.get(
            Constant.KEY_COMM_GROUP_PARALLEL_INFO
        ):
            logger.warning("%s not in %s", Constant.KEY_COMM_GROUP_PARALLEL_INFO, Constant.COMMUNICATION_GROUP_JSON)
            return None
        # convert to dataframe
        comm_group_df = pd.DataFrame(group_data.get(Constant.KEY_COMM_GROUP_PARALLEL_INFO))
        expected_columns = [
            TableConstant.TYPE,
            TableConstant.RANK_SET,
            TableConstant.GROUP_NAME,
            TableConstant.GROUP_ID,
            TableConstant.PG_NAME,
        ]
        if list(comm_group_df.columns) != expected_columns:
            logger.error("%s has unexpected columns: %s", Constant.COMMUNICATION_GROUP_JSON, comm_group_df.columns)
            return None
        comm_group_df[TableConstant.RANK_SET] = comm_group_df[TableConstant.RANK_SET].apply(set)
        return comm_group_df

    def load_communication_group_df_for_db(self):
        # load data from cluster_analysis.db
        if not os.path.exists(self.cluster_analysis_output_dir):
            logger.warning(
                "db path %s does not exist.",
                self.cluster_analysis_output_path,
            )
        cluster_analysis_db = os.path.join(self.cluster_analysis_output_dir, Constant.DB_CLUSTER_COMMUNICATION_ANALYZER)
        data_service = DatabaseService(cluster_analysis_db, {})
        table_communication_group = Constant.TABLE_COMMUNICATION_GROUP_MAPPING
        data_service.add_table_for_query(table_communication_group)
        data_dict = data_service.query_data()
        comm_group_df = data_dict.get(table_communication_group, None)
        if comm_group_df is None or comm_group_df.empty:
            logger.error("There is no %s data in %s.", table_communication_group, cluster_analysis_db)
            return None
        expected_columns = [
            TableConstant.TYPE,
            TableConstant.RANK_SET,
            TableConstant.GROUP_NAME,
            TableConstant.GROUP_ID,
            TableConstant.PG_NAME,
        ]
        if list(comm_group_df.columns) != expected_columns:
            logger.error("%s has unexpected columns: %s", Constant.COMMUNICATION_GROUP_JSON, comm_group_df.columns)
            return None
        # process rank_set
        try:
            comm_group_df[TableConstant.RANK_SET] = comm_group_df[TableConstant.RANK_SET].apply(
                lambda s: set(map(int, s.strip('()').split(',')))
            )
        except Exception as e:
            logger.error("Process rank_set for communication group map with error: %s", e)
            return None
        return comm_group_df

    def extract_infos(self, comm_group_df):
        if comm_group_df is None:
            return False
        self.collective_group_dict = (
            comm_group_df[comm_group_df[TableConstant.TYPE] == Constant.COLLECTIVE]
            .set_index(TableConstant.GROUP_NAME)[TableConstant.RANK_SET]
            .to_dict()
        )
        pp_df = comm_group_df[comm_group_df[TableConstant.TYPE] == Constant.P2P]
        pp_df = pp_df[pp_df[TableConstant.PG_NAME].str.lower().str.startswith('pp', na=False)]
        self.p2p_link = pp_df[TableConstant.RANK_SET].to_list()
        return len(self.p2p_link) > 0

    def generate_p2p_union_group(self):
        self.p2p_link.sort(key=min)
        while self.p2p_link:
            union_set = deepcopy(self.p2p_link[0])
            rm_list = [self.p2p_link[0]]
            for link_rank_set_x in self.p2p_link[1:]:
                if UnionFind.is_connected(link_rank_set_x, union_set):
                    union_set = union_set.union(link_rank_set_x)
                    rm_list.append(link_rank_set_x)
            self.p2p_union_group.append(union_set)
            self.p2p_link = [element for element in self.p2p_link if element not in rm_list]

    def generate_stage_group(self):
        stage_group = {}
        for _, rank_set in self.collective_group_dict.items():
            if not self.whether_valid_comm_group(rank_set):
                continue
            unioned_set = set()
            remove_key = []
            for first_rank, stage in stage_group.items():
                if UnionFind.is_connected(rank_set, stage):
                    unioned_set = UnionFind.union(rank_set, stage, unioned_set)
                    remove_key.append(first_rank)
            if unioned_set:
                for key in remove_key:
                    del stage_group[key]
                stage_group[min(unioned_set)] = unioned_set
            else:
                stage_group[min(rank_set)] = rank_set
        first_rank_sort_list = sorted(first_rank for first_rank in stage_group)
        self.stage_group = [list(stage_group.get(first_rank, {})) for first_rank in first_rank_sort_list]

    def whether_valid_comm_group(self, rank_set: set):
        """
        while distinguish which communication group should be used to infer stage info, these group should be ignored:
            1. group can not include more than 1 rank in every single p2p group
        """
        for p2p_rank_set in self.p2p_union_group:
            if len(rank_set.intersection(p2p_rank_set)) > 1:
                return False
        return True
