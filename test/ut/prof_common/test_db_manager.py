# Copyright (c) 2025, Huawei Technologies Co., Ltd. All rights reserved.
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
import sqlite3
import unittest
from unittest.mock import patch, MagicMock

from msprof_analyze.cluster_analyse.common_func.empty_class import EmptyClass
from msprof_analyze.prof_common.db_manager import DBManager, CustomizedDictFactory
from msprof_analyze.prof_common.logger import get_logger

logger = get_logger()


class TestDBManager(unittest.TestCase):
    def setUp(self):
        # 创建临时文件用于测试
        self.temp_dir = os.path.join(os.path.dirname(__file__), "DT_DBManager")
        os.makedirs(self.temp_dir)
        self.temp_db_path = os.path.join(self.temp_dir, "test.db")

    def tearDown(self):
        # 清理临时文件
        if os.path.exists(self.temp_db_path):
            os.remove(self.temp_db_path)
        if os.path.exists(self.temp_dir):
            os.rmdir(self.temp_dir)

    @patch('msprof_analyze.prof_common.db_manager.check_db_path_valid')
    @patch('sqlite3.connect')
    def test_create_connect_db_success(self, mock_connect, mock_check_path):
        # 测试创建数据库连接成功的情况
        mock_check_path.return_value = True
        mock_conn = MagicMock(spec=sqlite3.Connection)
        mock_cursor = MagicMock(spec=sqlite3.Cursor)
        mock_conn.cursor.return_value = mock_cursor
        mock_connect.return_value = mock_conn

        conn, curs = DBManager.create_connect_db(self.temp_db_path)
        mock_check_path.assert_called_once_with(self.temp_db_path)
        mock_connect.assert_called_once_with(self.temp_db_path)
        mock_conn.cursor.assert_called_once()
        self.assertEqual(conn, mock_conn)
        self.assertEqual(curs, mock_cursor)

    @patch('msprof_analyze.prof_common.db_manager.check_db_path_valid')
    def test_create_connect_db_invalid_path(self, mock_check_path):
        # 测试无效路径的情况
        mock_check_path.return_value = False
        conn, curs = DBManager.create_connect_db("invalid/path.db")
        mock_check_path.assert_called_once_with("invalid/path.db")
        self.assertIsInstance(conn, EmptyClass)
        self.assertIsInstance(curs, EmptyClass)

    @patch('msprof_analyze.prof_common.db_manager.check_db_path_valid')
    @patch('sqlite3.connect')
    def test_create_connect_db_sqlite_error(self, mock_connect, mock_check_path):
        # 测试SQLite错误的情况
        mock_check_path.return_value = True
        mock_connect.side_effect = sqlite3.Error("SQLite error")

        conn, curs = DBManager.create_connect_db(self.temp_db_path)
        self.assertIsInstance(conn, EmptyClass)
        self.assertIsInstance(curs, EmptyClass)

    def test_judge_table_exists(self):
        # 测试表存在检查
        mock_cursor = MagicMock(spec=sqlite3.Cursor)
        mock_cursor.fetchone.return_value = (1,)

        result = DBManager.judge_table_exists(mock_cursor, "test_table")
        mock_cursor.execute.assert_called_once_with(
            "select count(*) from sqlite_master where type='table' and name=?", ("test_table",)
        )
        self.assertEqual(result, 1)

    def test_judge_table_exists_not_exists(self):
        # 测试表不存在的情况
        mock_cursor = MagicMock(spec=sqlite3.Cursor)
        mock_cursor.fetchone.return_value = (0,)

        result = DBManager.judge_table_exists(mock_cursor, "non_existent_table")
        self.assertEqual(result, 0)

    def test_judge_table_exists_invalid_cursor(self):
        # 测试无效游标
        result = DBManager.judge_table_exists("invalid_cursor", "test_table")
        self.assertFalse(result)

    def test_judge_table_exists_sql_error(self):
        # 测试SQL错误
        mock_cursor = MagicMock(spec=sqlite3.Cursor)
        mock_cursor.execute.side_effect = sqlite3.Error("SQL error")

        result = DBManager.judge_table_exists(mock_cursor, "test_table")
        self.assertFalse(result)

    def test_sql_generate_table_invalid_map(self):
        # 测试无效表映射
        result = DBManager.sql_generate_table("invalid_table_map")
        self.assertEqual(result, "")

    @patch('msprof_analyze.cluster_analyse.common_func.tables_config.TablesConfig.DATA', {})
    def test_sql_generate_table_empty_data(self):
        # 测试空数据表配置
        result = DBManager.sql_generate_table("testTableMap")
        self.assertEqual(result, "")

    def test_execute_sql_success(self):
        # 测试执行SQL成功
        mock_conn = MagicMock(spec=sqlite3.Connection)
        mock_cursor = MagicMock(spec=sqlite3.Cursor)
        mock_conn.cursor.return_value = mock_cursor

        result = DBManager.execute_sql(mock_conn, "SELECT * FROM test")
        mock_conn.cursor.assert_called_once()
        mock_cursor.execute.assert_called_once_with("SELECT * FROM test")
        mock_conn.commit.assert_called_once()
        self.assertTrue(result)

    def test_execute_sql_with_params(self):
        # 测试带参数执行SQL
        mock_conn = MagicMock(spec=sqlite3.Connection)
        mock_cursor = MagicMock(spec=sqlite3.Cursor)
        mock_conn.cursor.return_value = mock_cursor
        params = (1, "test")

        result = DBManager.execute_sql(mock_conn, "SELECT * FROM test WHERE id=? AND name=?", params)
        mock_cursor.execute.assert_called_once_with("SELECT * FROM test WHERE id=? AND name=?", params)
        self.assertTrue(result)

    def test_execute_sql_invalid_conn(self):
        # 测试无效连接
        result = DBManager.execute_sql("invalid_conn", "SELECT * FROM test")
        self.assertFalse(result)

    def test_executemany_sql_success(self):
        # 测试批量执行SQL成功
        mock_conn = MagicMock(spec=sqlite3.Connection)
        mock_cursor = MagicMock(spec=sqlite3.Cursor)
        mock_conn.cursor.return_value = mock_cursor
        params = [(1, "test1"), (2, "test2")]

        result = DBManager.executemany_sql(mock_conn, "INSERT INTO test VALUES (?, ?)", params)
        mock_conn.cursor.assert_called_once()
        mock_cursor.executemany.assert_called_once_with("INSERT INTO test VALUES (?, ?)", params)
        mock_conn.commit.assert_called_once()
        self.assertTrue(result)

    def test_executemany_sql_invalid_conn(self):
        # 测试无效连接
        result = DBManager.executemany_sql("invalid_conn", "INSERT INTO test VALUES (?, ?)", [(1, "test")])
        self.assertFalse(result)

    def test_executemany_sql_error(self):
        # 测试SQL执行错误
        mock_conn = MagicMock(spec=sqlite3.Connection)
        mock_cursor = MagicMock(spec=sqlite3.Cursor)
        mock_conn.cursor.return_value = mock_cursor
        mock_cursor.executemany.side_effect = sqlite3.Error("SQL error")

        result = DBManager.executemany_sql(mock_conn, "INSERT INTO test VALUES (?, ?)", [(1, "test")])
        self.assertFalse(result)

    @patch('msprof_analyze.prof_common.db_manager.check_db_path_valid')
    @patch('msprof_analyze.prof_common.db_manager.DBManager.create_connect_db')
    @patch('msprof_analyze.prof_common.db_manager.DBManager.judge_table_exists')
    @patch('msprof_analyze.prof_common.db_manager.DBManager.destroy_db_connect')
    def test_check_tables_in_db(self, mock_destroy, mock_judge, mock_create, mock_check_path):
        # 测试检查数据库中的表
        mock_check_path.return_value = True
        mock_conn = MagicMock(spec=sqlite3.Connection)
        mock_cursor = MagicMock(spec=sqlite3.Cursor)
        mock_create.return_value = (mock_conn, mock_cursor)
        mock_judge.return_value = True

        result = DBManager.check_tables_in_db(self.temp_db_path, "table1", "table2")
        mock_check_path.assert_called_once_with(self.temp_db_path)
        mock_create.assert_called_once_with(self.temp_db_path)
        self.assertEqual(mock_judge.call_count, 2)
        mock_destroy.assert_called_once_with(mock_conn, mock_cursor)
        self.assertTrue(result)

    @patch('msprof_analyze.prof_common.db_manager.check_db_path_valid')
    def test_check_tables_in_db_invalid_path(self, mock_check_path):
        # 测试无效路径
        mock_check_path.return_value = False
        result = DBManager.check_tables_in_db("invalid/path.db", "table1")
        self.assertFalse(result)

    @patch('msprof_analyze.prof_common.db_manager.check_db_path_valid')
    @patch('msprof_analyze.prof_common.db_manager.DBManager.create_connect_db')
    def test_check_tables_in_db_invalid_connection(self, mock_create, mock_check_path):
        # 测试无效连接
        mock_check_path.return_value = True
        mock_create.return_value = (EmptyClass("empty conn"), EmptyClass("empty curs"))

        result = DBManager.check_tables_in_db(self.temp_db_path, "table1")

        self.assertFalse(result)

    @patch('msprof_analyze.prof_common.db_manager.check_db_path_valid')
    @patch('msprof_analyze.prof_common.db_manager.DBManager.create_connect_db')
    @patch('msprof_analyze.prof_common.db_manager.DBManager.judge_table_exists')
    @patch('msprof_analyze.prof_common.db_manager.DBManager.destroy_db_connect')
    def test_check_tables_in_db_table_not_exists(self, mock_destroy, mock_judge, mock_create, mock_check_path):
        # 测试表不存在
        mock_check_path.return_value = True
        mock_conn = MagicMock(spec=sqlite3.Connection)
        mock_cursor = MagicMock(spec=sqlite3.Cursor)
        mock_create.return_value = (mock_conn, mock_cursor)
        mock_judge.side_effect = [True, False]

        result = DBManager.check_tables_in_db(self.temp_db_path, "table1", "table2")
        self.assertFalse(result)

    @patch('msprof_analyze.prof_common.db_manager.DBManager.create_connect_db')
    @patch('msprof_analyze.prof_common.db_manager.DBManager.judge_table_exists')
    @patch('msprof_analyze.prof_common.db_manager.DBManager.execute_sql')
    @patch('msprof_analyze.prof_common.db_manager.DBManager.sql_generate_table')
    @patch('msprof_analyze.prof_common.db_manager.DBManager.destroy_db_connect')
    def test_create_tables(self, mock_destroy, mock_generate, mock_execute, mock_judge, mock_create):
        # 测试创建表
        mock_conn = MagicMock(spec=sqlite3.Connection)
        mock_cursor = MagicMock(spec=sqlite3.Cursor)
        mock_create.return_value = (mock_conn, mock_cursor)
        mock_judge.return_value = True
        mock_generate.return_value = "(id INTEGER, name TEXT)"

        DBManager.create_tables(self.temp_db_path, "table1")
        mock_create.assert_called_once_with(self.temp_db_path)
        mock_judge.assert_called_once_with(mock_cursor, "table1")
        mock_execute.assert_any_call(mock_conn, "drop table table1")
        mock_generate.assert_called_once_with("table1Map")
        mock_execute.assert_any_call(mock_conn, "CREATE TABLE IF NOT EXISTS table1(id INTEGER, name TEXT)")
        mock_destroy.assert_called_once_with(mock_conn, mock_cursor)

    @patch('msprof_analyze.prof_common.db_manager.DBManager.create_connect_db')
    def test_create_tables_invalid_connection(self, mock_create):
        # 测试无效连接
        mock_create.return_value = (EmptyClass("empty conn"), EmptyClass("empty curs"))
        DBManager.create_tables(self.temp_db_path, "table1")
        mock_create.assert_called_once_with(self.temp_db_path)

    @patch('msprof_analyze.prof_common.db_manager.DBManager.create_connect_db')
    @patch('msprof_analyze.prof_common.db_manager.DBManager.judge_table_exists')
    @patch('msprof_analyze.prof_common.db_manager.DBManager.destroy_db_connect')
    def test_get_table_column_count(self, mock_destroy, mock_judge, mock_create):
        # 测试获取表列数
        mock_conn = MagicMock(spec=sqlite3.Connection)
        mock_cursor = MagicMock(spec=sqlite3.Cursor)
        mock_create.return_value = (mock_conn, mock_cursor)
        mock_cursor.fetchall.return_value = [(0, "id", "INTEGER", 0, None, 1), (1, "name", "TEXT", 0, None, 0)]

        result = DBManager.get_table_column_count(self.temp_db_path, "table1")
        mock_cursor.execute.assert_called_once_with("PRAGMA table_info(table1)")
        mock_destroy.assert_called_once_with(mock_conn, mock_cursor)
        self.assertEqual(result, 2)

    @patch('msprof_analyze.prof_common.db_manager.DBManager.create_connect_db')
    def test_get_table_column_count_invalid_connection(self, mock_create):
        # 测试无效连接
        mock_create.return_value = (EmptyClass("empty conn"), EmptyClass("empty curs"))
        result = DBManager.get_table_column_count(self.temp_db_path, "table1")
        self.assertEqual(result, 0)

    @patch('msprof_analyze.prof_common.db_manager.logger.error')
    def test_get_table_column_count_sql_error(self, mock_logger_error):
        # 测试SQL错误
        mock_cursor = MagicMock(spec=sqlite3.Cursor)
        mock_cursor.execute.side_effect = sqlite3.Error("SQL error")

        result = DBManager.get_table_columns_name(mock_cursor, "table1")
        mock_logger_error.assert_called_once()
        self.assertEqual(result, [])

    @patch('msprof_analyze.prof_common.db_manager.DBManager.FETCH_SIZE', 3)
    @patch('msprof_analyze.prof_common.db_manager.DBManager.MAX_ROW_COUNT', 7)
    @patch('msprof_analyze.prof_common.db_manager.logger.warning')
    def test_fetch_all_data(self, mock_logger_warning):
        # 测试获取所有数据
        mock_cursor = MagicMock(spec=sqlite3.Cursor)
        mock_description = [("id",), ("name",)]
        mock_res = MagicMock()
        mock_res.description = mock_description
        mock_cursor.execute.return_value = mock_res
        mock_cursor.fetchmany.side_effect = [
            [(1, "test1"), (2, "test2"), (3, "test3")],
            [(4, "test4"), (5, "test5"), (6, "test6")],
            [(7, "test7"), (8, "test7")],
        ]

        result = DBManager.fetch_all_data(mock_cursor, "SELECT * FROM test")
        mock_cursor.execute.assert_called_once_with("SELECT * FROM test")
        self.assertEqual(mock_cursor.fetchmany.call_count, 3)
        self.assertEqual(len(result), 8)
        mock_logger_warning.assert_called_once_with("The records count in the table exceeds the limit!")

    def test_fetch_all_data_with_params(self):
        # 测试带参数获取数据
        mock_cursor = MagicMock(spec=sqlite3.Cursor)
        mock_description = [("id",), ("name",)]
        mock_res = MagicMock()
        mock_res.description = mock_description
        mock_cursor.execute.return_value = mock_res
        mock_cursor.fetchmany.return_value = [(1, "test1")]
        params = (1,)

        _ = DBManager.fetch_all_data(mock_cursor, "SELECT * FROM test WHERE id=?", params)
        mock_cursor.execute.assert_called_once_with("SELECT * FROM test WHERE id=?", params)

    def test_fetch_all_data_invalid_cursor(self):
        # 测试无效游标
        result = DBManager.fetch_all_data("invalid_cursor", "SELECT * FROM test")
        self.assertEqual(result, [])

    @patch('msprof_analyze.prof_common.db_manager.logger.error')
    def test_fetch_all_data_sql_error(self, mock_logger_error):
        # 测试SQL错误
        mock_cursor = MagicMock(spec=sqlite3.Cursor)
        mock_cursor.execute.side_effect = sqlite3.Error("SQL error")

        result = DBManager.fetch_all_data(mock_cursor, "SELECT * FROM test")
        mock_logger_error.assert_called_once()
        self.assertEqual(result, [])

    def test_fetch_all_data_not_dict(self):
        # 测试不以字典形式获取数据
        mock_cursor = MagicMock(spec=sqlite3.Cursor)
        mock_res = MagicMock()
        mock_res.description = None
        mock_cursor.execute.return_value = mock_res
        mock_cursor.fetchmany.return_value = [(1, "test1")]

        result = DBManager.fetch_all_data(mock_cursor, "SELECT * FROM test", is_dict=False)
        self.assertEqual(result, [(1, "test1")])

    @patch('msprof_analyze.prof_common.db_manager.DBManager.INSERT_SIZE', 2)
    @patch('msprof_analyze.prof_common.db_manager.DBManager.executemany_sql')
    def test_insert_data_into_table(self, mock_executemany):
        # 测试插入数据到表
        mock_conn = MagicMock(spec=sqlite3.Connection)
        mock_executemany.return_value = True
        data = [(1, "test1"), (2, "test2"), (3, "test3")]

        DBManager.insert_data_into_table(mock_conn, "table1", data)
        self.assertEqual(mock_executemany.call_count, 2)
        mock_executemany.assert_any_call(mock_conn, "insert into table1 values (?, ?)", [(1, "test1"), (2, "test2")])
        mock_executemany.assert_any_call(mock_conn, "insert into table1 values (?, ?)", [(3, "test3")])

    @patch('msprof_analyze.prof_common.db_manager.DBManager.executemany_sql')
    def test_insert_data_into_table_empty_data(self, mock_executemany):
        # 测试插入空数据
        mock_conn = MagicMock(spec=sqlite3.Connection)
        DBManager.insert_data_into_table(mock_conn, "table1", [])
        mock_executemany.assert_not_called()

    @patch('msprof_analyze.prof_common.db_manager.DBManager.executemany_sql')
    def test_insert_data_into_table_error(self, mock_executemany):
        # 测试插入数据错误
        mock_conn = MagicMock(spec=sqlite3.Connection)
        mock_executemany.return_value = False
        data = [(1, "test1")]

        with self.assertRaises(RuntimeError):
            DBManager.insert_data_into_table(mock_conn, "table1", data)

    @patch('msprof_analyze.prof_common.db_manager.DBManager.create_connect_db')
    @patch('msprof_analyze.prof_common.db_manager.DBManager.insert_data_into_table')
    @patch('msprof_analyze.prof_common.db_manager.DBManager.destroy_db_connect')
    def test_insert_data_into_db(self, mock_destroy, mock_insert_table, mock_create):
        # 测试插入数据到数据库
        mock_conn = MagicMock(spec=sqlite3.Connection)
        mock_cursor = MagicMock(spec=sqlite3.Cursor)
        mock_create.return_value = (mock_conn, mock_cursor)
        data = [(1, "test1")]

        DBManager.insert_data_into_db(self.temp_db_path, "table1", data)

        mock_create.assert_called_once_with(self.temp_db_path)
        mock_insert_table.assert_called_once_with(mock_conn, "table1", data)
        mock_destroy.assert_called_once_with(mock_conn, mock_cursor)

    @patch('msprof_analyze.prof_common.db_manager.DBManager.create_connect_db')
    @patch('msprof_analyze.prof_common.db_manager.logger.warning')
    def test_insert_data_into_db_invalid_connection(self, mock_logger_warning, mock_create):
        # 测试无效连接
        mock_create.return_value = (EmptyClass("empty conn"), EmptyClass("empty curs"))
        data = [(1, "test1")]

        DBManager.insert_data_into_db(self.temp_db_path, "table1", data)
        mock_logger_warning.assert_called_once_with("Failed to connect to db file: %s", self.temp_db_path)

    def test_check_columns_exist(self):
        # 测试检查列存在
        mock_cursor = MagicMock(spec=sqlite3.Cursor)
        mock_cursor.fetchall.return_value = [
            (0, "id", "INTEGER", 0, None, 1),
            (1, "name", "TEXT", 0, None, 0),
            (2, "age", "INTEGER", 0, None, 0),
        ]

        result = DBManager.check_columns_exist(mock_cursor, "table1", {"id", "name", "email"})

        mock_cursor.execute.assert_called_once_with("PRAGMA table_info(table1)")
        self.assertEqual(result, {"id", "name"})

    def test_check_columns_exist_invalid_cursor(self):
        # 测试无效游标
        result = DBManager.check_columns_exist("invalid_cursor", "table1", {"id"})
        self.assertIsNone(result)

    @patch('msprof_analyze.prof_common.db_manager.logger.error')
    def test_check_columns_exist_sql_error(self, mock_logger_error):
        # 测试SQL错误
        mock_cursor = MagicMock(spec=sqlite3.Cursor)
        mock_cursor.execute.side_effect = sqlite3.Error("SQL error")

        result = DBManager.check_columns_exist(mock_cursor, "table1", {"id"})
        mock_logger_error.assert_called_once()
        self.assertIsNone(result)


class TestCustomizedDictFactory(unittest.TestCase):
    def test_generate_dict_from_db(self):
        # 测试从数据库结果生成字典
        data_result = [(1, "test1"), (2, "test2")]
        description = [("id",), ("name",)]

        result = CustomizedDictFactory.generate_dict_from_db(data_result, description)
        expected = [{"id": 1, "name": "test1"}, {"id": 2, "name": "test2"}]
        self.assertEqual(result, expected)

    def test_generate_dict_from_db_empty(self):
        # 测试空结果
        data_result = []
        description = [("id",), ("name",)]

        result = CustomizedDictFactory.generate_dict_from_db(data_result, description)
        self.assertEqual(result, [])

    def test_generate_dict_from_db_single_row(self):
        # 测试单行结果
        data_result = [(1, "test1")]
        description = [("id",), ("name",)]

        result = CustomizedDictFactory.generate_dict_from_db(data_result, description)
        expected = [{"id": 1, "name": "test1"}]
        self.assertEqual(result, expected)


if __name__ == "__main__":
    unittest.main()
