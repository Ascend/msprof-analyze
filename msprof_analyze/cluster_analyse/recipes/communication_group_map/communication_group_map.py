# Copyright (c) 2025, Huawei Technologies Co., Ltd.
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
import json
import os
import pandas as pd

from msprof_analyze.cluster_analyse.common_func.utils import double_hash
from msprof_analyze.cluster_analyse.common_func.table_constant import TableConstant
from msprof_analyze.cluster_analyse.recipes.base_recipe_analysis import BaseRecipeAnalysis
from msprof_analyze.prof_common.constant import Constant
from msprof_analyze.prof_common.logger import get_logger
from msprof_analyze.prof_common.database_service import DatabaseService

logger = get_logger()


class CommunicationGroupMap(BaseRecipeAnalysis):
    GLOBAL_RANKS = "global_ranks"
    COMMUNICATION_GROUP_MAPPING_TABLE = "CommunicationGroupMapping"

    def __init__(self, params):
        super().__init__(params)
        logger.info("CommunicationGroupMap init.")
        self.group_df = None

    @property
    def base_dir(self):
        return os.path.basename(os.path.dirname(__file__))

    @staticmethod
    def get_comm_type_from_op_name(op_name: str):
        op_name_lower = op_name.lower()
        return Constant.P2P if ("send" in op_name_lower or "receive" in op_name_lower or "recv" in op_name_lower) \
               else Constant.COLLECTIVE

    @staticmethod
    def update_rank_set(group_df):
        """更新rank_set，优先使用global_ranks"""
        rank_set_col = TableConstant.RANK_SET
        global_ranks_col = CommunicationGroupMap.GLOBAL_RANKS
        if rank_set_col not in group_df.columns or global_ranks_col not in group_df.columns:
            logger.warning(f"Skip update rank_set, since {rank_set_col} or {global_ranks_col} column not in group_df.")
            return group_df

        mask = (group_df[global_ranks_col].notna() &
                (group_df[global_ranks_col].astype(str) != "") &
                (group_df[global_ranks_col].astype(str) != "[]") &
                (group_df[global_ranks_col] != group_df[rank_set_col]))

        updated_df = group_df.copy()
        updated_df.loc[mask, rank_set_col] = updated_df.loc[mask, global_ranks_col]
        return updated_df

    def run(self, context):
        mapper_res = self.mapper_func(context)
        self.reducer_func(mapper_res)
        if self._export_type == Constant.DB:
            self.save_db()
        elif self._export_type == Constant.TEXT:
            logger.info("Reset export_type to db")
            self.save_db()  # It may be invoked by other recipe, so it must be set to 'db' here.
        else:
            logger.error(f"CommGroupMap: {self._export_type} is not supported for export type.")

    def generate_communication_group_mapping(self, context):
        mapper_res = self.mapper_func(context)
        self.reducer_func(mapper_res)
        return self.group_df

    def reducer_func(self, mapper_res):
        # concat and process all comm group
        comm_group_df_list = [df for df, _ in mapper_res]
        comm_group_combined_df = pd.concat(comm_group_df_list).drop_duplicates()
        if comm_group_combined_df.empty:
            return
        comm_group_combined_df = (comm_group_combined_df.groupby([TableConstant.TYPE, TableConstant.GROUP_NAME])
                                  [TableConstant.RANK_ID].apply(lambda x: sorted(set(x))).reset_index())
        comm_group_combined_df[TableConstant.RANK_SET] = (
            comm_group_combined_df[TableConstant.RANK_ID].
            apply(lambda x: "(" + ",".join(str(i) for i in sorted(x)) + ")"))

        comm_group_combined_df = comm_group_combined_df.drop(columns=[TableConstant.RANK_ID])
        # concat all parallel group info
        parallel_info_df_list = [df for _, df in mapper_res]
        parallel_info_combined_df = pd.concat(parallel_info_df_list).drop_duplicates()
        # merge by group_name
        group_df = pd.merge(comm_group_combined_df, parallel_info_combined_df, on=TableConstant.GROUP_NAME, how="left")
        group_df.fillna("", inplace=True)
        # update rank_set, use global_ranks or rank_set
        if not parallel_info_combined_df.empty:
            group_df = self.update_rank_set(group_df)
        # column order
        column_order = [TableConstant.TYPE, TableConstant.RANK_SET, TableConstant.GROUP_NAME,
                        TableConstant.GROUP_ID, TableConstant.PG_NAME]
        self.group_df = group_df[column_order]

    def save_db(self):
        self.dump_data(self.group_df, Constant.DB_CLUSTER_COMMUNICATION_ANALYZER,
                       self.COMMUNICATION_GROUP_MAPPING_TABLE, index=False)

    def _mapper_func(self, data_map, analysis_class):
        rank_id = data_map.get(Constant.RANK_ID)
        # read CommAnalyzerTime table
        analysis_db_path = data_map.get(Constant.ANALYSIS_DB_PATH)
        analysis_data_service = DatabaseService(analysis_db_path, {})
        analysis_data_service.add_table_for_query(Constant.TABLE_COMM_ANALYZER_TIME,
                                                  [TableConstant.HCCL_OP_NAME, TableConstant.GROUP_NAME])
        comm_time_res = analysis_data_service.query_data()
        comm_time_df = comm_time_res.get(Constant.TABLE_COMM_ANALYZER_TIME)
        if comm_time_df is None or comm_time_df.empty:
            return pd.DataFrame(), pd.DataFrame()
        # process comm_time_df: group_name, type, rank_id
        comm_time_df[TableConstant.RANK_ID] = rank_id
        comm_time_df[TableConstant.TYPE] = (comm_time_df[TableConstant.HCCL_OP_NAME].
                                            apply(lambda x: self.get_comm_type_from_op_name(x)))
        comm_time_df = comm_time_df.drop(columns=[TableConstant.HCCL_OP_NAME])
        comm_time_df = comm_time_df.drop_duplicates()

        # read META_DATA table
        profiler_db_path = data_map.get(Constant.PROFILER_DB_PATH)
        profiler_data_service = DatabaseService(profiler_db_path, {})
        profiler_data_service.add_table_for_query(Constant.TABLE_META_DATA,
                                                  [TableConstant.NAME, TableConstant.VALUE])
        meta_data_res = profiler_data_service.query_data()
        meta_data_df = meta_data_res.get(Constant.TABLE_META_DATA)
        # process parallel_info_df
        parallel_info_df = pd.DataFrame(columns=[TableConstant.GROUP_NAME, TableConstant.GROUP_ID,
                                                 TableConstant.PG_NAME, self.GLOBAL_RANKS])
        if (meta_data_df is None or meta_data_df.empty or
                Constant.PARALLEL_GROUP_INFO not in meta_data_df[TableConstant.NAME].values):
            return comm_time_df, parallel_info_df
        info_str = meta_data_df.loc[meta_data_df[TableConstant.NAME] == Constant.PARALLEL_GROUP_INFO,
                                    TableConstant.VALUE].values[0]
        info_dict = json.loads(info_str)
        for group_id, parallel_info in info_dict.items():
            group_name = str(double_hash(group_id))  # group_name is hashed group_id
            pg_name = parallel_info.get(TableConstant.GROUP_NAME, "")
            global_ranks = sorted(parallel_info.get(self.GLOBAL_RANKS, []))
            parallel_info_df.loc[parallel_info_df.shape[0]] = [group_name, group_id, pg_name,
                                                               "(" + ",".join(str(i) for i in global_ranks) + ")"]

        return comm_time_df, parallel_info_df
