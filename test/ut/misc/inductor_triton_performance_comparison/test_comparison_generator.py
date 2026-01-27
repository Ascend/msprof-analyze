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
import mock
import unittest
import pandas as pd
import sys
from unittest.mock import patch, MagicMock

mock_torch = mock.Mock()
mock_torch_npu = mock.Mock()
sys.modules["torch"] = mock_torch
sys.modules["torch_npu"] = mock_torch_npu
from misc.inductor_triton_performance_comparison.comparison_generator import ComparisonGenerator

class TestComparisonGenerator(unittest.TestCase):
    test_data = pd.DataFrame({
        'message': ['inductor_triton_0', 'inductor_triton_0', 'inductor_triton_0'],
        'Name': ['aclnnReduceSum_ReduceSumOpAiCore_ReduceSum', 'aclnnDivs_RealDivAiCore_RealDiv',
                 'triton_unk_fused_native_layer_norm_0'],
        'Duration(us)': [100.0, 50.0, 30.0],
    })
    result_data = pd.DataFrame({
        ComparisonGenerator.COL_TRITON_OP: ['triton_unk_fused_native_layer_norm_0'],
        ComparisonGenerator.COL_TRITON_DURATION: [30.0],
        ComparisonGenerator.COL_ORIGINAL_DURATION:
            ['aclnnReduceSum_ReduceSumOpAiCore_ReduceSum:100.00\naclnnDivs_RealDivAiCore_RealDiv:50.00'],
        ComparisonGenerator.COL_ORIGINAL_TOTAL_DURATION: [150.0],
        ComparisonGenerator.COL_DURATION_DIFF_RATIO: [0.2]
    })

    def setUp(self):
        self.mock_params = MagicMock()
        self.mock_params.fx_graph_path = "/path/to/graph_cacahe"
        self.mock_params.output_path = "/path/to/output"
        self.generator = ComparisonGenerator(self.mock_params)

    def test_process_group_should_return_expected_series_when_given_valid_data(self):
        expected_result = pd.Series({
            ComparisonGenerator.COL_TRITON_OP: 'triton_unk_fused_native_layer_norm_0',
            ComparisonGenerator.COL_TRITON_DURATION: 30.0,
            ComparisonGenerator.COL_ORIGINAL_DURATION:
                'aclnnReduceSum_ReduceSumOpAiCore_ReduceSum:100.00\naclnnDivs_RealDivAiCore_RealDiv:50.00',
            ComparisonGenerator.COL_ORIGINAL_TOTAL_DURATION: 150.0,
        })
        result = self.generator.process_group(self.test_data)
        self.assertTrue(expected_result.equals(result))

    def test_process_group_should_return_none_when_triton_op_not_found(self):
        test_data = pd.DataFrame({
            ComparisonGenerator.COL_MESSAGE: ['inductor_triton_0', 'inductor_triton_0'],
            ComparisonGenerator.COL_NAME: ['aclnnReduceSum_ReduceSumOpAiCore_ReduceSum',
                                           'aclnnDivs_RealDivAiCore_RealDiv'],
            ComparisonGenerator.COL_DURATION: [100.0, 50.0],
        })
        result = test_data.groupby("message").apply(self.generator.process_group)
        self.assertTrue(result.empty)

    @patch('misc.inductor_triton_performance_comparison.comparison_generator.PathManager')
    @patch('misc.inductor_triton_performance_comparison.comparison_generator.FileManager')
    @patch('misc.inductor_triton_performance_comparison.comparison_generator.InductorTritonExport')
    @patch('misc.inductor_triton_performance_comparison.comparison_generator.glob')
    def test_generate_compare_result_success_when_profiling_data_exists(self, mock_glob, mock_export,
                                                                        mock_file_manager, mock_path_manager):
        generator = ComparisonGenerator(self.mock_params)
        mock_glob.glob.return_value = [
            "/path/to/output/inductor_triton/msprof_4130596_20260122065511633_ascend_pt/"
            "ASCEND_PROFILER_OUTPUT/ascend_pytorch_profiler.db",
        ]
        mock_export.return_value.read_export_db.return_value = self.test_data
        generator.generate_compare_result()
        expected_result = pd.DataFrame({
            ComparisonGenerator.COL_TRITON_OP: ['triton_unk_fused_native_layer_norm_0'],
            ComparisonGenerator.COL_TRITON_DURATION: [30.0],
            ComparisonGenerator.COL_ORIGINAL_DURATION:
                ['aclnnReduceSum_ReduceSumOpAiCore_ReduceSum:100.00\naclnnDivs_RealDivAiCore_RealDiv:50.00'],
            ComparisonGenerator.COL_ORIGINAL_TOTAL_DURATION: [150.0],
            ComparisonGenerator.COL_DURATION_DIFF_RATIO: [0.2]
        })
        self.assertTrue(generator._result_data.equals(expected_result))

    @patch('misc.inductor_triton_performance_comparison.comparison_generator.logger')
    @patch('misc.inductor_triton_performance_comparison.comparison_generator.glob')
    def test_generate_compare_result_should_return_when_db_not_exists(self, mock_glob, mock_logger):
        mock_glob.glob.return_value = []
        generator = ComparisonGenerator(self.mock_params)
        generator.generate_compare_result()
        mock_logger.error.assert_called_with(
            f"Invalid profiling data: {generator.output_path}, please check if the "
            f"ascend_pytorch_profiler.db file exists."
        )

    @patch('misc.inductor_triton_performance_comparison.comparison_generator.PathManager')
    @patch('misc.inductor_triton_performance_comparison.comparison_generator.FileManager')
    @patch('misc.inductor_triton_performance_comparison.comparison_generator.logger')
    @patch('misc.inductor_triton_performance_comparison.comparison_generator.glob')
    def test_generate_compare_result_should_return_when_df_is_empty_or_none(self, mock_glob, mock_logger,
                                                                        mock_file_manager, mock_path_manager):
        db_path = "/path/to/output/inductor_triton/msprof_4131596_20260122065512633_ascend_pt/" \
                  "ASCEND_PROFILER_OUTPUT/ascend_pytorch_profiler.db"
        mock_glob.glob.return_value = [db_path]
        generator = ComparisonGenerator(self.mock_params)
        generator.generate_compare_result()
        mock_logger.error.assert_called_with(
            f"Invalid profiling data, the db path is {db_path}"
        )

    @patch('misc.inductor_triton_performance_comparison.comparison_generator.Workbook')
    @patch('misc.inductor_triton_performance_comparison.comparison_generator.os')
    def test_generate_view_success_when_result_data_is_not_none(self, mock_os, mock_workbook):
        generator = ComparisonGenerator(self.mock_params)
        generator._result_data = self.result_data
        generator.generate_view()
        mock_workbook.assert_called()


if __name__ == '__main__':
    unittest.main()