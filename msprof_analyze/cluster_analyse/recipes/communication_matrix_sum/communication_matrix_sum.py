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

    @property
    def required_db_keys(self):
        return [Constant.ANALYSIS_DB_PATH]

    @staticmethod
    def _build_rank_set_map(rank_map):
        return {
            group_name: ",".join(map(str, sorted(group_rank_map.values())))
            for group_name, group_rank_map in rank_map.items()
        }

    @staticmethod
    def _build_rank_mapping_df(rank_map):
        mapping_rows = [
            (group_name, local_rank, global_rank)
            for group_name, group_rank_map in rank_map.items()
            for local_rank, global_rank in group_rank_map.items()
        ]
        return pd.DataFrame(mapping_rows, columns=["group_name", "local_rank", "global_rank"])

    @staticmethod
    def _log_invalid_rank_mapping(grouped_df, rank_column, group_column, invalid_mask, message_template):
        if not invalid_mask.any():
            return
        invalid_df = grouped_df.loc[invalid_mask, [group_column, rank_column]].drop_duplicates()
        for group_name, rank_value in invalid_df.itertuples(index=False, name=None):
            logger.warning(message_template.format(rank=rank_value, group_name=group_name))

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
        p2p_mask = matrix_data["hccl_op_name"].str.lower().str.startswith(tuple(cls.P2P_HCOM))
        matrix_data.loc[p2p_mask, "type"] = Constant.P2P

        matrix_data = matrix_data.rename(columns={'hccl_op_name': 'op_name'})
        matrix_data["hccl_op_name"] = matrix_data["op_name"].str.split("__").str[0]

        grouped_df = matrix_data.groupby(['type', 'step', 'group_name', 'hccl_op_name', 'src_rank', 'dst_rank'])

        def get_specific_rows(group):
            sorted_group = group.sort_values(by='bandwidth')
            bottom1 = sorted_group.iloc[-1]
            bottom2 = sorted_group.iloc[-2] if len(group) > 1 else pd.Series()
            bottom3 = sorted_group.iloc[-3] if len(group) > 2 else pd.Series()
            top1 = sorted_group.iloc[0]
            middle = sorted_group.iloc[len(group) // 2]
            return pd.DataFrame(
                [top1, bottom1, bottom2, bottom3, middle],
                index=['top1', 'bottom1', 'bottom2', 'bottom3', 'middle']
            ).reset_index()

        example_df = grouped_df.apply(get_specific_rows).reset_index(drop=True)
        example_df = example_df.dropna().reset_index(drop=True)
        example_df["hccl_op_name"] = example_df["hccl_op_name"].astype(str) + "-" + example_df["index"].astype(str)
        example_df = example_df.drop(columns="index")

        total_df = matrix_data.groupby(['type', 'step', 'group_name', 'hccl_op_name', 'src_rank', 'dst_rank']).agg(
            {'transport_type': 'first', "transit_size": "sum", "transit_time": "sum"})
        total_df = total_df.reset_index()
        total_df["op_name"] = None
        total_df["hccl_op_name"] = total_df["hccl_op_name"].astype(str) + "-total"
        total_df['bandwidth'] = total_df['transit_size'] / total_df['transit_time'].where(
            total_df['transit_time'] != 0, other=0)

        result_df = pd.concat([example_df, total_df], ignore_index=True)
        return result_df

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
        matrix_frames = [
            matrix_df
            for rank_data in mapper_res
            for matrix_df in [rank_data.get(self.MATRIX_DATA)]
            if matrix_df is not None and not matrix_df.empty
        ]
        concat_df = pd.concat(matrix_frames, ignore_index=True) if matrix_frames else pd.DataFrame()

        if concat_df.empty:
            logger.error("Communication matrix data is None.")
            return

        rank_set_map = self._build_rank_set_map(rank_map)
        concat_df[self.RANK_SET] = concat_df["group_name"].map(rank_set_map).fillna("")
        p2p_mask = concat_df["type"] == Constant.P2P
        concat_df.loc[p2p_mask, self.RANK_SET] = Constant.P2P

        grouped_df = concat_df.groupby(
            [self.RANK_SET, 'step', "hccl_op_name", "group_name", "src_rank", "dst_rank"], sort=False).agg(
            {'transport_type': 'first', 'op_name': 'first', "transit_size": "sum", "transit_time": "sum"})
        grouped_df = grouped_df.reset_index()
        grouped_df["bandwidth"] = None

        rank_mapping_df = self._build_rank_mapping_df(rank_map)
        if rank_mapping_df.empty:
            filtered_df = grouped_df.iloc[0:0].copy()
        else:
            grouped_df = grouped_df.merge(
                rank_mapping_df.rename(columns={"local_rank": "src_rank", "global_rank": "src_global_rank"}),
                on=["group_name", "src_rank"], how="left"
            )
            grouped_df = grouped_df.merge(
                rank_mapping_df.rename(columns={"local_rank": "dst_rank", "global_rank": "dst_global_rank"}),
                on=["group_name", "dst_rank"], how="left"
            )

            src_invalid_mask = grouped_df["src_global_rank"].isna()
            self._log_invalid_rank_mapping(
                grouped_df, "src_rank", "group_name", src_invalid_mask,
                "The src local rank {rank} of the group_name {group_name} cannot be mapped to the global rank."
            )
            dst_invalid_mask = grouped_df["dst_global_rank"].isna()
            self._log_invalid_rank_mapping(
                grouped_df, "dst_rank", "group_name", dst_invalid_mask,
                "The dst local rank {rank} of the group_name {group_name} cannot be mapped to the global rank."
            )

            valid_mask = ~src_invalid_mask & ~dst_invalid_mask
            filtered_df = grouped_df.loc[valid_mask].copy()
            filtered_df["src_rank"] = filtered_df["src_global_rank"].astype("int64")
            filtered_df["dst_rank"] = filtered_df["dst_global_rank"].astype("int64")
            non_zero_transit_mask = filtered_df["transit_time"] != 0
            filtered_df.loc[:, "bandwidth"] = 0.0
            filtered_df.loc[non_zero_transit_mask, "bandwidth"] = (
                filtered_df.loc[non_zero_transit_mask, "transit_size"] /
                filtered_df.loc[non_zero_transit_mask, "transit_time"]
            )
            filtered_df = filtered_df.drop(columns=["src_global_rank", "dst_global_rank"])

        total_op_info = filtered_df[filtered_df['hccl_op_name'].str.contains('total', na=False)].groupby(
            [TableConstant.GROUP_NAME, 'step', "src_rank", "dst_rank"], sort=False).agg(
            {'transport_type': 'first', 'op_name': 'first', "transit_size": "sum",
             "transit_time": "sum"}
        )
        total_op_info = total_op_info.reset_index()
        total_op_info["hccl_op_name"] = Constant.TOTAL_OP_INFO
        total_op_info['bandwidth'] = total_op_info['transit_size'] / total_op_info['transit_time'].where(
            total_op_info['transit_time'] != 0, other=0)
        filtered_df["bandwidth"] = filtered_df["bandwidth"].astype("object")
        total_op_info["bandwidth"] = total_op_info["bandwidth"].astype("object")
        self.cluster_matrix_df = pd.concat([filtered_df, total_op_info], ignore_index=True).drop(columns=self.RANK_SET)

    def save_db(self):
        if self.cluster_matrix_df is None:
            return
        db_df = self.cluster_matrix_df.copy()
        for column in ["src_rank", "dst_rank"]:
            if column in db_df.columns:
                db_df[column] = db_df[column].astype("float64")
        self.dump_data(db_df, Constant.DB_CLUSTER_COMMUNICATION_ANALYZER,
                       self.TABLE_CLUSTER_COMM_MATRIX, index=False)

    def save_csv(self):
        self.dump_data(self.cluster_matrix_df, "cluster_communication_matrix.csv", index=False)

    def _generate_rank_map(self, mapper_res):
        rank_map = {}

        rank_map_frames = []
        for rank_data in mapper_res:
            rank_map.update(rank_data.get(self.RANK_MAP))
            matrix_df = rank_data.get(self.MATRIX_DATA)
            if matrix_df is None or matrix_df.empty:
                continue
            filter_matrix_df = matrix_df[matrix_df["src_rank"] == matrix_df["dst_rank"]]
            grouped_matrix_df = filter_matrix_df[['group_name', 'src_rank']].drop_duplicates()
            if grouped_matrix_df.empty:
                continue
            grouped_matrix_df[Constant.RANK_ID] = rank_data.get(Constant.RANK_ID)
            rank_map_frames.append(grouped_matrix_df)
        rank_map_df = (pd.concat(rank_map_frames, ignore_index=True).drop_duplicates()
                       if rank_map_frames else pd.DataFrame(columns=["group_name", "src_rank", Constant.RANK_ID]))

        for group_name, local_rank, global_rank in rank_map_df.itertuples(index=False, name=None):
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
