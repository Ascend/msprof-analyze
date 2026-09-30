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
import unittest
from unittest.mock import patch
import pandas as pd

from msprof_analyze.advisor.common.profiling.op_summary import OpSummaryDB
from msprof_analyze.advisor.dataset.profiling.info_collection import OpInfo


class TestOpSummaryDB(unittest.TestCase):
    def setUp(self):
        self.test_db_path = "test_db.db"
        self.op_summary_db = OpSummaryDB(self.test_db_path)

    def tearDown(self):
        if os.path.exists(self.test_db_path):
            os.remove(self.test_db_path)

    @patch('msprof_analyze.advisor.common.profiling.op_summary.OpSummaryDB.export_compute_task')
    @patch('msprof_analyze.advisor.common.profiling.op_summary.OpSummaryDB._execute_sql')
    @patch('os.path.exists')
    def test_parse_from_file_when_valid_data_then_parse_success(self, mock_exists, mock_execute_sql,
                                                                mock_export_compute):
        # Mock file exists
        mock_exists.return_value = True

        # Mock compute task data
        compute_data = {
            'op_name': ['op1', 'op2'],
            'task_start_time': [0, 1000],
            'task_end_time': [900, 2000],
            'task_duration': [900, 1000],
            'aicore_time': [800, 1950],
            'aiv_time': [0, 0]
        }
        compute_df = pd.DataFrame(compute_data)
        mock_export_compute.return_value = compute_df

        # Mock communication data
        comm_data = {
            'op_name': ['hcom_op'],
            'task_start_time': [3000],
            'task_end_time': [3500],
            'task_duration': [500]
        }
        comm_df = pd.DataFrame(comm_data)

        # Mock comm schedule data
        comm_schedule_data = {
            'op_name': ['mc2_op'],
            'task_start_time': [3500],
            'task_end_time': [3800],
            'task_duration': [300]
        }
        comm_schedule_df = pd.DataFrame(comm_schedule_data)

        # Set up mock returns for _execute_sql
        mock_execute_sql.side_effect = [comm_df, comm_schedule_df]

        # Test parse_from_file
        result = self.op_summary_db.parse_from_file(self.test_db_path)
        self.assertTrue(result)
        self.assertEqual(len(self.op_summary_db.op_list), 4)
        self.assertEqual(self.op_summary_db._total_task_duration, 2.7)

    @patch('msprof_analyze.advisor.common.profiling.op_summary.OpSummaryDB.export_compute_task')
    @patch('msprof_analyze.advisor.common.profiling.op_summary.OpSummaryDB._execute_sql')
    @patch('os.path.exists')
    def test_parse_from_file_when_empty_data_then_return_false(self, mock_exists, mock_execute_sql,
                                                               mock_export_compute):
        # Mock file exists
        mock_exists.return_value = True

        # Mock empty dataframes
        empty_df = pd.DataFrame()
        mock_export_compute.return_value = empty_df
        mock_execute_sql.side_effect = [empty_df, empty_df]

        # Test parse_from_file with empty data
        result = self.op_summary_db.parse_from_file(self.test_db_path)
        self.assertFalse(result)
        self.assertEqual(len(self.op_summary_db.op_list), 0)

    def test_parse_from_file_when_file_not_exist_then_return_false(self):
        # Test parse_from_file when file not exists
        result = self.op_summary_db.parse_from_file(self.test_db_path)
        self.assertFalse(result)
        self.assertEqual(len(self.op_summary_db.op_list), 0)

    @patch('msprof_analyze.advisor.common.profiling.op_summary.OpSummaryDB._execute_sql')
    def test_export_compute_task_when_valid_data_then_return_merged_df(self, mock_execute_sql):
        # Mock basic compute task data
        basic_data = {
            'globalTaskId': [1, 2],
            'op_name': ['op1', 'op2'],
            'task_duration': [1000, 2000]
        }
        basic_df = pd.DataFrame(basic_data)

        # Mock PMU data
        pmu_data = {
            'globalTaskId': [1, 2],
            'name': ['aicore_time', 'aiv_time'],
            'value': [100, 200]
        }
        pmu_df = pd.DataFrame(pmu_data)

        # Set up mock returns
        mock_execute_sql.side_effect = [basic_df, pmu_df]

        # Test export_compute_task
        result = self.op_summary_db.export_compute_task(self.test_db_path)
        self.assertFalse(result.empty)
        self.assertEqual(len(result), 2)
        self.assertEqual(len(result.columns), 5)

    @patch('msprof_analyze.advisor.common.profiling.op_summary.OpSummaryDB._execute_sql')
    def test_export_compute_task_when_pmu_data_missing_then_return_basic_df(self, mock_execute_sql):
        # Mock basic compute task data
        basic_data = {
            'globalTaskId': [1, 2],
            'op_name': ['op1', 'op2'],
            'task_duration': [1000, 2000]
        }
        basic_df = pd.DataFrame(basic_data)

        # Mock empty PMU data
        empty_df = pd.DataFrame()
        mock_execute_sql.side_effect = [basic_df, empty_df]

        # Test export_compute_task
        result = self.op_summary_db.export_compute_task(self.test_db_path)
        self.assertFalse(result.empty)
        self.assertEqual(len(result), 2)
        self.assertEqual(len(result.columns), 3)  # Only basic columns without PMU data

    def test_post_process_when_multiple_dfs_then_return_merged_df(self):
        # Create test dataframes
        compute_data = {
            'op_name': ['op1'],
            'task_start_time': [0],
            'task_end_time': [1000],
            'task_duration': [1000]
        }
        compute_df = pd.DataFrame(compute_data)

        comm_data = {
            'op_name': ['comm1'],
            'task_start_time': [2000],
            'task_end_time': [2500],
            'task_duration': [500]
        }
        comm_df = pd.DataFrame(comm_data)

        # Test post_process
        result = self.op_summary_db.post_process([compute_df, comm_df])
        self.assertFalse(result.empty)
        self.assertEqual(len(result), 2)
        self.assertIn('task_wait_time', result.columns)

    def test_convert_to_op_info_list_when_valid_df_then_create_op_info_list(self):
        # Create test dataframe
        data = {
            'op_name': ['op1', 'op2'],
            'task_duration': [1000, 2000],
            'task_start_time': [0, 1000],
            'task_wait_time': [0, 100]
        }
        df = pd.DataFrame(data)

        # Test convert_to_op_info_list
        self.op_summary_db.convert_to_op_info_list(df)
        self.assertEqual(len(self.op_summary_db.op_list), 2)
        self.assertIsInstance(self.op_summary_db.op_list[0], OpInfo)
