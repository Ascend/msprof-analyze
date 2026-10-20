# -------------------------------------------------------------------------
# This file is part of the MindStudio project.
# Copyright (c) 2026 Huawei Technologies Co.,Ltd.
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
"""Test cluster analyse pytorch db"""
import os
from unittest import TestCase

import pandas as pd

from test.st.utils import execute_cmd, read_sql, select_count, select_by_query
from msprof_analyze.prof_common.file_manager import FileManager
from msprof_analyze.prof_common.path_manager import PathManager
from test.st.cluster_analyse.cluster_communication_analyzer_bandwidth_db \
    import ClusterCommunicationAnalyzerBandwidthDb
from test.st.cluster_analyse.cluster_communication_analyzer_matrix_db \
    import ClusterCommunicationAnalyzerMatrixDb
from test.st.cluster_analyse.cluster_communication_analyzer_time_db \
    import ClusterCommunicationAnalyzerTime
from test.st.cluster_analyse.cluster_step_trace_time_db import ClusterStepTraceTimeDb
from test.st.utils import ST_DATA_PATH


class TestClusterAnalysePytorchDb(TestCase):
    """
       Test cluster analyse pytorch db
    """
    CLUSTER_PATH = os.path.join(ST_DATA_PATH, "cluster_data_2_db")
    db_path = ""
    STEP_TRACE_TIME_PATH = os.path.join(ST_DATA_PATH, "cluster_data_2_db", "cluster_analysis_output_text",
                                        "cluster_analysis_output", "cluster_step_trace_time.csv")
    COMMUNICATION_MATRIX_PATH = os.path.join(ST_DATA_PATH, "cluster_data_2_db", "cluster_analysis_output_text",
                                             "cluster_analysis_output", "cluster_communication_matrix.json")
    COMMUNICATION_PATH = os.path.join(ST_DATA_PATH, "cluster_data_2_db", "cluster_analysis_output_text",
                                      "cluster_analysis_output", "cluster_communication.json")
    OUTPUT_PATH = os.path.join(os.path.abspath(os.path.dirname(__file__)), "TestClusterAnalysePytorchDb")
    COMMAND_SUCCESS = 0

    def setup_class(self):
        # generate db data
        PathManager.make_dir_safety(self.OUTPUT_PATH)
        cmd = ["msprof-analyze", "cluster", "-d", self.CLUSTER_PATH, "-m", "all",
               "--output_path", self.OUTPUT_PATH, "--force"]
        if execute_cmd(cmd) != self.COMMAND_SUCCESS or not os.path.exists(self.OUTPUT_PATH):
            self.fail("pytorch db cluster analyse task failed.")
        self.db_path = os.path.join(self.OUTPUT_PATH, "cluster_analysis_output", "cluster_analysis.db")

    def teardown_class(self):
        # Delete db Data
        PathManager.remove_path_safety(self.OUTPUT_PATH)

    def test_msprof_analyze_text_db_trace_time_compare(self):
        """
        Test case to compare the cluster step trace time from text file and database.
        """
        df = pd.read_csv(self.STEP_TRACE_TIME_PATH)
        query_count = "SELECT count(*) FROM ClusterStepTraceTime"
        self.assertEqual(len(df), select_count(self.db_path, query_count),
                         "Cluster step trace time count wrong.")
        query = "SELECT * FROM ClusterStepTraceTime where type= 'rank' and [index] = 7"
        db_cluster_step_trace_time = select_by_query(self.db_path, query, ClusterStepTraceTimeDb)
        df = df[df["Index"] == 7]
        text_cluster_step_trace_time = ClusterStepTraceTimeDb(*df.iloc[0])
        self.assertEqual(text_cluster_step_trace_time.type, db_cluster_step_trace_time.type,
                         "Cluster step trace time db vs text 'type' property wrong.")
        self.assertEqual(str(text_cluster_step_trace_time.index), str(db_cluster_step_trace_time.index),
                         "Cluster step trace time db vs text 'index' property wrong.")
        self.assertEqual(round(text_cluster_step_trace_time.computing), round(db_cluster_step_trace_time.computing),
                         "Cluster step trace time db vs text 'computing' property wrong.")
        self.assertEqual(int(text_cluster_step_trace_time.communication_not_overlapped) + 1,
                         round(db_cluster_step_trace_time.communication_not_overlapped),
                         "Cluster step trace time db vs text 'communication_not_overlapped' property wrong.")
        self.assertEqual(round(text_cluster_step_trace_time.overlapped), round(db_cluster_step_trace_time.overlapped),
                         "Cluster step trace time db vs text 'overlapped' property wrong.")
        self.assertEqual(round(text_cluster_step_trace_time.communication),
                         round(db_cluster_step_trace_time.communication),
                         "Cluster step trace time db vs text 'communication' property wrong.")
        self.assertEqual(round(text_cluster_step_trace_time.free), round(db_cluster_step_trace_time.free),
                         "Cluster step trace time db vs text 'free' property wrong.")
        self.assertEqual(round(text_cluster_step_trace_time.stage), round(db_cluster_step_trace_time.stage),
                         "Cluster step trace time db vs text 'stage' property wrong.")
        self.assertEqual(round(text_cluster_step_trace_time.bubble), round(db_cluster_step_trace_time.bubble),
                         "Cluster step trace time db vs text 'bubble' property wrong.")
        self.assertEqual(int(text_cluster_step_trace_time.communication_not_overlapped_and_exclude_receive) + 1,
                         round(db_cluster_step_trace_time.communication_not_overlapped_and_exclude_receive),
                         "Cluster step trace time db vs text 'communication_not_overlapped_and_exclude_receive' "
                         "property wrong.")

    def test_host_info_data(self):
        query = "select hostName from HostInfo"
        data = read_sql(self.db_path, query)
        self.assertEqual(data["hostName"].tolist(), ["n122-120-121"])

    def test_rank_device_map_data(self):
        query = "select * from RankDeviceMap"
        data = read_sql(self.db_path, query)
        self.assertEqual(len(data), 16)

    def test_step_trace_time_data_count(self):
        query = "select * from ClusterStepTraceTime"
        data = read_sql(self.db_path, query)
        self.assertEqual(len(data), 16)
        self.assertIn(14945901.524, data["computing"].tolist())

    def test_comm_group_map_data(self):
        query = "select * from CommunicationGroupMapping"
        data = read_sql(self.db_path, query)
        self.assertEqual(len(data), 33)
        data = data[data["group_name"] == '7519234732706649132']
        self.assertEqual(data["rank_set"].tolist(), ["(0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15)"])

    def test_comm_matrix_total_count(self):
        query = "SELECT * FROM ClusterCommunicationMatrix WHERE hccl_op_name = 'Total Op Info'"
        data = read_sql(self.db_path, query)
        self.assertEqual(len(data), 312)

    def test_comm_bandwidth_total_data(self):
        query = "select * from ClusterCommunicationBandwidth where hccl_op_name = 'Total Op Info' and " \
                "group_name='12703750860003234865' order by count"
        data = read_sql(self.db_path, query)
        self.assertEqual(len(data), 2)
        self.assertEqual(data["count"].tolist(), [2, 36])

    def test_msprof_analyze_text_db_communication_analyzer_matrix_compare(self):
        """
        Test case to compare the cluster communication matrix from text file and database.
        """
        query = ("SELECT * FROM ClusterCommunicationMatrix WHERE hccl_op_name = 'Total Op Info' and src_rank = 7 "
                 "and group_name = '15244899533746605158' and dst_rank = 4 and step = 'step'")
        db_cluster_communication_analyzer_matrix = select_by_query(self.db_path, query,
                                                                   ClusterCommunicationAnalyzerMatrixDb)
        query_count = ("SELECT count(*) FROM ClusterCommunicationMatrix WHERE hccl_op_name = 'Total Op Info' and "
                       "group_name = '15244899533746605158'")
        communication_matrix_json = FileManager.read_json_file(self.COMMUNICATION_MATRIX_PATH)
        self.assertEqual(select_count(self.db_path, query_count),
                         len(communication_matrix_json.get('(4, 5, 6, 7)')
                             .get('step').get('Total Op Info@15244899533746605158')),
                         "Cluster communication matrix db vs text count wrong.")
        text_cluster_communication_matrix = (communication_matrix_json.get('(4, 5, 6, 7)').get('step')
                                             .get('Total Op Info@15244899533746605158').get('7-4'))
        self.assertEqual(text_cluster_communication_matrix.get('Transport Type'),
                         db_cluster_communication_analyzer_matrix.transport_type,
                         "Cluster communication matrix db vs text 'Transport Type' property wrong.")
        self.assertEqual(round(text_cluster_communication_matrix.get('Transit Time(ms)')),
                         round(db_cluster_communication_analyzer_matrix.transit_time),
                         "Cluster communication matrix db vs text 'Transit Time' property wrong.")
        self.assertEqual(round(text_cluster_communication_matrix.get('Transit Size(MB)')),
                         round(db_cluster_communication_analyzer_matrix.transit_size),
                         "Cluster communication matrix db vs text 'Transit Size' property wrong.")
        self.assertEqual(round(text_cluster_communication_matrix.get('Bandwidth(GB/s)')),
                         round(db_cluster_communication_analyzer_matrix.bandwidth),
                         "Cluster communication matrix db vs text 'Bandwidth' property wrong.")

    def test_msprof_analyze_text_db_communication_analyzer_bandwidth_compare(self):
        """
        Test case to compare the cluster bandWidth from text file and database.
        """
        query = ("SELECT * FROM ClusterCommunicationBandwidth WHERE hccl_op_name = 'Total Op Info' and rank_id = 7 "
                 "and group_name = '15244899533746605158' and step = 'step' and band_type = 'HCCS' and "
                 "package_size = '3.372891'")
        db_cluster_communication_analyzer_band_width = select_by_query(self.db_path, query,
                                                                       ClusterCommunicationAnalyzerBandwidthDb)
        query_count = ("SELECT count(*) FROM ClusterCommunicationBandwidth WHERE hccl_op_name = 'Total Op Info' and "
                       "group_name = '15244899533746605158'"
                       "and rank_id = 7 and band_type = 'HCCS'")
        communication_json = FileManager.read_json_file(self.COMMUNICATION_PATH)
        self.assertEqual(select_count(self.db_path, query_count),
                         len(communication_json.get('(4, 5, 6, 7)')
                             .get('step').get('Total Op Info@15244899533746605158')
                             .get('7').get('Communication Bandwidth Info')
                             .get('HCCS').get('Size Distribution')),
                         "Cluster communication bandWidth db vs text count wrong.")
        text_cluster_communication_band_width = (communication_json.get('(4, 5, 6, 7)').get('step')
                                                 .get('Total Op Info@15244899533746605158')
                                                 .get('7').get('Communication Bandwidth Info')
                                                 .get('HCCS'))
        self.assertEqual(round(text_cluster_communication_band_width.get('Transit Time(ms)')),
                         round(db_cluster_communication_analyzer_band_width.transit_time),
                         "Cluster communication bandWidth db vs text 'Transport Time' property wrong.")
        self.assertEqual(round(text_cluster_communication_band_width.get('Transit Size(MB)')),
                         round(db_cluster_communication_analyzer_band_width.transit_size),
                         "Cluster communication bandWidth db vs text 'Transit Size(MB)' property wrong.")
        self.assertEqual(round(text_cluster_communication_band_width.get('Bandwidth(GB/s)')),
                         round(db_cluster_communication_analyzer_band_width.bandwidth),
                         "Cluster communication bandWidth db vs text 'Bandwidth(GB/s)' property wrong.")
        self.assertEqual(round(text_cluster_communication_band_width.get('Size Distribution').get('3.372891')[0]),
                         round(db_cluster_communication_analyzer_band_width.count),
                         "Cluster communication bandWidth db vs text 'count' property wrong.")
        total_duration = text_cluster_communication_band_width.get('Size Distribution').get('3.372891')[1]
        self.assertEqual(f"{round(total_duration, 2):.2f}",
                         f"{db_cluster_communication_analyzer_band_width.total_duration:.2f}",
                         "Cluster communication bandWidth db vs text 'total duration' property wrong.")

    def test_msprof_analyze_text_db_communication_analyzer_time_compare(self):
        """
        Test case to compare the cluster time from text file and database.
        """
        query = ("SELECT * FROM ClusterCommunicationTime WHERE hccl_op_name = 'Total Op Info' and rank_id = 0 "
                 "and group_name = '6902614901354803568' and step = 'step'")
        db_cluster_communication_analyzer_time = select_by_query(self.db_path, query,
                                                                 ClusterCommunicationAnalyzerTime)
        query_count = ("SELECT count(*) FROM ClusterCommunicationTime WHERE hccl_op_name = 'Total Op Info' "
                       "and group_name = '6902614901354803568'")
        communication_json = FileManager.read_json_file(self.COMMUNICATION_PATH)
        self.assertEqual(select_count(self.db_path, query_count),
                         len(communication_json.get('(0, 1, 2, 3)')
                             .get('step').get('Total Op Info@6902614901354803568')),
                         "Cluster communication time db vs text count wrong.")
        text_cluster_communication_analyzer_time = (communication_json.get('(0, 1, 2, 3)').get('step')
                                                    .get('Total Op Info@6902614901354803568')
                                                    .get('0').get('Communication Time Info'))
        self.assertEqual(round(text_cluster_communication_analyzer_time.get('Elapse Time(ms)')),
                         round(db_cluster_communication_analyzer_time.elapsed_time),
                         "Cluster communication time db vs text 'Elapse Time(ms)' property wrong.")
        self.assertEqual(round(text_cluster_communication_analyzer_time.get('Transit Time(ms)')),
                         round(db_cluster_communication_analyzer_time.transit_time),
                         "Cluster communication time db vs text 'Transit Time(ms)' property wrong.")
        self.assertEqual(round(text_cluster_communication_analyzer_time.get('Wait Time(ms)')),
                         round(db_cluster_communication_analyzer_time.wait_time),
                         "Cluster communication time db vs text 'Wait Time(ms)' property wrong.")
        self.assertEqual(round(text_cluster_communication_analyzer_time.get('Synchronization Time(ms)')),
                         round(db_cluster_communication_analyzer_time.synchronization_time),
                         "Cluster communication time db vs text 'Synchronization Time(ms)' property wrong.")
        self.assertEqual(round(text_cluster_communication_analyzer_time.get('Idle Time(ms)')),
                         round(db_cluster_communication_analyzer_time.idle_time),
                         "Cluster communication time db vs text 'Idle Time(ms)' property wrong.")
        self.assertEqual(round(text_cluster_communication_analyzer_time.get('Wait Time Ratio')),
                         round(db_cluster_communication_analyzer_time.wait_time_ratio),
                         "Cluster communication time db vs text 'Wait Time Ratio' property wrong.")
        self.assertEqual(round(text_cluster_communication_analyzer_time.get('Synchronization Time Ratio')),
                         round(db_cluster_communication_analyzer_time.synchronization_time_ratio),
                         "Cluster communication time db vs text 'Synchronization Time Ratio' property wrong.")
