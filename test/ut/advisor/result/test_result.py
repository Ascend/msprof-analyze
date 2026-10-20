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
import os
import shutil
from msprof_analyze.advisor.result.result import (
    ResultWriter, SheetRecoder, OptimizeResult, TerminalResult
)
from msprof_analyze.advisor.config.config import Config
from msprof_analyze.prof_common.file_manager import FileManager


class TestResultWriter(unittest.TestCase):
    temp_dir = os.path.join(os.path.dirname(__file__), 'DT_CLUSTER_PREPROCESS')

    def setUp(self):
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)
        self.test_file = os.path.join(self.temp_dir, "test_result.xlsx")
        os.makedirs(self.test_file, exist_ok=True)

    def tearDown(self):
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_add_data_normal_case(self):
        writer = ResultWriter(self.test_file)
        sheet_name = "Test Sheet"
        headers = ["Header1", "Header2", "Header3"]
        data_list = [
            ["Data1", "Data2", "Data3"],
            ["Data4", "Data5", "Data6"]
        ]

        writer.add_data(sheet_name, headers, data_list)
        writer.save()
        self.assertTrue(os.path.exists(self.test_file))

    def test_add_data_with_long_sheet_name(self):
        writer = ResultWriter(self.test_file)
        long_sheet_name = "A" * 50

        writer.add_data(long_sheet_name, ["Header"], [["Data"]])
        writer.save()
        self.assertTrue(os.path.exists(self.test_file))


class TestSheetRecoder(unittest.TestCase):
    def setUp(self):
        self.recorder = SheetRecoder()
        self.recorder.clear()

    def test_add_headers(self):
        sheet_name = "Test Sheet"
        headers = ["Header1", "Header2"]

        self.recorder.add_headers(sheet_name, headers)

        self.assertIn(sheet_name, self.recorder.sheet_data)
        self.assertEqual(self.recorder.sheet_data[sheet_name]["headers"], headers)

    def test_add_data(self):
        sheet_name = "Test Sheet"
        data = ["Data1", "Data2"]

        self.recorder.add_data(sheet_name, data)

        self.assertIn(sheet_name, self.recorder.sheet_data)
        self.assertIn(data, self.recorder.sheet_data[sheet_name]["data"])

    def test_clear(self):
        sheet_name = "Test Sheet"
        self.recorder.add_headers(sheet_name, ["Header"])
        self.recorder.add_data(sheet_name, ["Data"])

        self.recorder.clear()

        self.assertEqual(len(self.recorder.sheet_data), 0)


class TestOptimizeResult(unittest.TestCase):
    temp_dir = os.path.join(os.path.dirname(__file__), 'DT_CLUSTER_PREPROCESS')

    def setUp(self):
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)
        self.test_result_file = os.path.join(self.temp_dir, "analysis_result.xlsx")
        self.test_tune_ops_file = os.path.join(self.temp_dir, "tune_ops.json")
        os.makedirs(self.test_result_file, exist_ok=True)
        os.makedirs(self.test_tune_ops_file, exist_ok=True)


        self.config_patcher = patch.object(Config, 'analysis_result_file', self.test_result_file)
        self.config_patcher.start()

        self.tune_ops_patcher = patch.object(Config, 'tune_ops_file', self.test_tune_ops_file)
        self.tune_ops_patcher.start()

        self.optimize_result = OptimizeResult()
        self.optimize_result.clear()

    def tearDown(self):
        self.config_patcher.stop()
        self.tune_ops_patcher.stop()
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_add_tune_op_list(self):
        tune_op_list = ["op1", "op2", "op3"]
        self.optimize_result.add_tune_op_list(tune_op_list)
        with patch.object(FileManager, 'create_json_file') as mock_create:
            with patch.object(self.optimize_result.result_writer, 'add_data'):
                with patch.object(self.optimize_result.result_writer, 'save'):
                    self.optimize_result.show()
                    mock_create.assert_called_once()

    def test_clear(self):
        self.optimize_result.add_detail("Test Sheet", ["H1"], ["D1"])

        self.optimize_result.clear()

        self.assertEqual(len(self.optimize_result.data), 0)


class TestTerminalResult(unittest.TestCase):
    def setUp(self):
        self.terminal_result = TerminalResult()
        self.terminal_result.result_list = []

    def tearDown(self):
        self.terminal_result.result_list = []

    def test_add_result(self):
        result_str = ["Category", "Description", "Suggestion"]
        self.terminal_result.add(result_str)

        self.assertEqual(len(self.terminal_result.result_list), 1)
        self.assertEqual(self.terminal_result.result_list[0], result_str)

    def test_print_with_results(self):
        self.terminal_result.add(["Category1", "Description1", "Suggestion1"])
        self.terminal_result.add(["Category2", "Description2", "Suggestion2"])

        with patch('click.echo') as mock_echo:
            self.terminal_result.print()
            mock_echo.assert_called()
