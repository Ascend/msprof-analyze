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
from unittest.mock import MagicMock, patch

import pandas as pd

from msprof_analyze.cluster_analyse.cluster_kernels_analysis.cluster_prof_info_analysis import (
    FormDataProcessor,
    ViewInfoManager,
    OpSummaryAnalyzerBase,
    TimeToCsvAnalyzer,
    StatisticalInfoToHtmlAnalyzer,
    DeliverableGenerator,
)
from msprof_analyze.prof_common.path_manager import PathManager


class TestFormDataProcessor(unittest.TestCase):
    @patch('pathlib.Path.rglob')
    def test_init(self, mock_rglob):
        mock_rglob.return_value = [MagicMock()]
        processor = FormDataProcessor('test_path', 'test_form')
        self.assertEqual(processor.form_name, 'test_form')

    def test_get_device_id(self):
        dir_path = 'path/to/device_123'
        result = FormDataProcessor.get_device_id(dir_path)
        self.assertEqual(result, '123')

    def test_get_node_id(self):
        dir_path = 'path/to/node456'
        result = FormDataProcessor.get_node_id(dir_path)
        self.assertEqual(result, 456)

    @patch('pathlib.Path.rglob')
    def test_get_files_with_prefix_recursive(self, mock_rglob):
        mock_rglob.return_value = [MagicMock()]
        result = FormDataProcessor.get_files_with_prefix_recursive('test_path', 'test_str')
        self.assertEqual(len(result), 1)

    @patch('pandas.read_csv')
    @patch.object(PathManager, 'check_file_size')
    @patch.object(PathManager, 'check_input_file_path')
    @patch('pathlib.Path.rglob')
    def test_read_summary_data_without_device_id(self, mock_rglob, mock_check_file, mock_check_size, mock_read_csv):
        mock_rglob.return_value = [MagicMock()]
        mock_read_csv.return_value = pd.DataFrame(
            {
                'Op Name': ['test_op'],
                "Input Shapes": "1",
                "Input Data Types": "Float",
                "Output Shapes": "2",
                'Task Duration(us)': [100],
            }
        )
        processor = FormDataProcessor('test_path', 'test_form')
        result = processor.read_summary_data(['Op Name', 'Task Duration(us)'])
        self.assertEqual(len(result), 0)

    @patch('pandas.read_csv')
    @patch.object(PathManager, 'check_file_size')
    @patch.object(PathManager, 'check_input_file_path')
    @patch('pathlib.Path.rglob')
    def test_get_chip_type(self, mock_rglob, mock_check_file, mock_check_size, mock_read_csv):
        mock_rglob.return_value = [MagicMock()]
        mock_read_csv.return_value = pd.DataFrame(columns=['aiv_time(us)'])
        processor = FormDataProcessor('test_path', 'test_form')
        result = processor.get_chip_type()
        self.assertEqual(result, 'ASCEND_NEW')

    @patch('pathlib.Path.rglob')
    def test_get_rank_num(self, mock_rglob):
        mock_rglob.return_value = [MagicMock(), MagicMock()]
        processor = FormDataProcessor('test_path', 'test_form')
        result = processor.get_rank_num()
        self.assertEqual(result, 2)


class TestViewInfoManager(unittest.TestCase):
    def test_set_op_summary_columns_params(self):
        manager = ViewInfoManager('ASCEND_NEW')
        self.assertIn('TimeToCsvAnalyzer', manager.op_summary_columns_dict['ASCEND_NEW'])

    def test_get_columns_info(self):
        manager = ViewInfoManager('ASCEND_NEW')
        result = manager.get_columns_info('TimeToCsvAnalyzer')
        self.assertIsNotNone(result)


class TestOpSummaryAnalyzerBase(unittest.TestCase):
    @patch.object(PathManager, 'check_path_length')
    @patch.object(PathManager, 'remove_path_safety')
    @patch.object(PathManager, 'check_output_directory_path')
    @patch.object(PathManager, 'make_dir_safety')
    def test_init(self, mock_make_dir, mock_check_output, mock_remove_path, mock_check_length):
        analyzer = OpSummaryAnalyzerBase('ASCEND_NEW', 'TimeToCsvAnalyzer', 'test_dir')
        self.assertEqual(analyzer.chip_type, 'ASCEND_NEW')

    @patch.object(PathManager, 'check_path_length')
    @patch.object(PathManager, 'remove_path_safety')
    @patch.object(PathManager, 'check_output_directory_path')
    @patch.object(PathManager, 'make_dir_safety')
    def test_calculate_view_data(self, mock_make_dir, mock_check_output, mock_remove_path, mock_check_length):
        summary_data = pd.DataFrame(
            {
                'Op Name': ['test_op'],
                "Input Shapes": "1",
                "Input Data Types": "Float",
                "Output Shapes": "2",
                'Task Duration(us)': [100],
                "device_id": 1,
                "node_id": 1,
            }
        )
        analyzer = OpSummaryAnalyzerBase('ASCEND_NEW', 'TimeToCsvAnalyzer', 'test_dir')
        analyzer.columns_to_view = ['Task Duration(us)']
        analyzer.calculate_fun = ['mean']
        analyzer.attrs_to_group = ['Op Name']
        result = analyzer.calculate_view_data(summary_data)
        self.assertEqual(len(result), 1)


class TestTimeToCsvAnalyzer(unittest.TestCase):
    @patch.object(PathManager, 'check_path_length')
    @patch.object(PathManager, 'remove_path_safety')
    @patch.object(PathManager, 'check_output_directory_path')
    @patch.object(PathManager, 'make_dir_safety')
    def test_generate_deliverable(self, mock_make_dir, mock_check_output, mock_remove_path, mock_check_length):
        analyzer = TimeToCsvAnalyzer('ASCEND_NEW', 'test_dir')
        summary_data = pd.DataFrame(
            {
                'Op Name': ['test_op'],
                "Input Shapes": "1",
                "Input Data Types": "Float",
                "Output Shapes": "2",
                'Task Duration(us)': [100],
                "device_id": 1,
                "node_id": 1,
            }
        )
        with patch('pandas.DataFrame.to_csv') as mock_to_csv:
            _ = analyzer.generate_deliverable(summary_data, 1)
            mock_to_csv.assert_called_once()


class TestStatisticalInfoToHtmlAnalyzer(unittest.TestCase):
    @patch.object(PathManager, 'check_path_length')
    @patch.object(PathManager, 'remove_path_safety')
    @patch.object(PathManager, 'check_output_directory_path')
    @patch.object(PathManager, 'make_dir_safety')
    def test_get_cal_num(self, mock_make_dir, mock_check_output, mock_remove_path, mock_check_length):
        analyzer = StatisticalInfoToHtmlAnalyzer('ASCEND_NEW', 5, 'test_dir')
        result = analyzer.get_cal_num(10)
        self.assertEqual(result, 2)
        result = analyzer.get_cal_num(20)
        self.assertEqual(result, 1)


class TestDeliverableGenerator(unittest.TestCase):
    @patch('pathlib.Path.rglob')
    @patch.object(PathManager, 'check_file_size')
    @patch.object(PathManager, 'check_input_file_path')
    @patch.object(PathManager, 'check_output_directory_path')
    @patch('pandas.read_csv')
    def test_init(self, mock_pand_read, mock_check_output, mock_check_file, mock_file_size, mock_rglob):
        mock_rglob.return_value = [MagicMock()]
        params = {'dir': 'test_dir', 'type': 'all', 'top_n': 10}
        with patch.object(PathManager, 'input_path_common_check'):
            generator = DeliverableGenerator(params)
            self.assertEqual(len(generator.analyzers), 2)

    @patch('pathlib.Path.rglob')
    @patch.object(PathManager, 'check_file_size')
    @patch.object(PathManager, 'check_input_file_path')
    @patch.object(PathManager, 'check_output_directory_path')
    @patch('pandas.read_csv')
    def test_run(self, mock_pand_read, mock_check_output, mock_check_file, mock_file_size, mock_rglob):
        mock_rglob.return_value = [MagicMock()]
        params = {'dir': 'test_dir', 'type': 'all', 'top_n': 10}
        with (
            patch.object(PathManager, 'input_path_common_check'),
            patch.object(FormDataProcessor, 'read_summary_data') as mock_read_summary,
            patch.object(TimeToCsvAnalyzer, 'generate_deliverable') as mock_csv_gen,
            patch.object(StatisticalInfoToHtmlAnalyzer, 'generate_deliverable') as mock_html_gen,
        ):
            mock_read_summary.return_value = pd.DataFrame()
            generator = DeliverableGenerator(params)
            generator.run()
            mock_csv_gen.assert_not_called()
            mock_html_gen.assert_not_called()


if __name__ == '__main__':
    unittest.main()
