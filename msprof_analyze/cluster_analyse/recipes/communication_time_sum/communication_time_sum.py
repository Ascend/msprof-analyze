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

import numpy as np
import pandas as pd
from msprof_analyze.cluster_analyse.common_func.analysis_loader import get_class_from_name
from msprof_analyze.cluster_analyse.common_func.table_constant import TableConstant
from msprof_analyze.cluster_analyse.recipes.base_recipe_analysis import BaseRecipeAnalysis
from msprof_analyze.prof_common.constant import Constant
from msprof_analyze.prof_common.json_output import set_json_success
from msprof_analyze.prof_common.database_service import DatabaseService
from msprof_analyze.prof_common.logger import get_logger
from msprof_analyze.prof_common.db_manager import DBManager
from msprof_analyze.prof_common.file_manager import FileManager

logger = get_logger()


class CommunicationTimeSum(BaseRecipeAnalysis):
    TABLE_CLUSTER_COMM_TIME = "ClusterCommunicationTime"
    TABLE_CLUSTER_COMM_BANDWIDTH = "ClusterCommunicationBandwidth"

    TABLE_COMMUNICATION_GROUP_MAPPING = "CommunicationGroupMapping"
    TIME_GROUP_COLUMNS = [TableConstant.STEP, TableConstant.RANK_ID, TableConstant.GROUP_NAME]
    TIME_RATIO_COLUMNS = (
        (TableConstant.SYNCHRONIZATION_TIME, TableConstant.SYNCHRONIZATION_TIME_RATIO),
        (TableConstant.WAIT_TIME, TableConstant.WAIT_TIME_RATIO),
    )
    TIME_BREAKDOWN_COLUMNS = [
        TableConstant.TRANSIT_TIME,
        TableConstant.WAIT_TIME,
        TableConstant.SYNCHRONIZATION_TIME,
        TableConstant.IDLE_TIME,
    ]
    TIME_COLUMNS = [
        TableConstant.STEP,
        TableConstant.RANK_ID,
        TableConstant.HCCL_OP_NAME,
        TableConstant.GROUP_NAME,
        TableConstant.START_TIMESTAMP,
        "elapsed_time",
        TableConstant.TRANSIT_TIME,
        TableConstant.WAIT_TIME,
        TableConstant.SYNCHRONIZATION_TIME,
        TableConstant.IDLE_TIME,
        TableConstant.SYNCHRONIZATION_TIME_RATIO,
        TableConstant.WAIT_TIME_RATIO,
    ]
    BANDWIDTH_COLUMNS = [
        TableConstant.STEP,
        TableConstant.RANK_ID,
        TableConstant.HCCL_OP_NAME,
        TableConstant.GROUP_NAME,
        TableConstant.BAND_TYPE,
        TableConstant.TRANSIT_SIZE,
        TableConstant.TRANSIT_TIME,
        TableConstant.BANDWIDTH,
        TableConstant.LARGE_PACKET_RATIO,
        TableConstant.PACKAGE_SIZE,
        TableConstant.COUNT,
        TableConstant.TOTAL_DURATION,
    ]
    SUGGESTION = """
    ClusterCommunicationTime / cluster_communication_time.csv：按 step、rank、通信算子名记录通信总耗时、传输耗时、等待耗时、同步耗时及对应占比，识别具体通信算子的瓶颈类型。
    ClusterCommunicationBandwidth / cluster_communication_bandwidth.csv：按 step、rank、通信算子名记录通信算子的传输类型、数据量、耗时、带宽、大包占比与通信次数。用它快速识别低带宽通信算子。"
    """

    def __init__(self, params):
        super().__init__(params)
        self.params = params
        logger.info("CommunicationTimeSum init.")
        self.communication_time = pd.DataFrame(columns=self.TIME_COLUMNS)
        self.communication_bandwidth = pd.DataFrame(columns=self.BANDWIDTH_COLUMNS)

    @property
    def base_dir(self):
        return os.path.basename(os.path.dirname(__file__))

    @property
    def required_db_keys(self):
        return [Constant.ANALYSIS_DB_PATH]

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
            logger.warning("Mapper data is None, skipping empty results.")
            return
        cluster_db_path = os.path.join(self.output_path, Constant.DB_CLUSTER_COMMUNICATION_ANALYZER)
        data_service = DatabaseService(cluster_db_path, None)
        data_service.add_table_for_query(
            self.TABLE_COMMUNICATION_GROUP_MAPPING, [TableConstant.RANK_SET, TableConstant.GROUP_NAME]
        )
        df_dict = data_service.query_data()
        rank_set_df = df_dict.get(self.TABLE_COMMUNICATION_GROUP_MAPPING, None)
        if rank_set_df is None or rank_set_df.empty:
            logger.warning(
                "There is no %s data in %s, skipping empty results.",
                self.TABLE_COMMUNICATION_GROUP_MAPPING,
                cluster_db_path,
            )
            return
        rank_set_df = rank_set_df.drop_duplicates()
        communication_time = pd.concat(mapper_res_time) if mapper_res_time else pd.DataFrame()
        communication_bandwidth = pd.concat(mapper_res_bw) if mapper_res_bw else pd.DataFrame()
        if not communication_time.empty:
            self._compute_time_info(communication_time, rank_set_df)
        if not communication_bandwidth.empty:
            self._compute_bandwidth_info(communication_bandwidth, rank_set_df)

    def save_db(self):
        tables = []
        for data, table in (
            (self.communication_time, self.TABLE_CLUSTER_COMM_TIME),
            (self.communication_bandwidth, self.TABLE_CLUSTER_COMM_BANDWIDTH),
        ):
            if not data.empty:
                self._dump_data_to_db(data, table)
                tables.append(table)
        set_json_success(
            msg_dict={
                "db_path": os.path.join(self.output_path, Constant.DB_CLUSTER_COMMUNICATION_ANALYZER),
                "tables": tables,
            },
            suggestion=self.SUGGESTION,
        )

    def _dump_data_to_db(self, data, table_name):
        result_db = os.path.join(self.output_path, Constant.DB_CLUSTER_COMMUNICATION_ANALYZER)
        logger.info("Exporting data to database: %s, table: %s", result_db, table_name)
        conn, cursor = DBManager.create_connect_db(result_db)
        data.to_sql(table_name, conn, if_exists='replace', index=False)
        DBManager.destroy_db_connect(conn, cursor)

    def save_csv(self):
        csv_paths = []
        for data, file_name in (
            (self.communication_time, "cluster_communication_time.csv"),
            (self.communication_bandwidth, "cluster_communication_bandwidth.csv"),
        ):
            if not data.empty:
                self._dump_data_to_csv(data, file_name)
                csv_paths.append(os.path.join(self.output_path, file_name))
        set_json_success(
            msg_dict={"csv_path": csv_paths},
            suggestion=self.SUGGESTION,
        )

    def _dump_data_to_csv(self, data, file_name):
        result_csv = os.path.join(self.output_path, file_name)
        logger.info("Exporting data to CSV file: %s", result_csv)
        FileManager.create_csv_from_dataframe(result_csv, data, index=False)

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
        logger.info("Run CommunicationGroupMap recipe first to get %s table", self.TABLE_COMMUNICATION_GROUP_MAPPING)
        recipe_class = get_class_from_name("communication_group_map")
        if not recipe_class or len(recipe_class) != 2:  # 2: (class_name, class)
            return False
        try:
            group_map_recipe = recipe_class[1](self.params)
            group_map_recipe.run(context)
        except Exception as e:
            logger.error("Run CommunicationGroupMap recipe failed: %s!", e)
            return False
        return self.check_table_exist(self.TABLE_COMMUNICATION_GROUP_MAPPING)

    def _compute_time_info(self, communication_time, rank_set_df):
        """Preserve individual calls and append totals for each step/rank/group."""
        communication_time = communication_time.copy()
        for column in self.TIME_BREAKDOWN_COLUMNS:
            if column not in communication_time:
                communication_time[column] = Constant.INVALID_VALUE
            communication_time[column] = pd.to_numeric(communication_time[column], errors='coerce').fillna(
                Constant.INVALID_VALUE
            )
        merged_df = pd.merge(communication_time, rank_set_df, on=TableConstant.GROUP_NAME, how='left')
        total_time = self._compute_total_time_info(merged_df)
        for time_column, ratio_column in self.TIME_RATIO_COLUMNS:
            valid = communication_time[[time_column, TableConstant.TRANSIT_TIME]].ne(Constant.INVALID_VALUE).all(axis=1)
            # Preserve the legacy per-call ratio for detailed data.
            communication_time[ratio_column] = np.where(valid, 0, Constant.INVALID_VALUE)
        final_df = pd.concat([communication_time, total_time], axis=0)
        final_df = final_df.rename(columns={TableConstant.ELAPSED_TIME: "elapsed_time"})
        self.communication_time = final_df.reindex(columns=self.TIME_COLUMNS)

    def _compute_total_time_info(self, communication_time):
        """Sum valid values per metric; an entirely unavailable metric remains -1."""
        time_columns = [TableConstant.ELAPSED_TIME] + self.TIME_BREAKDOWN_COLUMNS
        valid_times = communication_time[self.TIME_GROUP_COLUMNS + time_columns].copy()
        valid_times[time_columns] = valid_times[time_columns].replace(Constant.INVALID_VALUE, np.nan)
        totals = (
            valid_times.groupby(self.TIME_GROUP_COLUMNS)[time_columns].sum(min_count=1).fillna(Constant.INVALID_VALUE)
        )
        for time_column, ratio_column in self.TIME_RATIO_COLUMNS:
            totals[ratio_column] = self._compute_total_time_ratio(communication_time, totals, time_column)
        totals[TableConstant.HCCL_OP_NAME] = Constant.TOTAL_OP_INFO
        totals[TableConstant.START_TIMESTAMP] = 0
        return totals.reset_index()

    def _compute_total_time_ratio(self, communication_time, totals, time_column):
        """Use the same valid calls for the numerator and transit time."""
        columns = [time_column, TableConstant.TRANSIT_TIME]
        valid = communication_time[columns].ne(Constant.INVALID_VALUE).all(axis=1)
        if valid.all():
            paired_totals = totals
        else:
            paired_totals = communication_time.loc[valid].groupby(self.TIME_GROUP_COLUMNS)[columns].sum()
        numerator = paired_totals[time_column]
        denominator = (numerator + paired_totals[TableConstant.TRANSIT_TIME]).replace(0, np.nan)
        ratio = (numerator / denominator).fillna(0).round(4)
        return ratio.reindex(totals.index, fill_value=Constant.INVALID_VALUE)

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
        sum_transit = (
            merged_df.groupby(
                [TableConstant.GROUP_NAME, TableConstant.STEP, TableConstant.RANK_ID, TableConstant.TRANSPORT_TYPE]
            )
            .apply(self._get_sum_distinct_op, include_groups=False)
            .reset_index()
            .rename(
                columns={TableConstant.TRANSIT_SIZE: sum_transit_size, TableConstant.TRANSIT_TIME: sum_transit_time}
            )
        )
        joined_df = pd.merge(
            merged_df,
            sum_transit,
            on=[TableConstant.GROUP_NAME, TableConstant.STEP, TableConstant.RANK_ID, TableConstant.TRANSPORT_TYPE],
        )
        # 按'rank_set', 'step', 'rank_id', 'transport_type', 'package_size'进行聚合
        agg_result = (
            joined_df.groupby(
                [
                    TableConstant.GROUP_NAME,
                    TableConstant.STEP,
                    TableConstant.RANK_ID,
                    TableConstant.TRANSPORT_TYPE,
                    TableConstant.PACKAGE_SIZE,
                ]
            )
            .agg(
                {
                    TableConstant.COUNT: 'sum',
                    TableConstant.TOTAL_DURATION: 'sum',
                    TableConstant.HCCL_OP_NAME: 'first',
                    sum_transit_size: 'first',
                    sum_transit_time: 'first',
                }
            )
            .reset_index()
        )
        agg_result[TableConstant.LARGE_PACKET_RATIO] = 0
        agg_result[TableConstant.HCCL_OP_NAME] = Constant.TOTAL_OP_INFO
        # 计算聚合数据带宽
        agg_result[TableConstant.BANDWIDTH] = (
            (agg_result[sum_transit_size] / agg_result[sum_transit_time].replace(0, np.nan)).fillna(0).round(4)
        )
        agg_result = agg_result.rename(
            columns={sum_transit_size: TableConstant.TRANSIT_SIZE, sum_transit_time: TableConstant.TRANSIT_TIME}
        )
        desired_order = [
            TableConstant.STEP,
            TableConstant.RANK_ID,
            TableConstant.HCCL_OP_NAME,
            TableConstant.GROUP_NAME,
            TableConstant.TRANSPORT_TYPE,
            TableConstant.TRANSIT_SIZE,
            TableConstant.TRANSIT_TIME,
            TableConstant.BANDWIDTH,
            TableConstant.LARGE_PACKET_RATIO,
            TableConstant.PACKAGE_SIZE,
            TableConstant.COUNT,
            TableConstant.TOTAL_DURATION,
        ]
        final_df = pd.concat([communication_bandwidth, agg_result], axis=0).reindex(columns=desired_order)
        final_df.rename(columns={TableConstant.TRANSPORT_TYPE: TableConstant.BAND_TYPE}, inplace=True)
        self.communication_bandwidth = final_df

    def _get_sum_distinct_op(self, op_df):
        return op_df.drop_duplicates(subset=[TableConstant.HCCL_OP_NAME])[
            [TableConstant.TRANSIT_SIZE, TableConstant.TRANSIT_TIME]
        ].sum()

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
        if is_time_df_empty and is_bandwidth_df_empty:
            logger.warning("There is no stats data in %s.", analysis_db_path)
            return None, None
        # 两类统计数据可独立生成，分别补充step、rank_id字段。
        if not is_time_df_empty:
            time_df[TableConstant.RANK_ID] = rank_id
            if TableConstant.STEP not in time_df.columns:
                time_df[TableConstant.STEP] = TableConstant.STEP
        if not is_bandwidth_df_empty:
            bandwidth_df[TableConstant.RANK_ID] = rank_id
            if TableConstant.STEP not in bandwidth_df.columns:
                bandwidth_df[TableConstant.STEP] = TableConstant.STEP
        return time_df, bandwidth_df
