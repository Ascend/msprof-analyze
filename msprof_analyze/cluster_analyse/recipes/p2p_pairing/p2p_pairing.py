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

from msprof_analyze.cluster_analyse.recipes.base_recipe_analysis import BaseRecipeAnalysis
from msprof_analyze.prof_common.constant import Constant
from msprof_analyze.prof_common.constant import ProfilerTableConstant
from msprof_analyze.prof_common.db_manager import DBManager
from msprof_analyze.prof_common.logger import get_logger
from msprof_analyze.prof_exports.p2p_pairing_export import P2PPairingExport


logger = get_logger()


class P2PPairing(BaseRecipeAnalysis):
    P2P_OP_NAME_PATTERN = r"^hcom_([Ss]end|[Rr](ecv|eceive))__\d+_\d+_\d+$"
    DOMAIN_ID_EXTRACT_PATTERN = r"__(\d+)_\d+_\d+"
    RECEIVE_OP_MATCH_PATTERN = r"[Rr]ecv|[Rr]eceive"
    VALID_DST_RANK_TASK_TYPE = [Constant.NOTIFY_RECORD, Constant.NOTIFY_WAIT]
    # intermediate dataframe column names
    COL_NAME_IS_UNIQUE_VALUE = "isUniqueValue"
    COL_NAME_OP_DST_RANK = "opDstRank"
    COL_NAME_DOMAIN_ID = "domainId"
    COL_NAME_IS_RECEIVE = "isReceive"
    COL_NAME_OP_NAMING_INDEX = "opNamingIndex"
    # output column name
    COL_NAME_P2P_CONNECTION_ID = "opConnectionId"
    # export params
    TARGET_TABLE_NAME = Constant.TABLE_COMMUNICATION_OP

    def __init__(self, params):
        super().__init__(params)
        logger.info("P2PPairing init.")

    @property
    def base_dir(self):
        return os.path.basename(os.path.dirname(__file__))

    def run(self, context):
        self.mapper_func(context)
        logger.info("P2PPairing completed.")

    def update_connection_info_to_table(self, df_result, profiler_db_path):
        """
        将生成好的连接ID添加至COMMUNICATION OP表中，新增列`opConnectionId`。目前只处理Send和Recv算子，对应的opId会更新具体的连接ID，
        否则置空
        """
        conn, cursor = DBManager.create_connect_db(profiler_db_path)
        try:
            ret = DBManager.check_columns_exist(cursor, self.TARGET_TABLE_NAME, {self.COL_NAME_P2P_CONNECTION_ID})
            if ret is None:
                logger.error("Failed to connect to the database. Please check the database configurations")
                return
            if self.COL_NAME_P2P_CONNECTION_ID not in ret:
                DBManager.execute_sql(
                    conn, f"ALTER TABLE {self.TARGET_TABLE_NAME} ADD COLUMN {self.COL_NAME_P2P_CONNECTION_ID} TEXT"
                )
            DBManager.execute_sql(
                conn,
                f"UPDATE {self.TARGET_TABLE_NAME} SET {self.COL_NAME_P2P_CONNECTION_ID} = NULL",  # nosec B608
            )
            DBManager.executemany_sql(
                conn,
                ""  # nosec B608
                f"""
                UPDATE {self.TARGET_TABLE_NAME}
                SET {self.COL_NAME_P2P_CONNECTION_ID} = ?
                WHERE {ProfilerTableConstant.OP_NAME} = ?;""",
                [
                    (row[self.COL_NAME_P2P_CONNECTION_ID], row[P2PPairingExport.CO_OP_NAME])
                    for _, row in df_result.iterrows()
                ],
            )
        finally:
            DBManager.destroy_db_connect(conn, cursor)

    def generate_p2p_connection_index(self, df):
        """
        生成每一个P2P的算子的对应连接ID，连接ID的生成规则按照`通信域_Send卡号_Recv卡号_算子index`。
        其中通信域为通信域字符串的哈希值后三位表示；Send卡和Recv卡分别为这个通信域内的local rank号；算子index是这两张卡之间按时间线排序，
        出现Send和Recv算子已有的频次。比如说，一个算子的名称为`hcom_send_233_58_1`，自己在通信域内的rank号为0，对端的rank号为1；在这之前
        并没有存在0卡向1卡的Send任务。因此生成的id为`233_0_1_0`
        """
        df[self.COL_NAME_DOMAIN_ID] = df[P2PPairingExport.OP_NAME].str.extract(self.DOMAIN_ID_EXTRACT_PATTERN)[0]
        df[self.COL_NAME_IS_RECEIVE] = df[P2PPairingExport.OP_NAME].str.contains(self.RECEIVE_OP_MATCH_PATTERN)
        df.loc[df[self.COL_NAME_IS_RECEIVE], [P2PPairingExport.SRC_RANK, self.COL_NAME_OP_DST_RANK]] = df.loc[
            df[self.COL_NAME_IS_RECEIVE], [self.COL_NAME_OP_DST_RANK, P2PPairingExport.SRC_RANK]
        ].values
        df[P2PPairingExport.SRC_RANK] = df[P2PPairingExport.SRC_RANK].astype(int)
        df[self.COL_NAME_OP_DST_RANK] = df[self.COL_NAME_OP_DST_RANK].astype(int)
        df[self.COL_NAME_OP_NAMING_INDEX] = (
            df.sort_values(by=[P2PPairingExport.START_TIME])
            .groupby([P2PPairingExport.SRC_RANK, self.COL_NAME_OP_DST_RANK])
            .cumcount()
        )
        df[self.COL_NAME_P2P_CONNECTION_ID] = (
            df[self.COL_NAME_DOMAIN_ID].astype(str)
            + "_"
            + df[P2PPairingExport.SRC_RANK].astype(str)
            + "_"
            + df[self.COL_NAME_OP_DST_RANK].astype(str)
            + "_"
            + df[self.COL_NAME_OP_NAMING_INDEX].astype(str)
        )
        return df.reset_index()

    def fine_filtering_src_dst_ranks(self, df: pd.DataFrame):
        """
        精筛符合条件的数据：
        1、小算子任务包含了“Notify_Record”和“Notify_Wait”的数据
        2、上一步得到的数据中对端卡号是否一致，如果不一致则会抛出warning
        3、步骤1得到数据中本端卡号是否一致，如果不一致则会报出error返回空值
        """
        df = df[df[P2PPairingExport.TASK_TYPE].isin(self.VALID_DST_RANK_TASK_TYPE)]
        if df.empty:
            return df

        def check_src_dst_rank_unique(group):
            return group[P2PPairingExport.DST_RANK].nunique() == 1 and group[P2PPairingExport.SRC_RANK].nunique() == 1

        unique_src_dst_rank: pd.DataFrame = df.groupby(P2PPairingExport.OP_NAME).apply(check_src_dst_rank_unique)

        def get_dst_rank_value(group):
            if group[P2PPairingExport.DST_RANK].nunique() == 1:
                return group[P2PPairingExport.DST_RANK].iloc[0]
            return np.nan

        dst_rank_value: pd.DataFrame = df.groupby(P2PPairingExport.OP_NAME, group_keys=False).apply(get_dst_rank_value)

        df = df.copy()
        df[self.COL_NAME_IS_UNIQUE_VALUE] = df[P2PPairingExport.OP_NAME].map(unique_src_dst_rank)
        df[self.COL_NAME_OP_DST_RANK] = df[P2PPairingExport.OP_NAME].map(dst_rank_value)
        df[self.COL_NAME_OP_DST_RANK] = df[self.COL_NAME_OP_DST_RANK].fillna(Constant.INVALID_RANK_NUM)
        df[self.COL_NAME_OP_DST_RANK] = df[self.COL_NAME_OP_DST_RANK].astype(df[P2PPairingExport.DST_RANK].dtype)

        check_src_dst_rank_unique_false: pd.DataFrame = df[~df[self.COL_NAME_IS_UNIQUE_VALUE]]
        if not check_src_dst_rank_unique_false.empty:
            logger.warning(
                "There are communication op entries with multiple destination ranks! "
                "Please check the corresponding profiler database file."
            )

        df = df[df[self.COL_NAME_IS_UNIQUE_VALUE]]
        return df.reset_index()

    def filter_data_by_group_name(self, df: pd.DataFrame):
        """
        初步筛选出目标数据：
        1、筛选出Send和Recv的算子
        2、筛选出同一opId在COMMUNICATION OP中groupName和COMMUNICATION TASK INFO中groupName一致的数据
        """
        df = df[df[P2PPairingExport.OP_NAME].str.match(self.P2P_OP_NAME_PATTERN)]
        filtered_df = df[df[P2PPairingExport.CO_GROUP_NAME] == df[P2PPairingExport.CTI_GROUP_NAME]]
        anomaly_group_match = df[df[P2PPairingExport.CO_GROUP_NAME] != df[P2PPairingExport.CTI_GROUP_NAME]]
        if not anomaly_group_match.empty:
            logger.warning(
                "Group name mismatch in %s entries. Please check the profiler database in communication task info.",
                len(anomaly_group_match),
            )
        return filtered_df.reset_index()

    def _mapper_func(self, data_map, analysis_class):
        profiler_db_path: str = data_map.get(Constant.PROFILER_DB_PATH)
        if not DBManager.check_tables_in_db(
            profiler_db_path, Constant.TABLE_COMMUNICATION_OP, Constant.TABLE_COMMUNICATION_TASK_INFO
        ):
            logger.warning(
                "Some communication data is missing. Please check whether the data level is at level1 or above."
            )
            return None
        step_range = data_map.get(Constant.STEP_RANGE)
        df: pd.DataFrame = P2PPairingExport(profiler_db_path, analysis_class, step_range).read_export_db()
        if df is None or df.empty:
            logger.warning("There is no stats data in %s.", profiler_db_path)
            return None

        df = self.filter_data_by_group_name(df)
        if df.empty:
            return None

        df_filtered = self.fine_filtering_src_dst_ranks(df.copy())
        if df_filtered.empty:
            logger.warning(
                "The result of fine_filtering_src_dst_ranks is empty!"
                "Please check whether the data level is at level1 or above."
            )
            return None

        df_result = (
            df_filtered.groupby([P2PPairingExport.OP_NAME, P2PPairingExport.CO_OP_NAME])
            .agg(
                {
                    P2PPairingExport.START_TIME: "first",
                    P2PPairingExport.SRC_RANK: "first",
                    self.COL_NAME_OP_DST_RANK: "first",
                }
            )
            .reset_index()
        )

        df_result = self.generate_p2p_connection_index(df_result)

        df_result = df_result[[P2PPairingExport.CO_OP_NAME, self.COL_NAME_P2P_CONNECTION_ID]]

        self.update_connection_info_to_table(df_result, profiler_db_path)
        return data_map.get(Constant.RANK_ID)
