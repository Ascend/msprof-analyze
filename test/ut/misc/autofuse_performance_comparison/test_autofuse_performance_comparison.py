# Copyright (c) 2026, Huawei Technologies Co., Ltd.
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
import pandas as pd
from misc.autofuse_performance_comparison.autofuse_core.autofuse_performance_comparison import ComparisonGenerator


class TestComparisonGenerator(unittest.TestCase):
    expected_result = pd.DataFrame({
        ComparisonGenerator.COL_NAME: ['autofuse_pointwise_0_Abs_Add', 'autofuse_pointwise_0_Abs_Mul'],
        "Duration(us)_disabled": [100, 200],
        "aic_scalar_time(us)_disabled": [10, 20],
        "aic_mte2_time(us)_disabled": [5, 10],
        "aiv_scalar_time(us)_disabled": [2, 4],
        "aiv_vec_time(us)_disabled": [8, 16],
        "aiv_mte2_time(us)_disabled": [3, 6],
        "aiv_mte3_time(us)_disabled": [1, 2],
        "Duration(us)_enabled": [80, 180],
        "aic_scalar_time(us)_enabled": [8, 18],
        "aic_mte2_time(us)_enabled": [4, 9],
        "aiv_scalar_time(us)_enabled": [1, 3],
        "aiv_vec_time(us)_enabled": [7, 15],
        "aiv_mte2_time(us)_enabled": [2, 5],
        "aiv_mte3_time(us)_enabled": [0, 1],
        ComparisonGenerator.COL_DURATION_DIFF_RATIO: [0.8, 0.9]
    })

    def setUp(self):
        self.mock_params = MagicMock()
        self.mock_params.whole_graph = "/path/to/graph"
        self.mock_params.subgraph_dir = "/path/to/subgraph"
        self.mock_params.dump_path = "/path/to/dump"
        self.mock_params.output_path = "/path/to/output"

    @patch('misc.autofuse_performance_comparison.autofuse_core.autofuse_performance_comparison.PathManager')
    @patch('misc.autofuse_performance_comparison.autofuse_core.autofuse_performance_comparison.FileManager')
    @patch('misc.autofuse_performance_comparison.autofuse_core.autofuse_performance_comparison.AutofuseExport')
    @patch('misc.autofuse_performance_comparison.autofuse_core.autofuse_performance_comparison.glob')
    def test_generate_compare_result_success_when_profiling_data_exists(self, mock_glob, mock_autofuse_export,
                                           mock_file_manager, mock_path_manager):
        generator = ComparisonGenerator(self.mock_params)
        mock_glob.glob.return_value = [
            "/path/to/output/autofuse_disabled/msprof_4130596_20260122065511633_ascend_pt/"
            "ASCEND_PROFILER_OUTPUT/ascend_pytorch_profiler.db",
            "/path/to/output/autofuse_enabled/msprof_4131596_20260122065512633_ascend_pt/"
            "ASCEND_PROFILER_OUTPUT/ascend_pytorch_profiler.db"
        ]
        df_disabled = pd.DataFrame({
            ComparisonGenerator.COL_MESSAGE: ['autofuse_pointwise_0_Abs_Add', 'autofuse_pointwise_0_Abs_Mul'],
            ComparisonGenerator.COL_NAME: ['/Abs/Add', '/Abs/Mul'],
            ComparisonGenerator.COL_DURATION: [100, 200],
            ComparisonGenerator.COL_AIC_SCALAR_TIME: [10, 20],
            ComparisonGenerator.COL_AIC_MTE2_TIME: [5, 10],
            ComparisonGenerator.COL_AIV_SCALAR_TIME: [2, 4],
            ComparisonGenerator.COL_AIV_VEC_TIME: [8, 16],
            ComparisonGenerator.COL_AIV_MTE2_TIME: [3, 6],
            ComparisonGenerator.COL_AIV_MTE3_TIME: [1, 2]
        })
        
        df_enabled = pd.DataFrame({
            ComparisonGenerator.COL_MESSAGE: ['autofuse_pointwise_0_Abs_Add', 'autofuse_pointwise_0_Abs_Mul'],
            ComparisonGenerator.COL_NAME: ['autofuse_pointwise_0_Abs_Add', 'autofuse_pointwise_0_Abs_Mul'],
            ComparisonGenerator.COL_DURATION: [80, 180],
            ComparisonGenerator.COL_AIC_SCALAR_TIME: [8, 18],
            ComparisonGenerator.COL_AIC_MTE2_TIME: [4, 9],
            ComparisonGenerator.COL_AIV_SCALAR_TIME: [1, 3],
            ComparisonGenerator.COL_AIV_VEC_TIME: [7, 15],
            ComparisonGenerator.COL_AIV_MTE2_TIME: [2, 5],
            ComparisonGenerator.COL_AIV_MTE3_TIME: [0, 1]
        })
        mock_autofuse_export.return_value.read_export_db.side_effect = [df_disabled, df_enabled]
        generator.generate_compare_result()
        self.assertTrue(generator._result_data.equals(self.expected_result))

    @patch('misc.autofuse_performance_comparison.autofuse_core.autofuse_performance_comparison.glob')
    def test_generate_compare_result_should_return_when_no_db_files(self, mock_glob):
        generator = ComparisonGenerator(self.mock_params)
        mock_glob.glob.return_value = []
        generator.generate_compare_result()
        self.assertIsNone(generator._result_data)

    @patch('misc.autofuse_performance_comparison.autofuse_core.autofuse_performance_comparison.PathManager')
    @patch('misc.autofuse_performance_comparison.autofuse_core.autofuse_performance_comparison.FileManager')
    @patch('misc.autofuse_performance_comparison.autofuse_core.autofuse_performance_comparison.AutofuseExport')
    @patch('misc.autofuse_performance_comparison.autofuse_core.autofuse_performance_comparison.glob')
    def test_generate_compare_result_should_return_when_df_is_empty(self, mock_glob, mock_autofuse_export,
                                            mock_file_manager, mock_path_manager):
        generator = ComparisonGenerator(self.mock_params)
        mock_glob.glob.return_value = [
            "/path/to/output/autofuse_enabled/some_ascend_pt/ASCEND_PROFILER_OUTPUT/ascend_pytorch_profiler.db",
            "/path/to/output/autofuse_enabled/some_ascend_pt/ASCEND_PROFILER_OUTPUT/ascend_pytorch_profiler.db"
        ]
        mock_autofuse_export.return_value.read_export_db.return_value = pd.DataFrame()
        generator.generate_compare_result()
        self.assertIsNone(generator._result_data)

    @patch('misc.autofuse_performance_comparison.autofuse_core.autofuse_performance_comparison.Workbook')
    @patch('misc.autofuse_performance_comparison.autofuse_core.autofuse_performance_comparison.os')
    def test_generate_view_success_when_result_data_is_not_none(self, mock_os, mock_workbook):
        generator = ComparisonGenerator(self.mock_params)
        generator._result_data = self.expected_result
        generator.generate_view()
        mock_workbook.assert_called()

    @patch('misc.autofuse_performance_comparison.autofuse_core.autofuse_performance_comparison.logger')
    def test_generate_view_when_data_is_none(self, mock_logger):
        generator = ComparisonGenerator(self.mock_params)
        generator._result_data = None
        generator.generate_view()
        mock_logger.error.assert_called_with(
            "Invalid comparison result, please check if the comparison result exists."
        )

    @patch('misc.autofuse_performance_comparison.autofuse_core.autofuse_performance_comparison.logger')
    def test_generate_view_invalid_column_count(self, mock_logger):
        generator = ComparisonGenerator(self.mock_params)
        generator._result_data = pd.DataFrame({
            'Name': ['op1'],
            'Duration(us)_disabled': [100]
        })
        generator.generate_view()
        mock_logger.error.assert_called_with(
            "Please verify the structure of the input data and column definitions."
        )

    @patch('misc.autofuse_performance_comparison.autofuse_core.autofuse_performance_comparison.shutil')
    @patch('misc.autofuse_performance_comparison.autofuse_core.autofuse_performance_comparison.os')
    @patch('misc.autofuse_performance_comparison.autofuse_core.autofuse_performance_comparison.PathManager')
    @patch('misc.autofuse_performance_comparison.autofuse_core.autofuse_performance_comparison.subprocess_cmd')
    @patch('misc.autofuse_performance_comparison.autofuse_core.autofuse_performance_comparison.ComparisonGenerator.generate_compare_result')
    @patch('misc.autofuse_performance_comparison.autofuse_core.autofuse_performance_comparison.ComparisonGenerator.generate_view')
    def test_run_success(self, mock_gen_view, mock_gen_result, mock_subprocess_cmd, 
                        mock_path_manager, mock_os, mock_shutil):
        generator = ComparisonGenerator(self.mock_params)
        mock_shutil.which.return_value = "/usr/bin/msprof"
        mock_subprocess_cmd.return_value = True
        generator.run()
        mock_path_manager.remove_path_safety.assert_any_call(generator.autofuse_disabled_path)
        mock_path_manager.remove_path_safety.assert_any_call(generator.autofuse_enabled_path)
        mock_subprocess_cmd.assert_called()
        mock_gen_result.assert_called()
        mock_gen_view.assert_called()

    @patch('misc.autofuse_performance_comparison.autofuse_core.autofuse_performance_comparison.shutil')
    @patch('misc.autofuse_performance_comparison.autofuse_core.autofuse_performance_comparison.logger')
    def test_run_should_return_when_msprof_not_found(self, mock_logger, mock_shutil):
        generator = ComparisonGenerator(self.mock_params)
        mock_shutil.which.return_value = None
        generator.run()
        mock_logger.info.assert_called_with("msprof: command not found")

    @patch('misc.autofuse_performance_comparison.autofuse_core.autofuse_performance_comparison.shutil')
    @patch('misc.autofuse_performance_comparison.autofuse_core.autofuse_performance_comparison.os')
    @patch('misc.autofuse_performance_comparison.autofuse_core.autofuse_performance_comparison.PathManager')
    @patch('misc.autofuse_performance_comparison.autofuse_core.autofuse_performance_comparison.subprocess_cmd')
    @patch('misc.autofuse_performance_comparison.autofuse_core.autofuse_performance_comparison.logger')
    def test_run_should_return_when_subprocess_failed(self, mock_logger, mock_subprocess_cmd,
                                  mock_path_manager, mock_os, mock_shutil):
        generator = ComparisonGenerator(self.mock_params)
        mock_shutil.which.return_value = "/usr/bin/msprof"
        mock_subprocess_cmd.return_value = False
        generator.run()
        mock_logger.error.assert_called_with("Failed to collect profiling data with autofuse disabled.")


if __name__ == '__main__':
    unittest.main()