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


import os

import numpy as np
import pandas as pd
from msprof_analyze.cluster_analyse.common_func.analysis_loader import get_class_from_name
from msprof_analyze.cluster_analyse.common_func.table_constant import TableConstant
from msprof_analyze.cluster_analyse.recipes.base_recipe_analysis import BaseRecipeAnalysis
from msprof_analyze.prof_common.constant import Constant
from msprof_analyze.prof_common.database_service import DatabaseService
from msprof_analyze.prof_common.logger import get_logger
from msprof_analyze.prof_common.db_manager import DBManager

logger = get_logger()


class CommunicationTimeSum(BaseRecipeAnalysis):
    TABLE_CLUSTER_COMM_TIME = "ClusterCommunicationTime"
    TABLE_CLUSTER_COMM_BANDWIDTH = "ClusterCommunicationBandwidth"

    TABLE_COMMUNICATION_GROUP_MAPPING = "CommunicationGroupMapping"

    def __init__(self, params):
        super().__init__(params)
        self.params = params
        logger.info("CommunicationTimeSum init.")
        self.communication_time = None
        self.communication_bandwidth = None

    @property
    def base_dir(self):
        return os.path.basename(os.path.dirname(__file__))

    def run(self, context):
        if not self.check_table_exist(self.TABLE_COMMUNICATION_GROUP_MAPPING):
            if not self.run_communication_group_map_recipe(context):
                logger.error("Create CommunicationGroupMap table failed! Skip CommunicationTimeSum.")
                return
        mapper_res = self.mapper_func(context)
        self.reducer_func(mapper_res)
        if self._export_type == Constant.DB:
            self.save_db()
        elif self._export_type == Constant.TEXT:
            self.save_csv()
        else:
            logger.error("Unknown export type.")

    def reducer_func(self, mapper_res):
        mapper_res_time = list(item[0] for item in mapper_res if item[0] is not None)
        mapper_res_bw = list(item[1] for item in mapper_res if item[1] is not None)
        if not mapper_res_time and not mapper_res_bw:
            logger.error("Mapper data is None.")
            return
        cluster_db_path = os.path.join(self.output_path, Constant.DB_CLUSTER_COMMUNICATION_ANALYZER)
        data_service = DatabaseService(cluster_db_path, None)
        data_service.add_table_for_query(self.TABLE_COMMUNICATION_GROUP_MAPPING,
                                         [TableConstant.RANK_SET, TableConstant.GROUP_NAME])
        df_dict = data_service.query_data()
        rank_set_df = df_dict.get(self.TABLE_COMMUNICATION_GROUP_MAPPING, None)
        if rank_set_df is None or rank_set_df.empty:
            logger.error(f"There is no {self.TABLE_COMMUNICATION_GROUP_MAPPING} data in {cluster_db_path}.")
            return
        rank_set_df = rank_set_df.drop_duplicates()
        communication_time = pd.concat(mapper_res_time)
        communication_bandwidth = pd.concat(mapper_res_bw)
        self._compute_time_info(communication_time, rank_set_df)
        self._compute_bandwidth_info(communication_bandwidth, rank_set_df)

    def save_db(self):
        self.dump_data(self.communication_time, Constant.DB_CLUSTER_COMMUNICATION_ANALYZER,
                       self.TABLE_CLUSTER_COMM_TIME, index=False)
        self.dump_data(self.communication_bandwidth, Constant.DB_CLUSTER_COMMUNICATION_ANALYZER,
                       self.TABLE_CLUSTER_COMM_BANDWIDTH, index=False)

    def save_csv(self):
        self.dump_data(self.communication_time, "cluster_communication_time.csv", index=False)
        self.dump_data(self.communication_bandwidth, "cluster_communication_bandwidth.csv", index=False)

    def check_table_exist(self, table):
        db_path = os.path.join(self.output_path, Constant.DB_CLUSTER_COMMUNICATION_ANALYZER)
        conn, cursor = DBManager.create_connect_db(db_path)
        table_exist = DBManager.judge_table_exists(cursor, table)
        DBManager.destroy_db_connect(conn, cursor)
        return table_exist

    def run_communication_group_map_recipe(self, context):
        """
        Run Recipe to create CommunicationGroupMapping table
        """
        logger.info(f"Run CommunicationGroupMap recipe first to get {self.TABLE_COMMUNICATION_GROUP_MAPPING} table")
        recipe_class = get_class_from_name("communication_group_map")
        if not recipe_class or len(recipe_class) != 2:  # 2: (class_name, class)
            return False
        try:
            group_map_recipe = recipe_class[1](self.params)
            group_map_recipe.run(context)
        except Exception as e:
            logger.error(f"Run CommunicationGroupMap recipe failed: {e}!")
            return False
        return self.check_table_exist(self.TABLE_COMMUNICATION_GROUP_MAPPING)

    def _compute_time_info(self, communication_time, rank_set_df):
        """
        communication_time: ['hccl_op_name', 'group_name', 'start_timestamp', 'elapse_time',
                            'transit_time', 'wait_time', 'synchronization_time', 'idle_time',
                            'step', 'type', 'rank_id']
        rank_set_df: ['rank_set', 'group_name']
        output: ['step', 'rank_id', 'hccl_op_name', 'group_name', 'start_timestamp', 'elapse_time', 'transit_time',
                'wait_time', 'synchronization_time', 'idle_time', 'synchronization_time_ratio', 'wait_time_ratio']

        按"step", "rank_id", "rank_set"字段进行分组，汇总"elapse_time", "transit_time", "wait_time",
        "synchronization_time", "idle_time"等时间数据，新增汇总行插入communication_time
        """
        merged_df = pd.merge(communication_time, rank_set_df, on=TableConstant.GROUP_NAME, how='left')
        summed_df = merged_df.groupby([TableConstant.STEP, TableConstant.RANK_ID, TableConstant.GROUP_NAME]).agg({
            TableConstant.ELAPSED_TIME: "sum",
            TableConstant.TRANSIT_TIME: "sum",
            TableConstant.WAIT_TIME: "sum",
            TableConstant.SYNCHRONIZATION_TIME: "sum",
            TableConstant.IDLE_TIME: "sum"
        }).reset_index()
        summed_df[TableConstant.HCCL_OP_NAME] = Constant.TOTAL_OP_INFO
        summed_df[TableConstant.START_TIMESTAMP] = 0
        # 计算 synchronization_time_ratio，wait_time_ratio
        summed_df[TableConstant.SYNCHRONIZATION_TIME_RATIO] = (
                summed_df[TableConstant.SYNCHRONIZATION_TIME] /
                (summed_df[TableConstant.TRANSIT_TIME] + summed_df[TableConstant.SYNCHRONIZATION_TIME]).replace(0,
                                                                                                                np.nan)
        ).fillna(0).round(4)
        summed_df[TableConstant.WAIT_TIME_RATIO] = (
                summed_df[TableConstant.WAIT_TIME] /
                (summed_df[TableConstant.TRANSIT_TIME] + summed_df[TableConstant.WAIT_TIME]).replace(0, np.nan)
        ).fillna(0).round(4)

        communication_time[TableConstant.SYNCHRONIZATION_TIME_RATIO] = 0
        communication_time[TableConstant.WAIT_TIME_RATIO] = 0
        desired_order = [TableConstant.STEP, TableConstant.RANK_ID, TableConstant.HCCL_OP_NAME,
                         TableConstant.GROUP_NAME, TableConstant.START_TIMESTAMP, TableConstant.ELAPSED_TIME,
                         TableConstant.TRANSIT_TIME, TableConstant.WAIT_TIME, TableConstant.SYNCHRONIZATION_TIME,
                         TableConstant.IDLE_TIME, TableConstant.SYNCHRONIZATION_TIME_RATIO,
                         TableConstant.WAIT_TIME_RATIO]
        # 合并汇总数据DataFrame
        final_df = pd.concat([communication_time, summed_df], axis=0).reindex(columns=desired_order)
        final_df.rename(columns={'elapse_time': 'elapsed_time'}, inplace=True)
        self.communication_time = final_df

    def _compute_bandwidth_info(self, communication_bandwidth, rank_set_df):
        """
        communication_bandwidth: ['hccl_op_name', 'group_name', 'transport_type', 'transit_size',
                                  'transit_time', 'bandwidth', 'large_packet_ratio', 'package_size',
                                  'count', 'total_duration', 'step', 'type', 'rank_id']
        output: ['step', 'rank_id', 'hccl_op_name', 'group_name', 'band_type', 'transit_size', 'transit_time',
                'bandwidth', 'large_packet_ratio', 'package_size', 'count', 'total_duration']
        rank_set_df: ['rank_set', 'group_name']
        按'rank_set', 'step', 'rank_id', 'transport_type', 'package_size'进行分组，对'count', 'total_duration'进行求和；
        对于同一'rank_set', 'step', 'rank_id', 'transport_type'下的数据，对'transit_size', 'transit_time'求和，
        其中如果'hccl_op_name'+'group_name'相同，求和时只累加一次
        """
        merged_df = pd.merge(communication_bandwidth, rank_set_df, on=TableConstant.GROUP_NAME, how='left')
        # 计算每个rank_set/step/rank_id/transport_type分组下去重后的transit_size和transit_time总和
        sum_transit_size = 'sum_transit_size'
        sum_transit_time = 'sum_transit_time'
        sum_transit = merged_df.groupby(
            [TableConstant.GROUP_NAME, TableConstant.STEP, TableConstant.RANK_ID, TableConstant.TRANSPORT_TYPE]).apply(
            self._get_sum_distinct_op).reset_index().rename(columns={
                TableConstant.TRANSIT_SIZE: sum_transit_size,
                TableConstant.TRANSIT_TIME: sum_transit_time
            })
        joined_df = pd.merge(merged_df, sum_transit,
                             on=[TableConstant.GROUP_NAME, TableConstant.STEP, TableConstant.RANK_ID,
                                 TableConstant.TRANSPORT_TYPE])
        # 按'rank_set', 'step', 'rank_id', 'transport_type', 'package_size'进行聚合
        agg_result = joined_df.groupby(
            [TableConstant.GROUP_NAME, TableConstant.STEP, TableConstant.RANK_ID, TableConstant.TRANSPORT_TYPE,
             TableConstant.PACKAGE_SIZE]
        ).agg({
            TableConstant.COUNT: 'sum',
            TableConstant.TOTAL_DURATION: 'sum',
            TableConstant.HCCL_OP_NAME: 'first',
            sum_transit_size: 'first',
            sum_transit_time: 'first'
        }).reset_index()
        agg_result[TableConstant.LARGE_PACKET_RATIO] = 0
        agg_result[TableConstant.HCCL_OP_NAME] = Constant.TOTAL_OP_INFO
        # 计算聚合数据带宽
        agg_result[TableConstant.BANDWIDTH] = (
                agg_result[sum_transit_size] / agg_result[sum_transit_time].replace(0, np.nan)
        ).fillna(0).round(4)
        agg_result = agg_result.rename(columns={
            sum_transit_size: TableConstant.TRANSIT_SIZE,
            sum_transit_time: TableConstant.TRANSIT_TIME
        })
        desired_order = [TableConstant.STEP, TableConstant.RANK_ID, TableConstant.HCCL_OP_NAME,
                         TableConstant.GROUP_NAME, TableConstant.TRANSPORT_TYPE, TableConstant.TRANSIT_SIZE,
                         TableConstant.TRANSIT_TIME, TableConstant.BANDWIDTH, TableConstant.LARGE_PACKET_RATIO,
                         TableConstant.PACKAGE_SIZE, TableConstant.COUNT, TableConstant.TOTAL_DURATION]
        final_df = pd.concat([communication_bandwidth, agg_result], axis=0).reindex(columns=desired_order)
        final_df.rename(columns={TableConstant.TRANSPORT_TYPE: TableConstant.BAND_TYPE}, inplace=True)
        self.communication_bandwidth = final_df

    def _get_sum_distinct_op(self, op_df):
        return op_df.drop_duplicates(subset=[TableConstant.HCCL_OP_NAME, TableConstant.GROUP_NAME])[
            [TableConstant.TRANSIT_SIZE, TableConstant.TRANSIT_TIME]].sum()

    def _mapper_func(self, data_map, analysis_class):
        analysis_db_path = data_map.get(Constant.ANALYSIS_DB_PATH)
        rank_id = data_map.get(Constant.RANK_ID)
        step_range = data_map.get(Constant.STEP_RANGE)
        date_service = DatabaseService(analysis_db_path, step_range)
        date_service.add_table_for_query(Constant.TABLE_COMM_ANALYZER_TIME)
        date_service.add_table_for_query(Constant.TABLE_COMM_ANALYZER_BANDWIDTH)
        df_dict = date_service.query_data()
        time_df = df_dict.get(Constant.TABLE_COMM_ANALYZER_TIME)
        bandwidth_df = df_dict.get(Constant.TABLE_COMM_ANALYZER_BANDWIDTH)

        is_time_df_empty = time_df is None or time_df.empty
        is_bandwidth_df_empty = bandwidth_df is None or bandwidth_df.empty
        if is_time_df_empty or is_bandwidth_df_empty:
            logger.warning(f"There is no stats data in {analysis_db_path}.")
            return None, None
        # 补充step、rank_id字段
        time_df[TableConstant.RANK_ID] = rank_id
        bandwidth_df[TableConstant.RANK_ID] = rank_id
        if TableConstant.STEP not in time_df.columns:
            time_df[TableConstant.STEP] = TableConstant.STEP
        if TableConstant.STEP not in bandwidth_df.columns:
            bandwidth_df[TableConstant.STEP] = TableConstant.STEP
        return time_df, bandwidth_df
