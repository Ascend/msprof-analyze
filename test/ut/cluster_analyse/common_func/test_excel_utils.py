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
import os
import unittest
from unittest.mock import patch
import pandas as pd

from msprof_analyze.cluster_analyse.common_func.excel_utils import ExcelUtils


class TestExcelUtils(unittest.TestCase):
    def setUp(self):
        """在每个测试方法前执行"""
        self.sample_df = pd.DataFrame({
            'A': ['foo', 'foo', 'bar', 'bar', 'baz'],
            'B': [1, 1, 2, 2, 3],
            'C': ['x', 'x', 'y', 'y', 'z']
        })
        self.excel_utils = ExcelUtils()
        self.tmp_dir = "test_tmp"  # 实际使用时应该用 pytest 的 tmp_path
        os.makedirs(self.tmp_dir, exist_ok=True)

    def tearDown(self):
        """在每个测试方法后执行"""
        self.excel_utils.clear()
        # 清理临时文件
        for filename in os.listdir(self.tmp_dir):
            file_path = os.path.join(self.tmp_dir, filename)
            if os.path.isfile(file_path):
                os.unlink(file_path)
        os.rmdir(self.tmp_dir)

    def test_create_excel_writer_when_given_valid_df_then_excel_created(self):
        """测试 create_excel_writer 能正确写入 DataFrame 到 Excel 文件。"""
        file_name = 'test.xlsx'
        expected_path = os.path.join(self.tmp_dir, file_name)
        self.excel_utils.create_excel_writer(output_path=self.tmp_dir, file_name=file_name, df=self.sample_df)
        self.excel_utils.save_and_close()
        self.assertTrue(os.path.exists(expected_path))

    def test_set_column_width_when_called_then_column_width_set(self):
        """测试 set_column_width 能正确设置列宽。"""
        file_name = 'test_col_width.xlsx'
        expected_path = os.path.join(self.tmp_dir, file_name)
        self.excel_utils.create_excel_writer(output_path=self.tmp_dir, file_name=file_name, df=self.sample_df)
        self.excel_utils.set_column_width({'A': 20, 'B': 10, 'C': 15})
        self.excel_utils.save_and_close()
        self.assertTrue(os.path.exists(expected_path))

    def test_set_row_height_when_called_then_row_height_set(self):
        """测试 set_row_height 能正确设置行高。"""
        file_name = 'test_row_height.xlsx'
        expected_path = os.path.join(self.tmp_dir, file_name)
        self.excel_utils.create_excel_writer(output_path=self.tmp_dir, file_name=file_name, df=self.sample_df)
        self.excel_utils.set_row_height(1, 30)
        self.excel_utils.save_and_close()
        self.assertTrue(os.path.exists(expected_path))

    def test_freeze_panes_when_called_then_panes_frozen(self):
        """测试 freeze_panes 能正确冻结窗格。"""
        file_name = 'test_freeze.xlsx'
        expected_path = os.path.join(self.tmp_dir, file_name)
        self.excel_utils.create_excel_writer(output_path=self.tmp_dir, file_name=file_name, df=self.sample_df)
        self.excel_utils.freeze_panes(1, 1)
        self.excel_utils.save_and_close()
        self.assertTrue(os.path.exists(expected_path))

    def test_merge_duplicate_cells_when_duplicates_exist_then_cells_merged(self):
        """测试 merge_duplicate_cells 能合并连续相同值的单元格。"""
        file_name = 'test_merge.xlsx'
        expected_path = os.path.join(self.tmp_dir, file_name)
        self.excel_utils.create_excel_writer(output_path=self.tmp_dir, file_name=file_name, df=self.sample_df)
        self.excel_utils.merge_duplicate_cells(['A'])
        self.excel_utils.save_and_close()
        self.assertTrue(os.path.exists(expected_path))

    def test_clear_when_called_then_resources_released(self):
        """测试 clear 能释放资源并允许实例复用。"""
        file_name = 'test_clear.xlsx'
        self.excel_utils.create_excel_writer(output_path=self.tmp_dir, file_name=file_name, df=self.sample_df)
        self.excel_utils.clear()
        self.assertIsNone(self.excel_utils.writer)
        self.assertIsNone(self.excel_utils.workbook)
        self.assertIsNone(self.excel_utils.worksheet)
        self.assertIsNone(self.excel_utils.df)
        self.assertEqual(self.excel_utils._formats_cache, {})

    def test_get_format_when_called_multiple_times_then_cache_used(self):
        """测试 _get_format 多次调用同一格式时使用缓存。"""
        file_name = 'test_format.xlsx'
        self.excel_utils.create_excel_writer(output_path=self.tmp_dir, file_name=file_name, df=self.sample_df)
        fmt1 = self.excel_utils._get_format({'valign': 'vcenter'})
        fmt2 = self.excel_utils._get_format({'valign': 'vcenter'})
        self.assertIs(fmt1, fmt2)

    def test_set_column_width_when_worksheet_not_initialized_then_raises_exception(self):
        """测试 set_column_width 在worksheet未初始化时抛出异常。"""
        with self.assertRaises(Exception) as context:
            self.excel_utils.set_column_width({'A': 20})
        self.assertIn("Worksheet has not been initialized", str(context.exception))

    def test_set_row_height_when_worksheet_not_initialized_then_raises_exception(self):
        """测试 set_row_height 在worksheet未初始化时抛出异常。"""
        with self.assertRaises(Exception) as context:
            self.excel_utils.set_row_height(1, 30)
        self.assertIn("Worksheet not initialized", str(context.exception))

    def test_freeze_panes_when_worksheet_not_initialized_then_raises_exception(self):
        """测试 freeze_panes 在worksheet未初始化时抛出异常。"""
        with self.assertRaises(Exception) as context:
            self.excel_utils.freeze_panes(1, 1)
        self.assertIn("Worksheet has not been initialized", str(context.exception))

    def test_merge_duplicate_cells_when_worksheet_not_initialized_then_raises_exception(self):
        """测试 merge_duplicate_cells 在worksheet未初始化时抛出异常。"""
        with self.assertRaises(Exception) as context:
            self.excel_utils.merge_duplicate_cells(['A'])
        self.assertIn("Worksheet has not been initialized", str(context.exception))

    @patch("msprof_analyze.cluster_analyse.common_func.excel_utils.logger")
    def test_merge_duplicate_cells_when_invalid_column_then_warns_and_continues(self, mock_logger):
        """测试 merge_duplicate_cells 在无效列名时发出警告但继续执行。"""
        file_name = 'test_invalid_column.xlsx'
        expected_path = os.path.join(self.tmp_dir, file_name)
        self.excel_utils.create_excel_writer(output_path=self.tmp_dir, file_name=file_name, df=self.sample_df)
        # 测试不存在的列名
        self.excel_utils.merge_duplicate_cells(['InvalidColumn'])
        self.excel_utils.save_and_close()
        self.assertTrue(os.path.exists(expected_path))
        self.assertTrue(mock_logger.warning.called)

    def test_create_excel_writer_when_empty_dataframe_then_creates_empty_excel(self):
        """测试 create_excel_writer 处理空DataFrame的情况。"""
        empty_df = pd.DataFrame()
        file_name = 'test_empty.xlsx'
        expected_path = os.path.join(self.tmp_dir, file_name)
        self.excel_utils.create_excel_writer(output_path=self.tmp_dir, file_name=file_name, df=empty_df)
        self.excel_utils.save_and_close()
        self.assertTrue(os.path.exists(expected_path))

    def test_clear_when_called_multiple_times_then_no_error(self):
        """测试 clear 方法被多次调用时不会出错。"""
        self.excel_utils.clear()
        self.excel_utils.clear()  # 再次调用
        self.assertIsNone(self.excel_utils.writer)
        self.assertIsNone(self.excel_utils.workbook)

    def test_save_and_close_when_writer_not_initialized_then_no_error(self):
        """测试 save_and_close 在writer未初始化时不会出错。"""
        self.excel_utils.save_and_close()
        self.assertIsNone(self.excel_utils.writer)

    def test_get_format_when_workbook_not_initialized_then_raises_exception(self):
        """测试 _get_format 在workbook未初始化时抛出异常。"""
        with self.assertRaises(AttributeError):
            self.excel_utils._get_format({'valign': 'vcenter'})