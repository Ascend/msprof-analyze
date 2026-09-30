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
import shutil
import unittest
from unittest.mock import MagicMock, patch
from collections import OrderedDict

from msprof_analyze.compare_tools.compare_backend.generator.detail_performance_generator \
    import (DetailPerformanceGenerator)
from msprof_analyze.prof_common.constant import Constant
from msprof_analyze.prof_common.path_manager import PathManager

NAMESPACE = 'msprof_analyze.compare_tools.compare_backend'


class TestDetailPerformanceGenerator(unittest.TestCase):

    def setUp(self):
        """Set up test fixtures before each test method."""
        # Mock args with various comparison options
        self.args = MagicMock()
        self.args.base_step = "1"
        self.args.comparison_step = "2"
        self.args.output_path = "/test/output"
        self.args.enable_operator_compare = True
        self.args.enable_memory_compare = False
        self.args.enable_communication_compare = False
        self.args.enable_api_compare = False
        self.args.enable_kernel_compare = False
        self.args.enable_profiling_compare = False
        self.args.disable_module = False
        self.args.disable_details = False
        self.args.use_kernel_type = False

        # Mock profiling data dict
        self.profiling_data_dict = {
            Constant.BASE_DATA: MagicMock(),
            Constant.COMPARISON_DATA: MagicMock()
        }

        # Setup mock data for base and comparison
        self.setup_mock_profiling_data()

        # Create generator instance
        self.generator = DetailPerformanceGenerator(self.profiling_data_dict, self.args)

    def tearDown(self):
        if os.path.exists(self.args.output_path):
            shutil.rmtree(self.args.output_path)

    def setup_mock_profiling_data(self):
        """
        Setup mock profiling data for testing.
        """
        # Mock base data
        base_data = self.profiling_data_dict[Constant.BASE_DATA]
        base_data.overall_metrics = MagicMock()
        base_data.communication_dict = {}
        base_data.kernel_details = []
        base_data.python_function_data = [MagicMock()]
        base_data.bwd_tid = 2

        # Mock comparison data
        comparison_data = self.profiling_data_dict[Constant.COMPARISON_DATA]
        comparison_data.overall_metrics = MagicMock()
        comparison_data.communication_dict = {}
        comparison_data.kernel_details = []
        comparison_data.python_function_data = [MagicMock()]
        comparison_data.bwd_tid = 9

    def test_init_with_none_steps_should_use_void_step(self):
        """
        Test initialization with None step values.
        """
        self.args.base_step = None
        self.args.comparison_step = None

        generator = DetailPerformanceGenerator(self.profiling_data_dict, self.args)

        self.assertEqual(generator._base_step_id, Constant.VOID_STEP)
        self.assertEqual(generator._comparison_step_id, Constant.VOID_STEP)

    @patch(NAMESPACE + '.generator.detail_performance_generator.logger')
    def test_run_should_call_compare_and_generate_view(self, mock_logger):
        """
        Test that run method calls compare and generate_view.
        """
        with patch.object(self.generator, 'compare') as mock_compare, \
             patch.object(self.generator, 'generate_view') as mock_generate_view:

            self.generator.run()

            mock_compare.assert_called_once()
            mock_generate_view.assert_called_once()

    def test_compare_with_no_enabled_comparisons_should_get_empty_result_list(self):
        """Test compare with no comparison types enabled."""
        backup_args = self.args
        self.args.enable_operator_compare = False
        self.args.enable_memory_compare = False
        self.args.enable_communication_compare = False
        self.args.enable_api_compare = False
        self.args.enable_kernel_compare = False
        self.args.enable_profiling_compare = False

        generator = DetailPerformanceGenerator(self.profiling_data_dict, self.args)

        generator.compare()

        self.assertEqual(generator._result_data, OrderedDict())
        self.args = backup_args

    @patch(NAMESPACE + '.generator.detail_performance_generator.logger')
    def test_compare_with_enabled_comparisons_should_log_and_process_comparators(self, mock_logger):
        """
        Test compare with enabled comparison types.
        """
        mock_comparator = MagicMock()
        mock_comparator.generate_data.return_value = {"test": "data"}

        with patch.object(self.generator, '_create_comparator', return_value=[mock_comparator]) as mock_create:
            self.generator.compare()

            mock_create.assert_called_once()
            mock_comparator.generate_data.assert_called_once()
            self.assertEqual(self.generator._result_data, {"test": "data"})
            mock_logger.info.assert_called_with("Start to compare performance detail data, please wait.")


    @patch.object(PathManager, 'check_output_directory_path')
    def test_generate_view_should_create_excel_file_with_result_data(self, mock_check_output):
        """
        Test generate_view with result data creates Excel file.
        """
        with patch('os.path.abspath') as mock_abspath, \
             patch(NAMESPACE + '.generator.detail_performance_generator.logger'), \
             patch(NAMESPACE + '.generator.detail_performance_generator.datetime') as mock_datetime, \
             patch(NAMESPACE + '.generator.detail_performance_generator.ExcelView') as mock_excel_view:
            self.generator._result_data = {"test": "data"}
            mock_datetime.utcnow.return_value.strftime.return_value = "1145141919810"
            mock_abspath.return_value = "/absolute/path/to"
            mock_excel_instance = MagicMock()
            mock_excel_view.return_value = mock_excel_instance

            self.generator.generate_view()

            expected_file_path = os.path.join("/absolute/path/to", "performance_comparison_result_1145141919810.xlsx")
            mock_excel_view.assert_called_once_with(
                {"test": "data"},
                expected_file_path,
                self.args
            )

    def test_create_comparator_with_profiling_compare_enabled(self):
        """
        Test _create_comparator with profiling compare enabled.
        """
        self.args.enable_profiling_compare = True
        self.args.enable_operator_compare = False

        with patch(NAMESPACE + '.generator.detail_performance_generator.OverallMetricsComparator') as mock_overall:
            mock_instance = MagicMock()
            mock_overall.return_value = mock_instance

            comparators = self.generator._create_comparator()

            mock_overall.assert_called_once()
            self.assertEqual(len(comparators), 1)
            self.assertEqual(comparators[0], mock_instance)

    def test_create_comparator_with_communication_compare_enabled(self):
        """
        Test _create_comparator with communication compare enabled.
        """
        self.args.enable_communication_compare = True
        self.args.enable_operator_compare = False

        with patch(NAMESPACE + '.generator.detail_performance_generator.CommunicationComparator') as mock_comm:
            mock_instance = MagicMock()
            mock_comm.return_value = mock_instance

            comparators = self.generator._create_comparator()

            mock_comm.assert_called_once()
            self.assertEqual(len(comparators), 1)
            self.assertEqual(comparators[0], mock_instance)

    @patch.object(DetailPerformanceGenerator, '_module_match')
    @patch.object(DetailPerformanceGenerator, '_operator_match')
    def test_create_comparator_with_operator_compare_no_module_match(self, mock_operator_match, mock_module_match):
        """
        Test _create_comparator with operator compare but no module match.
        """
        self.args.enable_operator_compare = True
        self.args.disable_module = False

        mock_module_match.return_value = []
        mock_operator_result = [MagicMock()]
        mock_operator_match.return_value = mock_operator_result

        with patch(NAMESPACE + '.generator.detail_performance_generator.OperatorDataPrepare') as mock_prepare, \
             patch(NAMESPACE + '.generator.detail_performance_generator.OperatorStatisticComparator') as mock_stat, \
             patch(NAMESPACE + '.generator.detail_performance_generator.OperatorComparator') as mock_detail:

            mock_prepare_instance = MagicMock()
            mock_prepare_instance.get_top_layer_ops.return_value = [MagicMock()]
            mock_prepare.return_value = mock_prepare_instance

            mock_stat_instance = MagicMock()
            mock_detail_instance = MagicMock()
            mock_stat.return_value = mock_stat_instance
            mock_detail.return_value = mock_detail_instance

            comparators = self.generator._create_comparator()

            mock_module_match.assert_called_once()
            mock_operator_match.assert_called_once()
            self.assertEqual(len(comparators), 2)

    @patch.object(DetailPerformanceGenerator, '_module_match')
    def test_create_comparator_with_disable_module_flag(self, mock_module_match):
        """
        Test _create_comparator with disable_module flag set.
        """
        self.args.enable_operator_compare = True
        self.args.disable_module = True

        _comparators = self.generator._create_comparator()

        mock_module_match.assert_not_called()

    def test_create_comparator_with_api_compare_enabled(self):
        """Test _create_comparator with API compare enabled."""
        self.args.enable_api_compare = True
        self.args.enable_operator_compare = False

        with patch(NAMESPACE + '.generator.detail_performance_generator.OperatorDataPrepare') as mock_prepare, \
             patch(NAMESPACE + '.generator.detail_performance_generator.ApiCompareComparator') as mock_api:

            mock_prepare_instance = MagicMock()
            mock_prepare_instance.get_all_layer_ops.return_value = [MagicMock()]
            mock_prepare.return_value = mock_prepare_instance

            mock_api_instance = MagicMock()
            mock_api.return_value = mock_api_instance

            comparators = self.generator._create_comparator()

            mock_api.assert_called_once()
            self.assertEqual(len(comparators), 1)

    def test_create_comparator_with_kernel_compare_and_kernel_type(self):
        """Test _create_comparator with kernel compare and kernel type enabled."""
        self.args.enable_kernel_compare = True
        self.args.use_kernel_type = True

        with patch(NAMESPACE + '.generator.detail_performance_generator.KernelTypeComparator') as mock_kernel_type:
            mock_instance = MagicMock()
            mock_kernel_type.return_value = mock_instance

            comparators = self.generator._create_comparator()

            mock_kernel_type.assert_called_once()
            self.assertEqual(len(comparators), 3)

if __name__ == '__main__':
    unittest.main()
