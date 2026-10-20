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


from msprof_analyze.advisor.analyzer.analyzer_controller import AnalyzerController
from msprof_analyze.advisor.analyzer.analyzer_controller import AsyncParams, EnumParamsParser
from msprof_analyze.advisor.analyzer.cluster.slow_rank_analyzer import SlowRankAnalyzer
from msprof_analyze.advisor.common.analyzer_scopes import SupportedScopes
from msprof_analyze.advisor.common.async_analysis_status import AsyncAnalysisStatus
from msprof_analyze.advisor.interface.interface import Interface
from msprof_analyze.prof_common.constant import Constant


class TestAsyncParams(unittest.TestCase):
    def setUp(self):
        AsyncParams.user_valid_arguments = {}
        AsyncParams.user_valid_envs = {}
        AsyncParams.user_non_enum_params = {}
        AsyncParams.user_invalid_values = []
        AsyncParams.user_total_params = {}

    def test_parse_async_list_params_valid_envs(self):
        key = 'test_key'
        value = ['option1', 'option2']
        option_values = [['option1', 'option2']]
        key_type = EnumParamsParser.ENVS
        value_type = 'list'

        AsyncParams.parse_async_list_params(key, value, option_values, key_type, value_type)

        self.assertEqual(AsyncParams.user_valid_envs, {'TEST_KEY': 'option1,option2'})
        self.assertEqual(len(AsyncParams.user_invalid_values), 0)

    def test_parse_async_list_params_invalid(self):
        key = 'test_key'
        value = ['invalid']
        option_values = [['option1', 'option2']]
        key_type = EnumParamsParser.ARGUMENTS
        value_type = 'list'

        AsyncParams.parse_async_list_params(key, value, option_values, key_type, value_type)

        self.assertEqual(len(AsyncParams.user_invalid_values), 1)
        self.assertEqual(AsyncParams.user_valid_arguments, {})

    def test_parse_async_int_params_valid_arguments(self):
        key = 'test_key'
        value = '1'
        option_values = [1, 2, 3]
        key_type = EnumParamsParser.ARGUMENTS
        value_type = 'int'

        AsyncParams.parse_async_int_params(key, value, option_values, key_type, value_type)

        self.assertEqual(AsyncParams.user_valid_arguments, {'test_key': 1})
        self.assertEqual(len(AsyncParams.user_invalid_values), 0)

    def test_parse_async_int_params_invalid(self):
        key = 'test_key'
        value = '4'
        option_values = [1, 2, 3]
        key_type = EnumParamsParser.ENVS
        value_type = 'int'

        AsyncParams.parse_async_int_params(key, value, option_values, key_type, value_type)

        self.assertEqual(len(AsyncParams.user_invalid_values), 1)
        self.assertEqual(AsyncParams.user_valid_envs, {})

    def test_parse_async_str_params_valid_envs(self):
        key = 'test_key'
        value = 'option1'
        option_values = ['option1', 'option2']
        key_type = EnumParamsParser.ENVS
        value_type = 'str'

        AsyncParams.parse_async_str_params(key, value, option_values, key_type, value_type)

        self.assertEqual(AsyncParams.user_valid_envs, {'TEST_KEY': 'option1'})
        self.assertEqual(len(AsyncParams.user_invalid_values), 0)

    def test_parse_async_str_params_invalid(self):
        key = 'test_key'
        value = 'invalid'
        option_values = ['option1', 'option2']
        key_type = EnumParamsParser.ARGUMENTS
        value_type = 'str'

        AsyncParams.parse_async_str_params(key, value, option_values, key_type, value_type)

        self.assertEqual(len(AsyncParams.user_invalid_values), 1)
        self.assertEqual(AsyncParams.user_valid_arguments, {})

    def test_parse_async_boolean_params_valid_arguments(self):
        key = 'test_key'
        value = 'true'
        option_values = ['true', 'false']
        key_type = EnumParamsParser.ARGUMENTS
        value_type = 'boolean'

        AsyncParams.parse_async_boolean_params(key, value, option_values, key_type, value_type)

        self.assertEqual(AsyncParams.user_valid_arguments, {'test_key': True})
        self.assertEqual(len(AsyncParams.user_invalid_values), 0)

    def test_parse_async_boolean_params_invalid(self):
        key = 'test_key'
        value = 'invalid'
        option_values = ['true', 'false']
        key_type = EnumParamsParser.ENVS
        value_type = 'boolean'

        AsyncParams.parse_async_boolean_params(key, value, option_values, key_type, value_type)

        self.assertEqual(len(AsyncParams.user_invalid_values), 1)
        self.assertEqual(AsyncParams.user_valid_envs, {})


class TestAnalyzerController(unittest.TestCase):
    def setUp(self):
        self.controller = AnalyzerController()
        self.controller.slow_rank_analyzer = MagicMock()
        self.controller.slow_link_analyzer = MagicMock()
        self.controller.default_rank_id = 0
        self.profiling_path = "./DTTestAnalyzerController"
        self.controller._stage_computation_analysis = MagicMock()
        self.controller._global_computation_analysis = MagicMock()
        self.controller.memory_analysis = MagicMock()
        self.controller._get_profiling_path_by_rank = MagicMock()

    def test_compute__given_valid_input_when_scope_not_equal_to_stage_compute_then_get_job_list(self):
        job_list = AnalyzerController().computation_analysis("./DTTestAnalyzerController")
        self.assertEqual(len(job_list), len(Interface.supported_analyzer.get(Interface.COMPUTATION).keys()))

    def test_compute_given_valid_input_when_scope_equal_to_stage_compute_then_get_empty_list(self):
        with patch("msprof_analyze.advisor.interface.interface.Interface.get_scope",
                   return_value=[SupportedScopes.STAGE_COMPUTE]):
            job_list = AnalyzerController().computation_analysis("./DTTestAnalyzerController")
            self.assertEqual(len(job_list), 0)

    def test_memory_given_valid_input_then_get_job_list(self):
        job_list = AnalyzerController().memory_analysis("./DTTestAnalyzerController")
        self.assertEqual(len(job_list), len(Interface.supported_analyzer.get(Interface.MEMORY).keys()))

    def test_communication_given_valid_input_when_supported_trans_type_then_get_job_list(self):
        args = {
            "rank": 1,
            "step": 1,
            "benchmark_step": 1,
            "bandwidth_type": "RDMA",
            "step_duration": 10
        }
        job_list = AnalyzerController().communication_analysis(profiling_path="./DTTestAnalyzerController", **args)
        self.assertEqual(len(job_list), 3)

    def test_communication_given_valid_input_when_not_supported_trans_type_then_get_empty_list(self):
        args = {
            "rank": 1,
            "step": 1,
            "benchmark_step": 1,
            "bandwidth_type": "Local",
            "step_duration": 10
        }
        job_list = AnalyzerController().communication_analysis(profiling_path="./DTTestAnalyzerController", **args)
        self.assertEqual(len(job_list), 0)

    def test_schedule_given_valid_input_when_correct_scope_then_get_job_list(self):
        job_list = AnalyzerController().schedule_analysis(profiling_path="./DTTestAnalyzerController")
        self.assertEqual(len(job_list), len(Interface.supported_analyzer.get(Interface.SCHEDULE).keys()))

    @patch('psutil.Process')
    def test__set_analysis_process_priority(self, mock_process):
        pid = 1234
        mock_process_instance = MagicMock()
        mock_process.return_value = mock_process_instance

        # test for Linux
        with patch('platform.system', return_value='Linux'):
            mock_process_instance.reset_mock()
            AnalyzerController._set_analysis_process_priority(pid)
            mock_process_instance.nice.assert_called_once_with(19)

    @patch('msprof_analyze.prof_common.path_manager.PathManager.input_path_common_check')
    @patch('pathlib.Path.exists')
    def test__check_profiling_path_valid(self, mock_exists, mock_check):
        profiling_path = 'test_path'
        mock_exists.return_value = True
        result = AnalyzerController._check_profiling_path_valid(profiling_path)
        self.assertTrue(result)

        mock_exists.return_value = False
        result = AnalyzerController._check_profiling_path_valid(profiling_path)
        self.assertFalse(result)

    @patch('msprof_analyze.advisor.analyzer.cluster.slow_rank_analyzer.SlowRankAnalyzer.compute_max_gap_ratio')
    def test__get_step_rank_for_cluster_statistic_diff(self, mock_compute_ratio):
        target_data = [[1, 2, 3], [4, 5, 6]]
        benchmark_data = [[1, 2, 3], [4, 5, 6]]
        headers = ['step', 'rank_id', 'dimension']
        dimension = 'dimension'
        mock_compute_ratio.return_value = 1

        step, benchmark_step, rank_id = AnalyzerController._get_step_rank_for_cluster_statistic_diff(
            target_data, benchmark_data, headers, dimension
        )
        self.assertEqual(step, 1)
        self.assertEqual(benchmark_step, 1)
        self.assertEqual(rank_id, 2)

    @patch.dict('os.environ', {})
    def test__init_async_analysis_env(self):
        kwargs = {'async_analysis_env': {'KEY': 'VALUE'}}
        AnalyzerController._init_async_analysis_env(kwargs)
        self.assertEqual(os.environ['KEY'], 'VALUE')

    @patch('msprof_analyze.advisor.analyzer.analyzer_controller.AsyncParams.parse_params')
    @patch('msprof_analyze.advisor.analyzer.analyzer_controller.AsyncParams.user_invalid_values', [])
    @patch('msprof_analyze.advisor.analyzer.analyzer_controller.AsyncParams.user_total_params',
           {'analysis_dimensions': ['test']})
    def test_format_async_analysis_params(self, mock_parse):
        pid = 1234
        async_resp = {}
        dimensions = ['original']
        kwargs = {}
        result_dimensions, result_kwargs = self.controller.format_async_analysis_params(pid, async_resp, dimensions,
                                                                                        kwargs)
        self.assertEqual(result_dimensions, ['test'])

    @patch('psutil.Process')
    def test_get_response_by_pid(self, mock_process):
        pid = 1234
        self.controller.analysis_process_resp[pid] = {'status': AsyncAnalysisStatus.SUCCESS}
        result = self.controller.get_response_by_pid(pid)
        self.assertEqual(result['status'], AsyncAnalysisStatus.SUCCESS)

    @patch.object(AnalyzerController, 'schedule_analysis', return_value=[])
    @patch.object(AnalyzerController, '_profiling_comparison', return_value=[])
    def test_cluster_schedule_analysis_with_slow_rank(self, mock_profiling_comparison, mock_schedule_analysis):
        global_step_rank = {
            "maximum": {"rank_id": 1, "step": 10},
            "minimum": {"rank_id": 2, "step": 5}
        }
        self.controller.slow_rank_analyzer.get_global_step_rank.return_value = global_step_rank
        self.controller.slow_rank_analyzer.get_step_duration.return_value = 100
        self.controller._get_profiling_path_by_rank = MagicMock(return_value='test_path')
        self.controller.kwargs = {}

        result = self.controller.cluster_schedule_analysis(self.profiling_path)

        self.controller.slow_rank_analyzer.get_global_step_rank.assert_called_once_with(SlowRankAnalyzer.FREE)
        mock_schedule_analysis.assert_called_once()
        mock_profiling_comparison.assert_called_once()
        self.assertIsInstance(result, list)

    @patch.object(AnalyzerController, 'schedule_analysis', return_value=[])
    @patch.object(AnalyzerController, '_profiling_comparison', return_value=[])
    def test_cluster_schedule_analysis_without_slow_rank(self, mock_profiling_comparison, mock_schedule_analysis):
        global_step_rank = {
            "maximum": {},
            "minimum": {"rank_id": 2, "step": 5}
        }
        self.controller.slow_rank_analyzer.get_global_step_rank.return_value = global_step_rank
        self.controller.slow_rank_analyzer.get_step_duration.return_value = 100
        self.controller._get_profiling_path_by_rank = MagicMock(return_value='test_path')
        self.controller.kwargs = {}

        result = self.controller.cluster_schedule_analysis(self.profiling_path)

        self.controller.slow_rank_analyzer.get_global_step_rank.assert_called_once_with(SlowRankAnalyzer.FREE)
        mock_schedule_analysis.assert_called_once()
        mock_profiling_comparison.assert_called_once()
        self.assertIsInstance(result, list)

    @patch.object(AnalyzerController, 'schedule_analysis', return_value=[])
    @patch.object(AnalyzerController, '_profiling_comparison', return_value=[])
    def test_cluster_schedule_analysis_with_benchmark_path(self, mock_profiling_comparison, mock_schedule_analysis):
        global_step_rank = {
            "maximum": {"rank_id": 1, "step": 10},
            "minimum": {"rank_id": 2, "step": 5}
        }
        self.controller.slow_rank_analyzer.get_global_step_rank.return_value = global_step_rank
        self.controller.slow_rank_analyzer.get_step_duration.return_value = 100
        self.controller._get_profiling_path_by_rank = MagicMock(return_value='test_path')
        self.controller.kwargs = {"benchmark_profiling_path": "test_benchmark_path"}

        result = self.controller.cluster_schedule_analysis(self.profiling_path)

        self.controller.slow_rank_analyzer.get_global_step_rank.assert_called_once_with(SlowRankAnalyzer.FREE)
        mock_schedule_analysis.assert_called_once()
        mock_profiling_comparison.assert_not_called()
        self.assertIsInstance(result, list)

    @patch.object(Interface, 'get_scope')
    @patch.object(Interface, 'get_analyzer')
    @patch.object(AnalyzerController, 'communication_analysis')
    def test_cluster_communication_analysis_requires_cluster_dataset(self, mock_communication_analysis,
                                                                     mock_get_analyzer, mock_get_scope):
        mock_get_scope.return_value = ['scope1']
        mock_analyzer_class = MagicMock()
        mock_analyzer_class.requires_cluster_dataset = True
        mock_get_analyzer.return_value = mock_analyzer_class

        result = self.controller.cluster_communication_analysis(self.profiling_path)

        mock_get_scope.assert_called_once_with(Interface.COMMUNICATION)
        mock_get_analyzer.assert_called_once_with(Interface.COMMUNICATION, 'scope1')
        self.assertEqual(len(result), 1)
        self.assertIsInstance(result[0], tuple)
        mock_communication_analysis.assert_not_called()

    @patch.object(Interface, 'get_scope')
    @patch.object(Interface, 'get_analyzer')
    @patch.object(AnalyzerController, 'communication_analysis', return_value=["comm"])
    def test_cluster_communication_analysis_not_requires_cluster_dataset(self, mock_communication_analysis,
                                                                         mock_get_analyzer, mock_get_scope):
        mock_get_scope.return_value = ['scope1']
        mock_analyzer_class = MagicMock()
        mock_analyzer_class.requires_cluster_dataset = False
        mock_get_analyzer.return_value = mock_analyzer_class
        self.controller.slow_link_analyzer.get_global_step_rank.side_effect = [
            {'minimum': {'rank_id': 1, 'step': 10}},
            {'minimum': {'rank_id': 2, 'step': 20}}
        ]

        result = self.controller.cluster_communication_analysis(self.profiling_path)

        mock_get_scope.assert_called_once_with(Interface.COMMUNICATION)
        mock_get_analyzer.assert_called_once_with(Interface.COMMUNICATION, 'scope1')
        self.assertEqual(len(result), 2)
        mock_communication_analysis.assert_called()

    def test_cluster_computation_analysis_with_stage_step_rank(self):
        stage_step_rank = {'some_key': 'some_value'}
        global_step_rank = {}
        self.controller.slow_rank_analyzer.get_global_step_rank.return_value = global_step_rank
        self.controller.slow_rank_analyzer.get_stage_step_rank.return_value = stage_step_rank

        result = self.controller.cluster_computation_analysis(self.profiling_path)

        self.controller.slow_rank_analyzer.get_global_step_rank.assert_called_once_with(SlowRankAnalyzer.COMPUTE)
        self.controller.slow_rank_analyzer.get_stage_step_rank.assert_called_once_with(SlowRankAnalyzer.COMPUTE)
        self.controller._stage_computation_analysis.assert_called_once_with(self.profiling_path, stage_step_rank, [])
        self.controller._global_computation_analysis.assert_not_called()
        self.assertEqual(result, self.controller._stage_computation_analysis.return_value)

    def test_cluster_computation_analysis_without_stage_step_rank(self):
        stage_step_rank = {}
        global_step_rank = {'another_key': 'another_value'}
        self.controller.slow_rank_analyzer.get_global_step_rank.return_value = global_step_rank
        self.controller.slow_rank_analyzer.get_stage_step_rank.return_value = stage_step_rank

        result = self.controller.cluster_computation_analysis(self.profiling_path)

        self.controller.slow_rank_analyzer.get_global_step_rank.assert_called_once_with(SlowRankAnalyzer.COMPUTE)
        self.controller.slow_rank_analyzer.get_stage_step_rank.assert_called_once_with(SlowRankAnalyzer.COMPUTE)
        self.controller._stage_computation_analysis.assert_not_called()
        self.controller._global_computation_analysis.assert_called_once_with(self.profiling_path, global_step_rank, [])
        self.assertEqual(result, self.controller._global_computation_analysis.return_value)

    def test_cluster_memory_analysis_with_slow_rank(self):
        global_step_rank = {
            "maximum": {
                "rank_id": 1,
                "step": 10
            }
        }
        self.controller.slow_rank_analyzer.get_global_step_rank.return_value = global_step_rank
        self.controller.slow_rank_analyzer.get_step_duration.return_value = 100
        self.controller._get_profiling_path_by_rank.return_value = 'test_analysis_path'

        _result = self.controller.cluster_memory_analysis(self.profiling_path)

        self.controller.slow_rank_analyzer.get_global_step_rank.assert_called_once_with(SlowRankAnalyzer.FREE)
        self.controller._get_profiling_path_by_rank.assert_called_once_with(self.profiling_path, 1)
        self.controller.slow_rank_analyzer.get_step_duration.assert_called_once_with(1, 10)
        self.controller.memory_analysis.assert_called_once_with(
            'test_analysis_path',
            step=10,
            rank=1,
            step_duration=100
        )

    def test_cluster_memory_analysis_without_slow_rank(self):
        global_step_rank = {
            "maximum": {}
        }
        self.controller.slow_rank_analyzer.get_global_step_rank.return_value = global_step_rank
        self.controller.slow_rank_analyzer.get_step_duration.return_value = 100
        self.controller._get_profiling_path_by_rank.return_value = 'test_analysis_path'

        _result = self.controller.cluster_memory_analysis(self.profiling_path)

        self.controller.slow_rank_analyzer.get_global_step_rank.assert_called_once_with(SlowRankAnalyzer.FREE)
        self.controller._get_profiling_path_by_rank.assert_called_once_with(self.profiling_path, 0)
        self.controller.slow_rank_analyzer.get_step_duration.assert_called_once_with(0, None)
        self.controller.memory_analysis.assert_called_once_with(
            'test_analysis_path',
            step=None,
            rank=0,
            step_duration=100
        )

    def test_profiling_comparison_disabled(self):
        with patch.dict(os.environ, {Constant.DISABLE_PROFILING_COMPARISON: 'true'}):
            result = self.controller._profiling_comparison([])
            self.assertEqual(result, [])

    def test_profiling_comparison_enabled(self):
        compare_profiling_list = [{'profiling_path': 'test_path'}]
        with patch('msprof_analyze.advisor.analyzer.analyzer_controller.Interface'):
            result = self.controller._profiling_comparison(compare_profiling_list)
            self.assertEqual(len(result), 1)

    def test_is_cluster_profiling_file(self):
        with patch('os.path.isfile') as mock_isfile:
            mock_isfile.return_value = True
            result = self.controller._is_cluster_profiling('test_path')
            self.assertFalse(result)

    def test_update_analysis_process_resp(self):
        pid = 1
        resp = {}
        kwargs = {'test_key': 'test_value'}
        self.controller._update_analysis_process_resp(pid, resp, **kwargs)
        self.assertEqual(self.controller.analysis_process_resp[pid], kwargs)

    def test_get_analysis_finished_resp_success(self):
        pid = 1
        resp = {}
        with patch('os.path.exists') as mock_exists:
            mock_exists.return_value = True
            with patch('msprof_analyze.advisor.analyzer.analyzer_controller.Config') as mock_config:
                mock_config.return_value.work_path = 'test_work_path'
                self.controller._get_analysis_finished_resp(pid, resp)
                self.assertEqual(self.controller.analysis_process_resp[pid]['status'], 'success')

    def test_get_analysis_finished_resp_failed(self):
        pid = 1
        resp = {}
        with patch('os.path.exists') as mock_exists:
            mock_exists.return_value = False
            with patch('msprof_analyze.advisor.analyzer.analyzer_controller.Config') as mock_config:
                mock_config.return_value.work_path = 'test_work_path'
                self.controller._get_analysis_finished_resp(pid, resp)
                self.assertEqual(self.controller.analysis_process_resp[pid]['status'], 'failed')

    def test_stage_computation_analysis(self):
        profiling_path = 'test_profiling_path'
        stage_step_rank = {'stage1': {'maximum': {'rank_id': 0, 'step': 1}, 'minimum': {'rank_id': 1, 'step': 1}}}
        job_list = []
        with patch.object(self.controller, '_get_profiling_path_by_rank') as mock_get_path:
            mock_get_path.return_value = 'test_rank_path'
            with patch.object(self.controller, '_profiling_comparison') as mock_profiling_comparison:
                with patch('msprof_analyze.advisor.analyzer.analyzer_controller.Interface.add_analyzer'):
                    result = self.controller._stage_computation_analysis(profiling_path, stage_step_rank, job_list)
                    self.assertEqual(len(result), mock_profiling_comparison.return_value.__len__())

    def test_global_computation_analysis(self):
        profiling_path = 'test_profiling_path'
        global_step_rank = {'maximum': {'rank_id': 0, 'step': 1}, 'minimum': {'rank_id': 1, 'step': 1}}
        job_list = []
        with patch.object(self.controller, '_get_profiling_path_by_rank') as mock_get_path:
            mock_get_path.return_value = 'test_rank_path'
            with patch.object(self.controller, 'computation_analysis') as mock_computation_analysis:
                with patch.object(self.controller, '_profiling_comparison') as mock_profiling_comparison:
                    result = self.controller._global_computation_analysis(profiling_path, global_step_rank, job_list)
                    self.assertEqual(len(result),
                                     mock_computation_analysis.return_value.__len__() + \
                                     mock_profiling_comparison.return_value.__len__())


if __name__ == '__main__':
    unittest.main()
