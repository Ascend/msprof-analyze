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
import ast
import os

import pandas as pd
from msprof_analyze.cluster_analyse.recipes.base_recipe_analysis import BaseRecipeAnalysis
from msprof_analyze.prof_common.logger import get_logger
from msprof_analyze.prof_common.constant import Constant
from msprof_analyze.prof_common.database_service import DatabaseService
from msprof_analyze.cluster_analyse.common_func.utils import double_hash

from msprof_analyze.cluster_analyse.common_func.table_constant import TableConstant

logger = get_logger()


class CommMatrixSum(BaseRecipeAnalysis):
    TABLE_CLUSTER_COMM_MATRIX = "ClusterCommunicationMatrix"
    RANK_MAP = "rank_map"
    MATRIX_DATA = "matrix_data"
    RANK_SET = "rank_set"
    P2P_HCOM = ["hcom_send", "hcom_receive", "hcom_batchsendrecv"]

    def __init__(self, params):
        super().__init__(params)
        self.cluster_matrix_df = None
        logger.info("CommMatrixSum init.")

    @property
    def base_dir(self):
        return os.path.basename(os.path.dirname(__file__))

    @classmethod
    def _get_parallel_group_info(cls, profiler_db_path):
        rank_map = {}
        data_service = DatabaseService(profiler_db_path, {})
        data_service.add_table_for_query(TableConstant.TABLE_META_DATA)
        meta_df = data_service.query_data().get(TableConstant.TABLE_META_DATA, None)
        if meta_df is None or meta_df.empty:
            return rank_map
        filtered_df = meta_df[meta_df['name'] == "parallel_group_info"]
        if filtered_df.shape[0] == 1 and filtered_df.shape[1] == 2:
            parallel_group_info = ast.literal_eval(filtered_df['value'].tolist()[0])
            for group_name, group_info in parallel_group_info.items():
                global_ranks = group_info.get("global_ranks")
                if isinstance(global_ranks, list) and global_ranks:
                    global_ranks.sort()
                    rank_map[double_hash(group_name)] = dict(enumerate(global_ranks))
        return rank_map

    @classmethod
    def _trans_msprof_matrix_data(cls, matrix_data):
        matrix_data["step"] = "step"
        matrix_data["type"] = Constant.COLLECTIVE
        for index, row in matrix_data.iterrows():
            lower_op_name = row["hccl_op_name"].lower()
            if any(lower_op_name.startswith(start_str) for start_str in cls.P2P_HCOM):
                matrix_data.at[index, "type"] = Constant.P2P
        matrix_data = matrix_data.rename(columns={'hccl_op_name': 'op_name'})
        matrix_data["hccl_op_name"] = matrix_data["op_name"].str.split("__").str[0]

        # 按多字段分组
        grouped_df = matrix_data.groupby(['type', 'step', 'group_name', 'hccl_op_name', 'src_rank', 'dst_rank'])

        # 定义一个函数，用于提取特定的记录
        def get_specific_rows(group):
            # 按带宽排序
            sorted_group = group.sort_values(by='bandwidth')
            bottom1 = sorted_group.iloc[-1]
            bottom2 = sorted_group.iloc[-2] if len(group) > 1 else pd.Series()
            bottom3 = sorted_group.iloc[-3] if len(group) > 2 else pd.Series()
            top1 = sorted_group.iloc[0]
            mid_index = len(group) // 2
            middle = sorted_group.iloc[mid_index]
            return pd.DataFrame([top1, bottom1, bottom2, bottom3, middle],
                                index=['top1', 'bottom1', 'bottom2', 'bottom3', 'middle']).reset_index()

        example_df = grouped_df.apply(get_specific_rows).reset_index(drop=True)
        example_df = example_df.dropna().reset_index(drop=True)
        example_df["hccl_op_name"] = example_df["hccl_op_name"].astype(str) + "-" + example_df["index"].astype(str)
        example_df = example_df.drop(columns="index")

        # total
        total_df = matrix_data.groupby(['type', 'step', 'group_name', 'hccl_op_name', 'src_rank', 'dst_rank']).agg(
            {'transport_type': 'first', "transit_size": "sum", "transit_time": "sum"})
        total_df = total_df.reset_index()
        total_df["op_name"] = None
        total_df["hccl_op_name"] = total_df["hccl_op_name"].astype(str) + "-total"
        total_df['bandwidth'] = total_df['transit_size'] / total_df['transit_time'].where(total_df['transit_time'] != 0,
                                                                                          other=0)
        return pd.concat([example_df, total_df], ignore_index=True)

    def run(self, context):
        mapper_res = self.mapper_func(context)
        self.reducer_func(mapper_res)

        if self._export_type == Constant.DB:
            self.save_db()
        elif self._export_type == Constant.TEXT:
            self.save_csv()
        else:
            logger.error("communication_matrix_sum is not supported for notebook export type.")

    def reducer_func(self, mapper_res):
        rank_map = self._generate_rank_map(mapper_res)
        concat_df = pd.DataFrame()
        for rank_data in mapper_res:
            matrix_df = rank_data.get(self.MATRIX_DATA)
            concat_df = pd.concat([concat_df, matrix_df], ignore_index=True)
        if concat_df.empty:
            logger.error("Communication matrix data is None.")
            return
        concat_df[self.RANK_SET] = ""
        for index, row in concat_df.iterrows():
            if row["type"] == Constant.P2P:
                concat_df.at[index, self.RANK_SET] = Constant.P2P
                continue
            rank_list = sorted(rank_map.get(row["group_name"], {}).values())
            concat_df.at[index, self.RANK_SET] = ",".join([str(rank) for rank in rank_list])
        grouped_df = concat_df.groupby(
            [self.RANK_SET, 'step', "hccl_op_name", "group_name", "src_rank", "dst_rank"]).agg(
            {'transport_type': 'first', 'op_name': 'first', "transit_size": "sum", "transit_time": "sum"})
        grouped_df = grouped_df.reset_index()
        grouped_df["is_mapped"] = False
        grouped_df["bandwidth"] = None
        for index, row in grouped_df.iterrows():
            src_rank = row["src_rank"]
            dst_rank = row["dst_rank"]
            group_name = row["group_name"]
            group_rank_map = rank_map.get(group_name, {})
            if src_rank not in group_rank_map:
                logger.warning(f"The src local rank {src_rank} of the group_name {group_name} "
                               f"cannot be mapped to the global rank.")
                continue
            if dst_rank not in group_rank_map:
                logger.warning(f"The dst local rank {dst_rank} of the group_name {group_name} "
                               f"cannot be mapped to the global rank.")
                continue
            grouped_df.at[index, 'src_rank'] = group_rank_map[src_rank]
            grouped_df.at[index, 'dst_rank'] = group_rank_map[dst_rank]
            grouped_df.at[index, 'is_mapped'] = True
            grouped_df.at[index, 'bandwidth'] = row["transit_size"] / row["transit_time"] if row["transit_time"] else 0
        filtered_df = grouped_df[grouped_df["is_mapped"]].drop(columns="is_mapped")
        total_op_info = filtered_df[filtered_df['hccl_op_name'].str.contains('total', na=False)].groupby(
            [TableConstant.GROUP_NAME, 'step', "src_rank", "dst_rank"]).agg(
            {'transport_type': 'first', 'op_name': 'first', "transit_size": "sum",
             "transit_time": "sum"}
        )
        total_op_info = total_op_info.reset_index()
        total_op_info["hccl_op_name"] = Constant.TOTAL_OP_INFO
        total_op_info['bandwidth'] = total_op_info['transit_size'] / total_op_info['transit_time'].where(
            total_op_info['transit_time'] != 0, other=0)
        self.cluster_matrix_df = pd.concat([filtered_df, total_op_info], ignore_index=True).drop(columns=self.RANK_SET)

    def save_db(self):
        self.dump_data(self.cluster_matrix_df, Constant.DB_CLUSTER_COMMUNICATION_ANALYZER,
                       self.TABLE_CLUSTER_COMM_MATRIX, index=False)

    def save_csv(self):
        self.dump_data(self.cluster_matrix_df, "cluster_communication_matrix.csv", index=False)

    def _generate_rank_map(self, mapper_res):
        rank_map = {}
        rank_map_df = pd.DataFrame({"group_name": [], "src_rank": [], Constant.RANK_ID: []})
        for rank_data in mapper_res:
            rank_map.update(rank_data.get(self.RANK_MAP))
            matrix_df = rank_data.get(self.MATRIX_DATA)
            if matrix_df is None or matrix_df.empty:
                continue
            filter_matrix_df = matrix_df[matrix_df["src_rank"] == matrix_df["dst_rank"]]
            grouped_matrix_df = filter_matrix_df[['group_name', 'src_rank']].drop_duplicates()
            grouped_matrix_df[Constant.RANK_ID] = rank_data.get(Constant.RANK_ID)
            rank_map_df = pd.concat([grouped_matrix_df, rank_map_df], ignore_index=True)
        rank_map_df = rank_map_df.drop_duplicates()
        for _, row in rank_map_df.iterrows():
            group_name = row["group_name"]
            local_rank = row["src_rank"]
            global_rank = row[Constant.RANK_ID]
            if group_name not in rank_map:
                rank_map[group_name] = {local_rank: global_rank}
                continue
            if local_rank not in rank_map[group_name]:
                rank_map[group_name][local_rank] = global_rank
                continue
            if rank_map[group_name][local_rank] != global_rank:
                logger.warning(f"In the same communication group {group_name}, global rank {global_rank} "
                               f"and {rank_map[group_name][local_rank]} get the same local rank {local_rank}!")
        return rank_map

    def _mapper_func(self, data_map, analysis_class):
        result_data = {Constant.RANK_ID: data_map.get(Constant.RANK_ID)}
        profiler_db_path = data_map.get(Constant.PROFILER_DB_PATH)
        result_data[self.RANK_MAP] = self._get_parallel_group_info(profiler_db_path)
        analysis_db_path = data_map.get(Constant.ANALYSIS_DB_PATH)
        data_service = DatabaseService(analysis_db_path, {})
        data_service.add_table_for_query(TableConstant.TABLE_COMM_ANALYZER_MATRIX)
        matrix_data = data_service.query_data().get(TableConstant.TABLE_COMM_ANALYZER_MATRIX)
        if self._prof_type in [Constant.MSPROF, Constant.MINDSPORE]:
            matrix_data = self._trans_msprof_matrix_data(matrix_data)
        result_data[self.MATRIX_DATA] = matrix_data
        return result_data
