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
from unittest.mock import patch, MagicMock

from msprof_analyze.prof_common.constant import Constant
from msprof_analyze.compare_tools.compare_backend.comparison_generator import ComparisonGenerator


NAMESPACE = 'msprof_analyze.compare_tools.compare_backend'


class TestComparisonGenerator(unittest.TestCase):
    @staticmethod
    def build_args():
        return MagicMock()

    def test_load_data_should_use_parser_by_type_when_no_db_path(self):
        args = self.build_args()

        with patch(NAMESPACE + '.comparison_generator.ArgsManager') as mock_args_manager, \
             patch(NAMESPACE + '.comparison_generator.NPUProfilingParser') as mock_npu_parser, \
             patch(NAMESPACE + '.comparison_generator.GPUProfilingParser') as mock_gpu_parser, \
             patch(NAMESPACE + '.comparison_generator.NPUProfilingDbParser'):
            mgr = MagicMock()
            mgr.args = args
            mgr.base_path_dict = {Constant.PROFILER_DB_PATH: "path",
                                      Constant.PROFILING_TYPE: Constant.NPU}
            mgr.comparison_path_dict = {Constant.PROFILER_DB_PATH: "path",
                                             Constant.PROFILING_TYPE: Constant.GPU}
            mgr.base_step = 1
            mgr.comparison_step = 2
            mgr.base_profiling_type = Constant.NPU
            mgr.comparison_profiling_type = Constant.GPU
            mock_args_manager.return_value = mgr

            base_parser = MagicMock()
            cmp_parser = MagicMock()
            base_data = MagicMock(overall_metrics={'x': 3})
            cmp_data = MagicMock(overall_metrics={'y': 4})
            base_parser.load_data.return_value = base_data
            cmp_parser.load_data.return_value = cmp_data
            mock_npu_parser.return_value = base_parser
            mock_gpu_parser.return_value = cmp_parser

            gen = ComparisonGenerator(args)
            gen.load_data()

    def test_generate_compare_result_should_call_overall_start_and_join(self):
        args = self.build_args()
        gen = ComparisonGenerator(args)

        base_data = MagicMock(overall_metrics={'a': 1})
        cmp_data = MagicMock(overall_metrics={'b': 2})
        gen._data_dict = {
            Constant.BASE_DATA: base_data,
            Constant.COMPARISON_DATA: cmp_data,
        }

        with patch(NAMESPACE + '.comparison_generator.OverallPerformanceGenerator') as mock_overall_gen, \
             patch(NAMESPACE + '.comparison_generator.DetailPerformanceGenerator') as mock_detail_gen:
            overall_instance = MagicMock()
            mock_overall_gen.return_value = overall_instance
            detail_instance = MagicMock()
            mock_detail_gen.return_value = detail_instance

            gen.generate_compare_result()

            mock_overall_gen.assert_called_once()
            overall_instance.start.assert_called_once()
            detail_instance.run.assert_called_once()
            overall_instance.join.assert_called_once()

    def test_run_should_catch_exceptions_and_log_error(self):
        args = self.build_args()
        gen = ComparisonGenerator(args)

        with patch(NAMESPACE + '.comparison_generator.ArgsManager') as mock_args_manager, \
             patch(NAMESPACE + '.comparison_generator.logger') as mock_logger:
            mgr = MagicMock()
            mock_args_manager.return_value = mgr
            gen.load_data = MagicMock(side_effect=RuntimeError('boom'))
            gen.run()
            mock_logger.error.assert_called()

    def test_run_interface_should_use_specific_interface_when_available(self):
        args = self.build_args()
        with patch(NAMESPACE + '.comparison_generator.ArgsManager') as mock_args_manager, \
             patch.object(ComparisonGenerator, 'load_data') as mock_load_data, \
             patch(NAMESPACE + '.comparison_generator.OverallInterface') as mock_overall_interface, \
             patch(NAMESPACE + '.comparison_generator.CompareInterface') as mock_compare_interface:
            # Prepare mocks
            mock_load_data.return_value = None
            overall_instance = MagicMock()
            expected_result = {"result": "ok"}
            overall_instance.run.return_value = expected_result
            mock_overall_interface.return_value = overall_instance

            gen = ComparisonGenerator(args)
            gen.run_interface(Constant.OVERALL_COMPARE)

            mock_args_manager.return_value.init.assert_called_once()
            mock_args_manager.return_value.set_compare_type.assert_called_once_with(Constant.OVERALL_COMPARE)

            mock_compare_interface.assert_not_called()


if __name__ == '__main__':
    unittest.main()
