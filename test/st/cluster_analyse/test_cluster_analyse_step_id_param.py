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
from unittest import TestCase

import pandas as pd

from msprof_analyze.prof_common.path_manager import PathManager
from test.st.utils import execute_cmd
from msprof_analyze.prof_common.db_manager import DBManager
from test.st.utils import ST_DATA_PATH


class TestClusterAnalyseStepIdParam(TestCase):
    """
       Test cluster analyse pytorch db with step_id param
    """
    CLUSTER_PATH = os.path.join(ST_DATA_PATH, "cluster_data_2_db")
    OUTPUT_PATH = os.path.join(os.path.abspath(os.path.dirname(__file__)), "TestClusterAnalyseStepIdParam")
    COMMAND_SUCCESS = 0

    def setup_class(self):
        # generate db data
        PathManager.make_dir_safety(self.OUTPUT_PATH)
        cmd = ["msprof-analyze", "cluster", "-d", self.CLUSTER_PATH, "-m", "hccl_sum",
               "--output_path", self.OUTPUT_PATH, "--force", "--step_id", "5"]
        if execute_cmd(cmd) != self.COMMAND_SUCCESS or not os.path.exists(self.OUTPUT_PATH):
            self.fail("pytorch db cluster analyse task failed.")
        self.db_path = os.path.join(self.OUTPUT_PATH, "cluster_analysis_output", "cluster_analysis.db")
        self.conn, self.cursor = DBManager.create_connect_db(self.db_path)

    def teardown_class(self):
        # Delete db Data
        DBManager.destroy_db_connect(self.conn, self.cursor)
        PathManager.remove_path_safety(self.OUTPUT_PATH)

    def test_all_rank_stats(self):
        query = "select * from HcclAllRankStats"
        data = pd.read_sql(query, self.conn)
        self.assertEqual(data[data["OpType"] == "hcom_allGather_"]["Count"].tolist()[0], 12160)
        self.assertEqual(data[data["OpType"] == "hcom_allReduce_"]["Count"].tolist()[0], 192)
        self.assertEqual(data[data["OpType"] == "hcom_broadcast_"]["Count"].tolist()[0], 48)
        self.assertEqual(data[data["OpType"] == "hcom_reduceScatter_"]["Count"].tolist()[0], 7472)

    def test_group_name_map(self):
        query = "select * from HcclGroupNameMap"
        data = pd.read_sql(query, self.conn)
        self.assertEqual(len(data), 33)

    def test_per_rank_stats(self):
        query = "select Rank, sum(Count) cnt from HcclPerRankStats group by Rank"
        data = pd.read_sql(query, self.conn)
        for rank in range(16):
            self.assertEqual(data[data["Rank"] == rank]["cnt"].tolist()[0], 1242)

    def test_top_op_stats(self):
        check_data = {
            "hcom_allReduce__606_0_1": 7,
            "hcom_allReduce__058_0_1": 15,
            "hcom_allReduce__184_0_1": 11,
            "hcom_allReduce__286_0_1": 4,
            "hcom_allReduce__053_0_1": 9,
            "hcom_allReduce__408_0_1": 5,
            "hcom_allReduce__865_0_1": 0,
            "hcom_allReduce__618_0_1": 12,
            "hcom_allReduce__532_0_1": 3,
            "hcom_allReduce__809_0_1": 1,
            "hcom_allReduce__444_0_1": 8,
            "hcom_allReduce__740_0_1": 13,
            "hcom_allReduce__273_0_1": 2,
            "hcom_allReduce__349_0_1": 6,
            "hcom_allReduce__558_0_1": 14
        }
        query = "select * from HcclTopOpStats"
        data = pd.read_sql(query, self.conn)
        for op_name, rank in check_data.items():
            self.assertEqual(data[data["OpName"] == op_name]["MinRank"].tolist()[0], rank)
            self.assertEqual(data[data["OpName"] == op_name]["MaxRank"].tolist()[0], rank)
