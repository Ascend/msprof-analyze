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

from msprof_analyze.cluster_analyse.recipes.compute_op_sum.compute_op_sum import ComputeOpSum
from msprof_analyze.prof_common.constant import Constant
from msprof_analyze.prof_common.db_manager import DBManager
from msprof_analyze.prof_common.path_manager import PathManager
from test.st.utils import execute_cmd
from test.st.utils import ST_DATA_PATH


class TestComputeOpSum(TestCase):
    """
    Test recipe: compute_op_sum
    """

    CLUSTER_PATH = os.path.join(ST_DATA_PATH, "cluster_data_2_db")
    OUTPUT_PATH = os.path.join(os.path.abspath(os.path.dirname(__file__)), "TestComputeOpSum")
    COMMAND_SUCCESS = 0

    def setup_class(self):
        self.db_path_base = os.path.join(
            self.CLUSTER_PATH, "cluster_analysis_output_base", Constant.DB_CLUSTER_COMMUNICATION_ANALYZER
        )
        self.conn_base, self.cursor_base = DBManager.create_connect_db(self.db_path_base)

    def connect_db(self, cmd):
        # 需要手动调用
        PathManager.make_dir_safety(self.OUTPUT_PATH)
        if execute_cmd(cmd) != self.COMMAND_SUCCESS or not os.path.exists(self.OUTPUT_PATH):
            self.fail("ComputeOpSum task failed.")
        self.db_path = os.path.join(
            self.OUTPUT_PATH, Constant.CLUSTER_ANALYSIS_OUTPUT, Constant.DB_CLUSTER_COMMUNICATION_ANALYZER
        )
        self.conn, self.cursor = DBManager.create_connect_db(self.db_path)

    def tearDown(self):
        DBManager.destroy_db_connect(self.conn, self.cursor)
        PathManager.remove_path_safety(self.OUTPUT_PATH)

    def check_tables_in_db(self):
        expected_tables = [
            ComputeOpSum.TABLE_ALL_RANK_STATS,
            ComputeOpSum.TABLE_PER_RANK_STATS_BY_OPNAME,
            ComputeOpSum.TABLE_PER_RANK_STATS_BY_OPTYPE,
        ]
        return DBManager.check_tables_in_db(self.db_path, *expected_tables)

    def check_tables_in_db_when_exclude_op_name(self):
        expected_tables = [
            ComputeOpSum.TABLE_ALL_RANK_STATS,
            ComputeOpSum.TABLE_PER_RANK_STATS_BY_OPTYPE,
        ]
        return DBManager.check_tables_in_db(self.db_path, *expected_tables) and not DBManager.check_tables_in_db(
            self.db_path, ComputeOpSum.TABLE_PER_RANK_STATS_BY_OPNAME
        )

    def check_compute_op_all_rank_stats_columns(self):
        # 检查ComputeOpAllRankStats的表头
        expected_columns = [
            "OpType",
            "TaskType",
            "Count",
            "MeanNs",
            "StdNs",
            "MinNs",
            "Q1Ns",
            "MedianNs",
            "Q3Ns",
            "MaxNs",
            "SumNs",
        ]
        return DBManager.get_table_columns_name(self.cursor, ComputeOpSum.TABLE_ALL_RANK_STATS) == expected_columns

    def check_compute_op_per_rank_stats_by_opname_columns(self):
        # 检查ComputeOpPerRankStatsByOpName的表头
        expected_columns = [
            "OpName",
            "OpType",
            "TaskType",
            "InputShapes",
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
        return (
            DBManager.get_table_columns_name(self.cursor, ComputeOpSum.TABLE_PER_RANK_STATS_BY_OPNAME)
            == expected_columns
        )

    def check_compute_op_per_rank_stats_by_optype_columns(self):
        # 检查ComputeOpPerRankStatsByOpType的表头
        expected_columns = [
            "OpType",
            "TaskType",
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
        return (
            DBManager.get_table_columns_name(self.cursor, ComputeOpSum.TABLE_PER_RANK_STATS_BY_OPTYPE)
            == expected_columns
        )

    def check_compute_op_all_rank_stats_data_when_given_cluster_data(self):
        query = f"select * from {ComputeOpSum.TABLE_ALL_RANK_STATS}"
        df = pd.read_sql(query, self.conn)
        df_base = pd.read_sql(query, self.conn_base)
        self.assertEqual(len(df), len(df_base))
        self.assertEqual(list(df.columns), list(df_base.columns))

    def check_compute_op_per_rank_stats_by_opname_data_when_given_cluster_data(self):
        query = f"select * from {ComputeOpSum.TABLE_PER_RANK_STATS_BY_OPNAME}"
        df = pd.read_sql(query, self.conn)
        df_base = pd.read_sql(query, self.conn_base)
        self.assertEqual(len(df), len(df_base))
        self.assertEqual(list(df.columns), list(df_base.columns))

    def check_compute_op_per_rank_stats_by_optype_data_when_given_cluster_data(self):
        query = f"select * from {ComputeOpSum.TABLE_PER_RANK_STATS_BY_OPTYPE}"
        df = pd.read_sql(query, self.conn)
        df_base = pd.read_sql(query, self.conn_base)
        self.assertEqual(len(df), len(df_base))
        self.assertEqual(list(df.columns), list(df_base.columns))

    def test_compute_op_sum_should_run_success_when_given_cluster_data(self):
        cmd = [
            "msprof-analyze",
            "cluster",
            "-d",
            self.CLUSTER_PATH,
            "-m",
            "compute_op_sum",
            "-o",
            self.OUTPUT_PATH,
            "--force",
        ]
        self.connect_db(cmd)
        self.assertTrue(self.check_tables_in_db(), msg="DB does not exist or is missing tables.")
        self.assertTrue(
            self.check_compute_op_all_rank_stats_columns(),
            msg=f"The header of {ComputeOpSum.TABLE_ALL_RANK_STATS} does not meet expectations.",
        )
        self.assertTrue(
            self.check_compute_op_per_rank_stats_by_opname_columns(),
            msg=f"The header of {ComputeOpSum.TABLE_PER_RANK_STATS_BY_OPNAME} does not meet expectations.",
        )
        self.assertTrue(
            self.check_compute_op_per_rank_stats_by_optype_columns(),
            msg=f"The header of {ComputeOpSum.TABLE_PER_RANK_STATS_BY_OPTYPE} does not meet expectations.",
        )
        self.check_compute_op_all_rank_stats_data_when_given_cluster_data()
        self.check_compute_op_per_rank_stats_by_opname_data_when_given_cluster_data()
        self.check_compute_op_per_rank_stats_by_optype_data_when_given_cluster_data()

    def test_compute_op_sum_should_run_success_when_given_cluster_data_and_exclude_op_name(self):
        cmd = [
            "msprof-analyze",
            "cluster",
            "-d",
            self.CLUSTER_PATH,
            "-m",
            "compute_op_sum",
            "-o",
            self.OUTPUT_PATH,
            "--exclude_op_name",
            "--force",
        ]
        self.connect_db(cmd)
        self.assertTrue(self.check_tables_in_db_when_exclude_op_name(), msg="DB does not exist or is missing tables.")
        self.assertTrue(
            self.check_compute_op_all_rank_stats_columns(),
            msg=f"The header of {ComputeOpSum.TABLE_ALL_RANK_STATS} does not meet expectations.",
        )
        self.assertTrue(
            self.check_compute_op_per_rank_stats_by_optype_columns(),
            msg=f"The header of {ComputeOpSum.TABLE_PER_RANK_STATS_BY_OPTYPE} does not meet expectations.",
        )
        self.check_compute_op_all_rank_stats_data_when_given_cluster_data()
        self.check_compute_op_per_rank_stats_by_optype_data_when_given_cluster_data()
