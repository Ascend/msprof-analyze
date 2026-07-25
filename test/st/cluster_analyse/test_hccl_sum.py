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
# pylint: disable=W0201, R0801
import os
from unittest import TestCase
import pandas as pd

from msprof_analyze.cluster_analyse.recipes.hccl_sum.hccl_sum import HcclSum
from msprof_analyze.prof_common.constant import Constant
from msprof_analyze.prof_common.db_manager import DBManager
from msprof_analyze.prof_common.path_manager import PathManager
from test.st.utils import execute_cmd
from test.st.utils import ST_DATA_PATH


class TestHcclSum(TestCase):
    """
    Test recipe: hccl_sum
    """

    CLUSTER_PATH = os.path.join(ST_DATA_PATH, "cluster_data_2_db")
    OUTPUT_PATH = os.path.join(os.path.abspath(os.path.dirname(__file__)), "TestHcclSum")
    COMMAND_SUCCESS = 0

    def setup_class(self):
        PathManager.make_dir_safety(self.OUTPUT_PATH)
        cmd = [
            "msprof-analyze",
            "cluster",
            "-d",
            self.CLUSTER_PATH,
            "-m",
            "hccl_sum",
            "--output_path",
            self.OUTPUT_PATH,
            "--force",
        ]
        if execute_cmd(cmd) != self.COMMAND_SUCCESS or not os.path.exists(self.OUTPUT_PATH):
            self.fail("HcclSum task failed.")
        self.db_path = os.path.join(
            self.OUTPUT_PATH, Constant.CLUSTER_ANALYSIS_OUTPUT, Constant.DB_CLUSTER_COMMUNICATION_ANALYZER
        )
        self.conn, self.cursor = DBManager.create_connect_db(self.db_path)
        self.db_path_base = os.path.join(
            self.CLUSTER_PATH, "cluster_analysis_output_base", Constant.DB_CLUSTER_COMMUNICATION_ANALYZER
        )
        self.conn_base, self.cursor_base = DBManager.create_connect_db(self.db_path_base)

    def teardown_class(self):
        DBManager.destroy_db_connect(self.conn, self.cursor)
        DBManager.destroy_db_connect(self.conn_base, self.cursor_base)
        PathManager.remove_path_safety(self.OUTPUT_PATH)

    def check_tables_in_db(self):
        expected_tables = [
            HcclSum.TABLE_ALL_RANK_STATS,
            HcclSum.TABLE_PER_RANK_STATS,
            HcclSum.TABLE_TOP_OP_STATS,
            HcclSum.TABLE_GROUP_NAME_MAP,
        ]
        return DBManager.check_tables_in_db(self.db_path, *expected_tables)

    def check_hccl_all_rank_stats_columns(self):
        # 检查HcclAllRankStats的表头
        expected_columns = ["OpType", "Count", "MeanNs", "StdNs", "MinNs", "Q1Ns", "MedianNs", "Q3Ns", "MaxNs", "SumNs"]
        return DBManager.get_table_columns_name(self.cursor, HcclSum.TABLE_ALL_RANK_STATS) == expected_columns

    def check_hccl_per_rank_stats_columns(self):
        # 检查HcclPerRankStats的表头
        expected_columns = [
            "OpType",
            "Count",
            "MeanNs",
            "StdNs",
            "MinNs",
            "Q1Ns",
            "MedianNs",
            "Q3Ns",
            "MaxNs",
            "SumNs",
            "Rank",
        ]
        return DBManager.get_table_columns_name(self.cursor, HcclSum.TABLE_PER_RANK_STATS) == expected_columns

    def check_hccl_top_op_stats_columns(self):
        # 检查HcclTopOpStats的表头
        expected_columns = [
            "OpName",
            "Count",
            "MeanNs",
            "StdNs",
            "MinNs",
            "Q1Ns",
            "MedianNs",
            "Q3Ns",
            "MaxNs",
            "SumNs",
            "MinRank",
            "MaxRank",
        ]
        return DBManager.get_table_columns_name(self.cursor, HcclSum.TABLE_TOP_OP_STATS) == expected_columns

    def check_hccl_group_name_map_columns(self):
        # 检查HcclGroupNameMap的表头
        expected_columns = ["GroupName", "GroupId", "Ranks"]
        return DBManager.get_table_columns_name(self.cursor, HcclSum.TABLE_GROUP_NAME_MAP) == expected_columns

    def test_hccl_sum_should_run_success_when_given_cluster_data(self):
        self.assertTrue(self.check_tables_in_db(), msg="DB does not exist or is missing tables.")
        self.assertTrue(
            self.check_hccl_all_rank_stats_columns(),
            msg=f"The header of {HcclSum.TABLE_ALL_RANK_STATS} does not meet expectations.",
        )
        self.assertTrue(
            self.check_hccl_per_rank_stats_columns(),
            msg=f"The header of {HcclSum.TABLE_PER_RANK_STATS} does not meet expectations.",
        )
        self.assertTrue(
            self.check_hccl_top_op_stats_columns(),
            msg=f"The header of {HcclSum.TABLE_TOP_OP_STATS} does not meet expectations.",
        )
        self.assertTrue(
            self.check_hccl_group_name_map_columns(),
            msg=f"The header of {HcclSum.TABLE_GROUP_NAME_MAP} does not meet expectations.",
        )

    def test_hccl_all_rank_stats_data_when_given_cluster_data(self):
        query = f"select * from {HcclSum.TABLE_ALL_RANK_STATS}"
        df = pd.read_sql(query, self.conn)
        df_base = pd.read_sql(query, self.conn_base)
        self.assertEqual(list(df.columns), list(df_base.columns))
        self.assertEqual(len(df), len(df_base))

    def test_hccl_per_rank_stats_data_when_given_cluster_data(self):
        query = f"select * from {HcclSum.TABLE_PER_RANK_STATS}"
        df = pd.read_sql(query, self.conn)
        df_base = pd.read_sql(query, self.conn_base)
        self.assertEqual(list(df.columns), list(df_base.columns))
        self.assertEqual(len(df), len(df_base))

    def test_hccl_top_op_stats_data_when_given_cluster_data(self):
        query = f"select * from {HcclSum.TABLE_TOP_OP_STATS}"
        df = pd.read_sql(query, self.conn)
        df_base = pd.read_sql(query, self.conn_base)
        self.assertEqual(list(df.columns), list(df_base.columns))
        self.assertEqual(len(df), len(df_base))

    def test_hccl_group_name_map_data_when_given_cluster_data(self):
        query = f"select * from {HcclSum.TABLE_GROUP_NAME_MAP}"
        df = pd.read_sql(query, self.conn)
        df_base = pd.read_sql(query, self.conn_base)
        self.assertEqual(list(df.columns), list(df_base.columns))
        self.assertEqual(len(df), len(df_base))
