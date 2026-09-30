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
from unittest.mock import patch, MagicMock
import pandas as pd

from msprof_analyze.prof_common.constant import Constant
from msprof_analyze.advisor.dataset.timeline_op_collector.timeline_op_sql import (
    TimelineEventType,
    TimelineEventDBSQL,
    TimelineDBHelper
)


class TestTimelineEventDBSQL(unittest.TestCase):
    def test_get_related_table_when_valid_event_type_then_return_tables(self):
        # Test for FRAMEWORK_API
        tables = TimelineEventDBSQL.get_related_table(TimelineEventType.FRAMEWORK_API)
        self.assertIsInstance(tables, list)
        self.assertEqual(len(tables), 2)
        self.assertEqual(tables, [Constant.TABLE_STRING_IDS, Constant.TABLE_PYTORCH_API])

    def test_get_related_table_when_invalid_event_type_then_return_empty_list(self):
        # Test with invalid event type
        tables = TimelineEventDBSQL.get_related_table("invalid_type")
        self.assertEqual(tables, [])

    def test_get_sql_when_valid_event_type_then_return_sql(self):
        # Test for FRAMEWORK_API
        sql = TimelineEventDBSQL.get_sql(TimelineEventType.FRAMEWORK_API)
        self.assertIsInstance(sql, str)
        self.assertEqual(TimelineEventDBSQL.QUERY_PYTORCH_API_SQL, sql)

    def test_get_sql_when_invalid_event_type_then_return_empty_string(self):
        # Test with invalid event type
        sql = TimelineEventDBSQL.get_sql("invalid_type")
        self.assertEqual(sql, "")


class TestTimelineDBHelper(unittest.TestCase):
    def setUp(self):
        self.test_db_path = "test_ascend_pytorch_profiler.db"
        self.db_helper = TimelineDBHelper(self.test_db_path)

    def tearDown(self):
        if os.path.exists(self.test_db_path):
            os.remove(self.test_db_path)

    def test_is_ascend_pytorch_profiler_db_when_valid_name_then_true(self):
        valid_names = [
            "ascend_pytorch_profiler.db",
            "ascend_pytorch_profiler_123.db"
        ]
        for name in valid_names:
            result = TimelineDBHelper.is_ascend_pytorch_profiler_db(name)
            self.assertTrue(result)

    def test_is_ascend_pytorch_profiler_db_when_invalid_name_then_false(self):
        invalid_names = [
            "other.db",
            "profiler.db",
            "ascend_profiler_mindspore.db"
        ]
        for name in invalid_names:
            result = TimelineDBHelper.is_ascend_pytorch_profiler_db(name)
            self.assertFalse(result)

    @patch('pandas.read_sql')
    def test_query_timeline_event_when_valid_event_type_then_return_dataframe(self, mock_read_sql):
        # Setup
        self.db_helper.init = True
        self.db_helper.is_pta = True
        self.db_helper.conn = MagicMock()
        self.db_helper.curs = MagicMock()
        self.db_helper.check_table_exist = MagicMock(return_value=True)

        expected_df = pd.DataFrame({
            'name': ['test_api'],
            'ts': [1000.0],
            'dur': [500.0],
            'dataset_index': [1]
        })
        mock_read_sql.return_value = expected_df
        result = self.db_helper.query_timeline_event(TimelineEventType.FRAMEWORK_API)

        self.assertIsNotNone(result)
        self.assertIsInstance(result, pd.DataFrame)
        pd.testing.assert_frame_equal(result, expected_df)
        mock_read_sql.assert_called_once_with(TimelineEventDBSQL.QUERY_PYTORCH_API_SQL, self.db_helper.conn)

    def test_query_timeline_event_when_not_initialized_then_return_none(self):
        self.db_helper.init = False
        result = self.db_helper.query_timeline_event(TimelineEventType.FRAMEWORK_API)
        self.assertIsNone(result)

    def test_query_timeline_event_when_not_pta_then_return_none(self):
        self.db_helper.init = True
        self.db_helper.is_pta = False
        result = self.db_helper.query_timeline_event(TimelineEventType.FRAMEWORK_API)
        self.assertIsNone(result)

    @patch('pandas.read_sql')
    def test_query_timeline_event_when_sql_error_then_return_none(self, mock_read_sql):
        self.db_helper.init = True
        self.db_helper.is_pta = True
        self.db_helper.conn = MagicMock()
        self.db_helper.curs = MagicMock()
        self.db_helper.check_table_exist = MagicMock(return_value=True)

        mock_read_sql.side_effect = Exception("SQL Error")
        result = self.db_helper.query_timeline_event(TimelineEventType.FRAMEWORK_API)

        self.assertIsNone(result)
        self.assertIsNone(self.db_helper.event_data_map[TimelineEventType.FRAMEWORK_API])
        mock_read_sql.assert_called_once_with(TimelineEventDBSQL.QUERY_PYTORCH_API_SQL, self.db_helper.conn)

    def test_destroy_db_connection_when_initialized_then_close_connection(self):
        self.db_helper.init = True
        self.db_helper.conn = MagicMock()
        self.db_helper.curs = MagicMock()
        self.db_helper.destroy_db_connection()

        self.assertFalse(self.db_helper.init)
