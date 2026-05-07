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

import unittest
from unittest.mock import patch, MagicMock
import os
import shutil
from msprof_analyze.cluster_analyse.analysis.host_info_analysis import (
    HostInfoAnalysis,
    HostInfoScanResult,
    HostInfoScanTask,
)
from msprof_analyze.prof_common.constant import Constant


class TestHostInfoAnalysis(unittest.TestCase):
    test_dir = os.path.join(os.path.dirname(__file__), 'DT_CLUSTER_PREPROCESS')
    
    def setUp(self):
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)
        self.output_path = os.path.join(self.test_dir, "cluster_analysis_output")
        os.makedirs(self.output_path, exist_ok=True)
        
        self.profiling_dir_0 = os.path.join(self.test_dir, 'profiling_0')
        self.profiling_dir_1 = os.path.join(self.test_dir, 'profiling_1')
        os.makedirs(self.profiling_dir_0, exist_ok=True)
        os.makedirs(self.profiling_dir_1, exist_ok=True)
        
        self.param = {
            'data_type': Constant.DB,
            'cluster_analysis_output_path': self.output_path,
            Constant.IS_MSPROF: False,
            Constant.IS_MINDSPORE: False,
            'data_map': {
                '0': self.profiling_dir_0,
                '1': self.profiling_dir_1
            }
        }
        self.analysis = HostInfoAnalysis(self.param)
        
    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def mock_join_function(self, *args):
        filtered_args = [str(arg) for arg in args if arg is not None]
        return os.path.join("/mock", *filtered_args)
    
    @patch('msprof_analyze.cluster_analyse.analysis.host_info_analysis.increase_shared_value')
    @patch('msprof_analyze.cluster_analyse.analysis.host_info_analysis.logger')
    def test_run_when_no_db_data_type_and_with_process_lock(self, mock_logger, mock_increase):
        analysis = HostInfoAnalysis({'data_type': 'json'})
        completed_processes = MagicMock()
        lock = MagicMock()
        
        analysis.run(completed_processes, lock)
        
        mock_increase.assert_called_once_with(completed_processes, lock)
        mock_logger.info.assert_called_with("HostInfoAnalysis completed")
    
    @patch('msprof_analyze.cluster_analyse.analysis.host_info_analysis.increase_shared_value')
    @patch('msprof_analyze.cluster_analyse.analysis.host_info_analysis.logger')
    def test_run_when_no_db_data_type_no_lock(self, mock_logger, mock_increase):
        analysis = HostInfoAnalysis({'data_type': 'json'})
        
        analysis.run()
        
        mock_increase.assert_not_called()
        mock_logger.info.assert_called_with("HostInfoAnalysis completed")
    
    @patch.object(HostInfoAnalysis, 'analyze_host_info')
    @patch.object(HostInfoAnalysis, 'dump_db')
    @patch('msprof_analyze.cluster_analyse.analysis.host_info_analysis.increase_shared_value')
    @patch('msprof_analyze.cluster_analyse.analysis.host_info_analysis.logger')
    def test_run_when_db_data_type_and_with_process_lock(self, mock_logger, mock_increase, mock_dump_db, mock_analyze):
        completed_processes = MagicMock()
        lock = MagicMock()
        
        self.analysis.run(completed_processes, lock)
        mock_analyze.assert_called_once()
        mock_dump_db.assert_called_once()
        mock_increase.assert_called_with(completed_processes, lock)
        mock_logger.info.assert_called_with("HostInfoAnalysis completed")
    
    @patch.object(HostInfoAnalysis, 'analyze_host_info')
    @patch.object(HostInfoAnalysis, 'dump_db')
    @patch('msprof_analyze.cluster_analyse.analysis.host_info_analysis.increase_shared_value')
    @patch('msprof_analyze.cluster_analyse.analysis.host_info_analysis.logger')
    def test_run_when_db_data_type_and_no_lock_mode(self, mock_logger, mock_increase, mock_dump_db, mock_analyze):
        self.analysis.run()
        mock_dump_db.assert_called_once()
        mock_increase.assert_not_called()
        mock_logger.info.assert_called_with("HostInfoAnalysis completed")
    
    @patch('msprof_analyze.cluster_analyse.analysis.host_info_analysis.DBManager')
    @patch('msprof_analyze.cluster_analyse.analysis.host_info_analysis.os.path.join')
    def test_dump_host_info_when_host_info_is_not_empty(self, mock_join, mock_db_manager):
        mock_join.side_effect = self.mock_join_function
        self.analysis.all_rank_host_info = {'host1': 'hostname1', 'host2': 'hostname2'}
        mock_conn = MagicMock()
        mock_db_manager.create_connect_db.return_value = (mock_conn, MagicMock())
        
        self.analysis.dump_host_info('/mock/db', mock_conn)
        mock_db_manager.create_tables.assert_called_once()
        mock_db_manager.executemany_sql.assert_called_once()
    
    @patch('msprof_analyze.cluster_analyse.analysis.host_info_analysis.DBManager')
    @patch('msprof_analyze.cluster_analyse.analysis.host_info_analysis.os.path.join')
    def test_dump_rank_device_map_when_data_is_not_empty(self, mock_join, mock_db_manager):
        mock_join.side_effect = self.mock_join_function
        self.analysis.all_rank_device_info = [['0', 'device0'], ['1', 'device1']]
        mock_conn = MagicMock()
        mock_db_manager.create_connect_db.return_value = (mock_conn, MagicMock())
        
        self.analysis.dump_rank_device_map('/mock/db', mock_conn)
        mock_db_manager.create_tables.assert_called_once()
        mock_db_manager.executemany_sql.assert_called_once()
    
    @patch('msprof_analyze.cluster_analyse.analysis.host_info_analysis.DBManager')
    @patch('msprof_analyze.cluster_analyse.analysis.host_info_analysis.os.path.join')
    def test_dump_rank_device_map_when_data_is_empty(self, mock_join, mock_db_manager):
        mock_join.side_effect = self.mock_join_function
        mock_conn = MagicMock()
        mock_db_manager.create_connect_db.return_value = (mock_conn, MagicMock())
        
        self.analysis.dump_rank_device_map('/mock/db', mock_conn)
        mock_db_manager.create_tables.assert_not_called()
        mock_db_manager.executemany_sql.assert_not_called()
    
    @patch.object(HostInfoAnalysis, '_scan_all_ranks')
    @patch.object(HostInfoAnalysis, '_build_rank_tasks')
    def test_analyze_host_info_when_scan_result_exists(self, mock_build_tasks, mock_scan_all_ranks):
        mock_tasks = [MagicMock()]
        mock_build_tasks.return_value = mock_tasks
        mock_scan_all_ranks.return_value = [
            HostInfoScanResult(
                host_uid='host_uid_0',
                host_name='host_name_0',
                rank_device_info=[['0', 'device0', 'host_uid_0', self.profiling_dir_0]]
            ),
            HostInfoScanResult(
                host_uid='host_uid_1',
                host_name='host_name_1',
                rank_device_info=[['1', 'device1', 'host_uid_1', self.profiling_dir_1]]
            )
        ]

        self.analysis.analyze_host_info()

        mock_build_tasks.assert_called_once()
        mock_scan_all_ranks.assert_called_once_with(mock_tasks)
        self.assertEqual(self.analysis.all_rank_host_info, {
            'host_uid_0': 'host_name_0',
            'host_uid_1': 'host_name_1'
        })
        self.assertEqual(self.analysis.all_rank_device_info, [
            ['0', 'device0', 'host_uid_0', self.profiling_dir_0],
            ['1', 'device1', 'host_uid_1', self.profiling_dir_1]
        ])

    @patch('msprof_analyze.cluster_analyse.analysis.host_info_analysis.DBManager')
    @patch('msprof_analyze.cluster_analyse.analysis.host_info_analysis.MsprofDataPreprocessor')
    def test_scan_single_rank_msprof_when_info_exists(self, mock_msprof, mock_db_manager):
        self.analysis.is_msprof = True
        task = HostInfoScanTask('0', self.profiling_dir_0, os.path.join(self.test_dir, 'test.db'))
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_db_manager.create_connect_db.return_value = (mock_conn, mock_cursor)
        mock_db_manager.judge_table_exists.return_value = True
        mock_db_manager.fetch_all_data.return_value = [['host_uid_0', 'host_name_0']]
        mock_msprof.get_device_id.return_value = 'device0'

        with patch('os.path.exists', return_value=True):
            result = self.analysis._scan_single_rank(task)

        self.assertEqual(result.host_uid, 'host_uid_0')
        self.assertEqual(result.host_name, 'host_name_0')
        self.assertEqual(result.rank_device_info, [['0', 'device0', 'host_uid_0', self.profiling_dir_0]])
        mock_db_manager.create_connect_db.assert_called_once_with(task.db_path)
        mock_db_manager.fetch_all_data.assert_called_once_with(mock_cursor, "select * from HOST_INFO limit 1",
                                                               is_dict=False)
        mock_db_manager.destroy_db_connect.assert_called_once_with(mock_conn, mock_cursor)

    @patch('msprof_analyze.cluster_analyse.analysis.host_info_analysis.DBManager')
    @patch('msprof_analyze.cluster_analyse.analysis.host_info_analysis.logger')
    def test_analyze_host_info_when_no_host_info(self, mock_logger, mock_db_manager):
        task = HostInfoScanTask('0', self.profiling_dir_0, os.path.join(self.test_dir, 'test.db'))
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_db_manager.create_connect_db.return_value = (mock_conn, mock_cursor)
        mock_db_manager.judge_table_exists.return_value = True
        mock_db_manager.fetch_all_data.return_value = []

        with patch('os.path.exists', return_value=True):
            result = self.analysis._scan_single_rank(task)

        self.assertEqual(
            result.warning_items,
            [("HOST_INFO", "0"), ("RANK_DEVICE_MAP", "0")]
        )
        self.analysis._merge_results([result])
        self.assertEqual(self.analysis.all_rank_host_info, {})
        self.assertEqual(self.analysis.all_rank_device_info, [])
        mock_logger.warning.assert_called_once_with(
            "No HOST_INFO data for rank(s): [0] in db file. "
            "No RANK_DEVICE_MAP data for rank(s): [0] in db file."
        )

    @patch('msprof_analyze.cluster_analyse.analysis.host_info_analysis.logger')
    def test_analyze_host_info_when_db_not_exist(self, mock_logger):
        task = HostInfoScanTask('0', self.profiling_dir_0, os.path.join(self.test_dir, 'test.db'))

        with patch('os.path.exists', return_value=False):
            result = self.analysis._scan_single_rank(task)

        self.assertEqual(
            result.warning_items,
            [("HOST_INFO", "0"), ("RANK_DEVICE_MAP", "0")]
        )
        self.analysis._merge_results([result])
        self.assertEqual(self.analysis.all_rank_host_info, {})
        self.assertEqual(self.analysis.all_rank_device_info, [])
        mock_logger.warning.assert_called_once_with(
            "No HOST_INFO data for rank(s): [0] in db file. "
            "No RANK_DEVICE_MAP data for rank(s): [0] in db file."
        )

    @patch('msprof_analyze.cluster_analyse.analysis.host_info_analysis.DBManager')
    @patch('msprof_analyze.cluster_analyse.analysis.host_info_analysis.logger')
    def test_analyze_host_info_when_no_tables(self, mock_logger, mock_db_manager):
        task = HostInfoScanTask('0', self.profiling_dir_0, os.path.join(self.test_dir, 'test.db'))
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_db_manager.create_connect_db.return_value = (mock_conn, mock_cursor)
        mock_db_manager.judge_table_exists.return_value = False

        with patch('os.path.exists', return_value=True):
            result = self.analysis._scan_single_rank(task)

        self.assertEqual(
            result.warning_items,
            [("HOST_INFO", "0"), ("RANK_DEVICE_MAP", "0")]
        )
        self.analysis._merge_results([result])
        self.assertEqual(self.analysis.all_rank_host_info, {})
        self.assertEqual(self.analysis.all_rank_device_info, [])
        mock_logger.warning.assert_called_once_with(
            "No HOST_INFO data for rank(s): [0] in db file. "
            "No RANK_DEVICE_MAP data for rank(s): [0] in db file."
        )

    @patch('msprof_analyze.cluster_analyse.analysis.host_info_analysis.logger')
    def test_merge_results_when_multiple_warning_types_then_log_summary_once(self, mock_logger):
        results = [
            HostInfoScanResult(
                warning_items=[("HOST_INFO", "1"), ("RANK_DEVICE_MAP", "1")]
            ),
            HostInfoScanResult(
                warning_items=[("RANK_DEVICE_MAP", "2")]
            ),
        ]

        self.analysis._merge_results(results)

        mock_logger.warning.assert_called_once_with(
            "No HOST_INFO data for rank(s): [1] in db file. "
            "No RANK_DEVICE_MAP data for rank(s): [1,2] in db file."
        )

    @patch('msprof_analyze.cluster_analyse.analysis.host_info_analysis.logger')
    def test_merge_results_when_warning_and_data_coexist_then_data_is_merged(self, mock_logger):
        results = [
            HostInfoScanResult(
                host_uid='host_uid_0',
                host_name='host_name_0',
                rank_device_info=[['0', 'device0', 'host_uid_0', self.profiling_dir_0]],
                warning_items=[("HOST_INFO", "0")]
            )
        ]

        self.analysis._merge_results(results)

        self.assertEqual(self.analysis.all_rank_host_info, {'host_uid_0': 'host_name_0'})
        self.assertEqual(
            self.analysis.all_rank_device_info,
            [['0', 'device0', 'host_uid_0', self.profiling_dir_0]]
        )
        mock_logger.warning.assert_called_once_with("No HOST_INFO data for rank(s): [0] in db file.")

    @patch('msprof_analyze.cluster_analyse.analysis.host_info_analysis.logger')
    def test_merge_results_when_missing_rank_count_exceeds_limit_then_log_partial_ranks_with_total(self, mock_logger):
        rank_count = HostInfoAnalysis.MAX_WARNING_RANK_DISPLAY + 2
        results = [
            HostInfoScanResult(
                warning_items=[("HOST_INFO", str(rank_id))]
            )
            for rank_id in range(rank_count)
        ]

        self.analysis._merge_results(results)

        displayed_ranks = ",".join(str(rank_id) for rank_id in range(HostInfoAnalysis.MAX_WARNING_RANK_DISPLAY))
        mock_logger.warning.assert_called_once_with(
            f"No HOST_INFO data for rank(s): [{displayed_ranks},...] "
            f"({rank_count} ranks missing in total) in db file."
        )
