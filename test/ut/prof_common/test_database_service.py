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

import pandas as pd
from mock import patch, MagicMock

from msprof_analyze.prof_common.constant import Constant
from msprof_analyze.prof_common.database_service import DatabaseService


class TestDatabaseService(unittest.TestCase):

    def setUp(self):
        """设置测试环境"""
        self.db_path = "/path/to/test.db"
        self.step_range = {
            Constant.START_NS: 1000000,
            Constant.END_NS: 2000000
        }
        self.database_service = DatabaseService(self.db_path, self.step_range)

    def test_init_with_step_range(self):
        """测试使用时间范围初始化数据库服务"""
        # 验证初始化后的属性值
        self.assertEqual(self.database_service._db_path, self.db_path)
        self.assertEqual(self.database_service._step_range, self.step_range)
        self.assertEqual(self.database_service._table_info, {})
        self.assertEqual(self.database_service._param, (1000000, 2000000))

    def test_init_without_step_range(self):
        """测试不使用时间范围初始化数据库服务"""
        # 创建没有时间范围的数据库服务
        database_service = DatabaseService(self.db_path, None)

        # 验证初始化后的属性值
        self.assertEqual(database_service._db_path, self.db_path)
        self.assertIsNone(database_service._step_range)
        self.assertEqual(database_service._table_info, {})
        self.assertIsNone(database_service._param)

    def test_add_table_for_query_valid(self):
        """测试添加有效的表和列信息"""
        # 添加表信息
        table_name = "TEST_TABLE"
        columns = ["col1", "col2", "col3"]
        self.database_service.add_table_for_query(table_name, columns)

        # 验证表信息是否正确添加
        self.assertIn(table_name, self.database_service._table_info)
        self.assertEqual(self.database_service._table_info[table_name], columns)

        # 测试不指定列的情况
        table_name2 = "TEST_TABLE2"
        self.database_service.add_table_for_query(table_name2)
        self.assertIn(table_name2, self.database_service._table_info)
        self.assertIsNone(self.database_service._table_info[table_name2])

    @patch('msprof_analyze.prof_common.database_service.logger.error')
    def test_add_table_for_query_invalid(self, mock_error):
        """测试添加无效的表和列信息"""
        # 测试无效的表名类型
        self.database_service.add_table_for_query(123, ["col1", "col2"])
        mock_error.assert_called_once_with("Parameter table_name must be type of string.")

        # 测试无效的列类型
        mock_error.reset_mock()
        self.database_service.add_table_for_query("TEST_TABLE", "not_a_list")
        mock_error.assert_called_once_with("Parameter columns must be type of list.")

    @patch('msprof_analyze.prof_common.database_service.DBManager.create_connect_db')
    def test_query_data_empty_table_info(self, mock_create_connect):
        """测试查询数据时表信息为空的情况"""
        # 确保_table_info为空
        self.database_service._table_info = {}

        # 调用查询方法
        result = self.database_service.query_data()

        # 验证结果和是否调用了数据库连接
        self.assertEqual(result, {})
        mock_create_connect.assert_not_called()

    @patch('msprof_analyze.prof_common.database_service.DBManager.create_connect_db')
    def test_query_data_empty_db_path(self, mock_create_connect):
        """测试查询数据时数据库路径为空的情况"""
        # 设置空的数据库路径
        self.database_service._db_path = ""
        self.database_service.add_table_for_query("TEST_TABLE")

        # 调用查询方法
        result = self.database_service.query_data()

        # 验证结果和是否调用了数据库连接
        self.assertEqual(result, {})
        mock_create_connect.assert_not_called()

    @patch('msprof_analyze.prof_common.database_service.DBManager.destroy_db_connect')
    @patch('pandas.read_sql')
    @patch('msprof_analyze.prof_common.database_service.DBManager.get_table_columns_name')
    @patch('msprof_analyze.prof_common.database_service.DBManager.judge_table_exists')
    @patch('msprof_analyze.prof_common.database_service.DBManager.create_connect_db')
    def test_query_data_successful(self, mock_create_connect, mock_judge_table,
                                   mock_get_columns, mock_read_sql, mock_destroy_connect):
        """测试成功查询数据的情况"""
        # 创建模拟的数据库连接和游标
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_create_connect.return_value = (mock_conn, mock_cursor)

        # 设置表存在和列信息
        mock_judge_table.return_value = True
        mock_get_columns.return_value = ["col1", "col2", "col3"]

        # 设置pandas读取结果
        mock_data = pd.DataFrame({"col1": [1, 2], "col2": [3, 4], "col3": [5, 6]})
        mock_read_sql.return_value = mock_data

        # 添加表信息并调用查询方法
        self.database_service.add_table_for_query("TEST_TABLE", ["col1", "col2"])
        result = self.database_service.query_data()

        # 验证结果
        self.assertIn("TEST_TABLE", result)
        pd.testing.assert_frame_equal(result["TEST_TABLE"], mock_data)

        # 验证调用了数据库连接和销毁方法
        mock_create_connect.assert_called_once_with(self.db_path)
        mock_destroy_connect.assert_called_once_with(mock_conn, mock_cursor)

    @patch('msprof_analyze.prof_common.database_service.logger.warning')
    @patch('msprof_analyze.prof_common.database_service.DBManager.destroy_db_connect')
    @patch('msprof_analyze.prof_common.database_service.DBManager.judge_table_exists')
    @patch('msprof_analyze.prof_common.database_service.DBManager.create_connect_db')
    def test_query_data_table_not_exists(self, mock_create_connect, mock_judge_table,
                                         mock_destroy_connect, mock_warning):
        """测试查询不存在的表的情况"""
        # 创建模拟的数据库连接和游标
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_create_connect.return_value = (mock_conn, mock_cursor)

        # 设置表不存在
        mock_judge_table.return_value = False

        # 添加表信息并调用查询方法
        self.database_service.add_table_for_query("NON_EXISTENT_TABLE")
        result = self.database_service.query_data()

        # 验证结果和警告日志
        self.assertEqual(result, {})

    @patch('msprof_analyze.prof_common.database_service.logger.error')
    @patch('msprof_analyze.prof_common.database_service.DBManager.destroy_db_connect')
    @patch('msprof_analyze.prof_common.database_service.DBManager.get_table_columns_name')
    @patch('msprof_analyze.prof_common.database_service.DBManager.judge_table_exists')
    @patch('msprof_analyze.prof_common.database_service.DBManager.create_connect_db')
    def test_query_data_invalid_columns(self, mock_create_connect, mock_judge_table,
                                        mock_get_columns, mock_destroy_connect, mock_error):
        """测试查询无效列的情况"""
        # 创建模拟的数据库连接和游标
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_create_connect.return_value = (mock_conn, mock_cursor)

        # 设置表存在但列不匹配
        mock_judge_table.return_value = True
        mock_get_columns.return_value = ["col1", "col2"]

        # 添加表信息并调用查询方法（使用不存在的列）
        self.database_service.add_table_for_query("TEST_TABLE", ["non_existent_col"])
        result = self.database_service.query_data()

        # 验证结果和错误日志
        self.assertEqual(result, {})
        expected_error = "The fields to be queried in Table TEST_TABLE are invalid."
        mock_error.assert_called_once_with(expected_error)


if __name__ == '__main__':
    unittest.main()
