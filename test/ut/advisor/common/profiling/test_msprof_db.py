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
import unittest
from unittest.mock import patch
import pandas as pd
from msprof_analyze.prof_common.constant import Constant

from msprof_analyze.advisor.common.profiling.msprof import MsprofDB
from msprof_analyze.advisor.dataset.profiling.info_collection import TaskInfo


class TestMsprofDB(unittest.TestCase):
    def setUp(self):
        self.test_db_path = "test_db.db"
        self.msprof_db = MsprofDB(self.test_db_path)

    def test_parse_from_file_when_file_not_exists_then_return_false(self):
        """Test parsing when file doesn't exist"""
        result = self.msprof_db.parse_from_file("non_existent.db")
        self.assertFalse(result)

    @patch.object(MsprofDB, '_execute_sql')
    def test_process_communication_tasks_when_valid_data_then_success(self, mock_execute_sql):
        """Test processing communication tasks with valid data"""
        # Mock data for HCCL tasks
        hccl_task_data = pd.DataFrame({
            'name': ['Memcpy', 'Notify_Wait'],
            'ts': [1726054679556862, 1726054679556864],
            'dur': [0.2, 0.4],
            'args': ['{"task type":"Memcpy","stream id":5,"task id":10690,"transport type":"SDMA",'
                     '"link type":"ON_CHIP","size(Byte)":8}',
                     '{"task type":"Notify_Wait","stream id":5,"task id":10690,"transport type":"LOCAL",'
                     '"link type":"INVALID_TYPE","size(Byte)":0}']
        })

        # Mock data for HCCL ops
        hccl_op_data = pd.DataFrame({
            'name': ['hcom_allreduce', 'hcom_broadcast'],
            'ts': [1726054679556861, 1726054679556890],
            'dur': [1.5, 0.3]
        })

        def mock_execute_sql_side_effect(*args, **kwargs):
            if args[1] == MsprofDB.HCCL_TASK_SQL:
                return hccl_task_data
            elif args[1] == MsprofDB.HCCL_OP_SQL:
                return hccl_op_data
            return pd.DataFrame()

        mock_execute_sql.side_effect = mock_execute_sql_side_effect

        self.msprof_db.process_communication_tasks(self.test_db_path)

        # Verify HCCL tasks
        self.assertEqual(len(self.msprof_db.hccl_tasks), 4)  # 2 tasks + 2 ops
        self.assertIsInstance(self.msprof_db.hccl_tasks[0], TaskInfo)
        self.assertEqual(self.msprof_db.hccl_tasks[0].name, 'hcom_allreduce')
        self.assertEqual(self.msprof_db.hccl_tasks[2].name, 'Notify_Wait')

        # Verify SQL calls
        mock_execute_sql.assert_any_call(self.test_db_path, MsprofDB.HCCL_TASK_SQL,
                                         [Constant.TABLE_COMMUNICATION_TASK_INFO])
        mock_execute_sql.assert_any_call(self.test_db_path, MsprofDB.HCCL_OP_SQL, [Constant.TABLE_COMMUNICATION_OP])
        self.assertEqual(mock_execute_sql.call_count, 2)

    @patch.object(MsprofDB, '_execute_sql')
    def test_process_node_tasks_when_valid_data_then_success(self, mock_execute_sql):
        """Test processing node tasks with valid data"""
        # Mock data for node tasks
        mock_data = pd.DataFrame({
            'name': ['node1', 'node2'],
            'ts': [1000.0, 2000.0],
            'dur': [100.0, 200.0],
            'args': ['{"item_id": "prev1"}', '{"item_id": "prev2"}']
        })
        mock_execute_sql.return_value = mock_data

        self.msprof_db.process_node_tasks(self.test_db_path)

        self.assertEqual(len(self.msprof_db.tasks), 2)
        self.assertIsInstance(self.msprof_db.tasks[0], TaskInfo)
        self.assertEqual(self.msprof_db.tasks[0].name, 'node1')
        mock_execute_sql.assert_called_with(self.test_db_path, self.msprof_db.NODE_INFO_SQL, None)

    @patch.object(MsprofDB, '_execute_sql')
    def test_process_task_data_when_empty_dataframe_then_no_tasks_added(self, mock_execute_sql):
        """Test processing tasks when SQL query returns empty dataframe"""
        mock_execute_sql.return_value = pd.DataFrame()

        self.msprof_db._process_task_data(self.test_db_path, MsprofDB.HCCL_OP_SQL, self.msprof_db.tasks)
        self.assertEqual(len(self.msprof_db.tasks), 0)
        mock_execute_sql.assert_called_with(self.test_db_path, MsprofDB.HCCL_OP_SQL, None)
