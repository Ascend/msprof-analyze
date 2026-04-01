# Copyright (c) 2024-2025, Huawei Technologies Co., Ltd.
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
import unittest
from unittest import TestCase

import pandas as pd

from msprof_analyze.prof_common.path_manager import PathManager
from test.st.utils import execute_cmd
from msprof_analyze.prof_common.db_manager import DBManager
from test.st.utils import ST_DATA_PATH


class TestClusterAnalyseMindsporeDb(TestCase):
    """
       Test cluster analyse MindSpore db
    """
    CLUSTER_PATH = os.path.join(ST_DATA_PATH, "cluster_data_mindspore_db")
    OUTPUT_PATH = os.path.join(os.path.abspath(os.path.dirname(__file__)), "TestClusterAnalyseMindsporeDb")
    COMMAND_SUCCESS = 0
    RUN_TEST = os.path.exists(CLUSTER_PATH)

    @unittest.skipIf(not RUN_TEST, "Skipping this test based on RUN_TEST environment variable")
    def setup_class(self):
        # generate db data
        PathManager.make_dir_safety(self.OUTPUT_PATH)
        cmd = ["msprof-analyze", "cluster", "-d", self.CLUSTER_PATH, "-m", "all",
               "--output_path", self.OUTPUT_PATH, "--force"]
        if execute_cmd(cmd) != self.COMMAND_SUCCESS or not os.path.exists(self.OUTPUT_PATH):
            self.fail("pytorch db cluster analyse task failed.")
        self.db_path = os.path.join(self.OUTPUT_PATH, "cluster_analysis_output", "cluster_analysis.db")
        self.conn, self.cursor = DBManager.create_connect_db(self.db_path)

    @unittest.skipIf(not RUN_TEST, "Skipping this test based on RUN_TEST environment variable")
    def teardown_class(self):
        # Delete db Data
        DBManager.destroy_db_connect(self.conn, self.cursor)
        PathManager.remove_path_safety(self.OUTPUT_PATH)

    @unittest.skipIf(not RUN_TEST, "Skipping this test based on RUN_TEST environment variable")
    def test_host_info_data(self):
        query = "select hostName from HostInfo"
        data = pd.read_sql(query, self.conn)
        self.assertEqual(data["hostName"].tolist(), ["90-90-81-187"])

    @unittest.skipIf(not RUN_TEST, "Skipping this test based on RUN_TEST environment variable")
    def test_rank_device_map_data(self):
        query = "select * from RankDeviceMap"
        data = pd.read_sql(query, self.conn)
        self.assertEqual(len(data), 8)

    @unittest.skipIf(not RUN_TEST, "Skipping this test based on RUN_TEST environment variable")
    def test_step_trace_time_data(self):
        query = "select * from ClusterStepTraceTime"
        data = pd.read_sql(query, self.conn)
        self.assertEqual(len(data), 8)
        flag = 470398.169 in data["computing"].tolist()
        self.assertTrue(flag)

    @unittest.skipIf(not RUN_TEST, "Skipping this test based on RUN_TEST environment variable")
    def test_comm_group_map_data(self):
        query = "select * from CommunicationGroupMapping"
        data = pd.read_sql(query, self.conn)
        self.assertEqual(len(data), 15)
        data = data[data["group_name"] == '11959133092869241673']
        self.assertEqual(data["rank_set"].tolist(), ["(0,1,2,3,4,5,6,7)"])

    @unittest.skipIf(not RUN_TEST, "Skipping this test based on RUN_TEST environment variable")
    def test_comm_matrix_data(self):
        query = "SELECT * FROM ClusterCommunicationMatrix WHERE hccl_op_name = 'Total Op Info' "
        data = pd.read_sql(query, self.conn)
        self.assertEqual(len(data), 71)
        query = "SELECT transport_type, transit_size, transit_time, bandwidth FROM ClusterCommunicationMatrix WHERE " \
                "hccl_op_name='Total Op Info'  and group_name='11262865095472569221' and src_rank=5 and dst_rank=1"
        data = pd.read_sql(query, self.conn)
        self.assertEqual(data.iloc[0].tolist(), ['HCCS', 37.748736, 3.609372109375, 10.458532635621374])

    @unittest.skipIf(not RUN_TEST, "Skipping this test based on RUN_TEST environment variable")
    def test_comm_time_data(self):
        query = "select rank_id, count(0) cnt from ClusterCommunicationTime where hccl_op_name = " \
                "'Total Op Info' group by rank_id"
        data = pd.read_sql(query, self.conn)
        self.assertEqual(len(data), 8)
        self.assertEqual(data["cnt"].tolist(), [4 for _ in range(8)])

    @unittest.skipIf(not RUN_TEST, "Skipping this test based on RUN_TEST environment variable")
    def test_comm_bandwidth_data(self):
        query = "select * from ClusterCommunicationBandwidth where hccl_op_name = 'Total Op Info' and " \
                "group_name='739319275709983152' order by count"
        data = pd.read_sql(query, self.conn)
        self.assertEqual(len(data), 15)
        self.assertEqual(data["count"].tolist(), [0, 0, 0, 0, 18, 24, 24, 24, 120, 120, 120, 387, 387, 387, 387])
