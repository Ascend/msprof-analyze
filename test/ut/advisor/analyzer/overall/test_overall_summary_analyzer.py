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

import logging
import unittest
from io import StringIO
from unittest import mock

from msprof_analyze.advisor.analyzer.overall.overall_summary_analyzer import OverallSummaryAnalyzer, get_profile_path


class TestOverallSummaryAnalyzer(unittest.TestCase):
    def setUp(self):
        logging.basicConfig(level=logging.INFO)
        self.logger = logging.getLogger()
        self.logger.addHandler(logging.StreamHandler(StringIO()))
        self.collection_path = "test_collection_path"
        self.n_processes = 2
        self.benchmark_profiling_path = "test_benchmark_path"

    def tearDown(self):
        self.logger.handlers.clear()

    def test_calculate_ratio(self):
        """测试calculate_ratio静态方法"""
        self.assertEqual(OverallSummaryAnalyzer.calculate_ratio(10, 2), 5.0)
        self.assertEqual(OverallSummaryAnalyzer.calculate_ratio(10, 0), float("inf"))
        self.assertEqual(OverallSummaryAnalyzer.calculate_ratio(-10, 2), -5.0)

    @mock.patch('msprof_analyze.prof_common.additional_args_manager.AdditionalArgsManager')
    def test_get_time_category_dict_zh(self, mock_additional_args_manager):
        """测试get_time_category_dict静态方法 - 中文"""
        mock_instance = mock.MagicMock()
        mock_instance.language = "zh"
        mock_additional_args_manager.return_value = mock_instance
        overall_dict = {
            'computing_time_ms': 100.5,
            'uncovered_communication_time_ms': 50.25,
            'free_time_ms': 25.125
        }
        result = OverallSummaryAnalyzer.get_time_category_dict(overall_dict)
        expected = {
            "计算时长": 100.5,
            "未被掩盖的通信时长": 50.25,
            "空闲时长": 25.125
        }
        self.assertEqual(result, expected)

    @mock.patch('msprof_analyze.advisor.analyzer.overall.overall_summary_analyzer.ComparisonInterface')
    def test_process_no_data(self, mock_comparison_interface):
        """测试process方法 - 无数据返回"""
        mock_comparison_interface_instance = mock.MagicMock()
        mock_comparison_interface_instance.disaggregate_perf.return_value = None
        mock_comparison_interface.return_value = mock_comparison_interface_instance
        analyzer = OverallSummaryAnalyzer(self.collection_path)
        analyzer.process()
        self.assertFalse(analyzer._is_minimal_profiling)
        self.assertEqual(analyzer.cur_data, {})

    @mock.patch('msprof_analyze.prof_common.additional_args_manager.AdditionalArgsManager')
    @mock.patch(
        'msprof_analyze.advisor.analyzer.overall.overall_summary_analyzer.OverallSummaryAnalyzer.calculate_ratio')
    def test_identify_bottleneck_with_benchmark(self, mock_calculate_ratio, mock_additional_args_manager):
        """测试identify_bottleneck方法 - 有基准比较"""
        mock_instance = mock.MagicMock()
        mock_instance.language = "en"
        mock_additional_args_manager.return_value = mock_instance
        mock_calculate_ratio.return_value = 0.05
        analyzer = OverallSummaryAnalyzer(self.collection_path)
        analyzer.cur_data = {
            "overall_data": {
                "Computing Time": 100.0,
                "Uncovered Communication Time": 50.0,
                "Free Time": 25.0
            }
        }
        analyzer._has_benchmark_profiling = True
        analyzer._disaggregate_benchmark_perf = {
            "overall": {
                "computing_time_ms": 80.0,
                "uncovered_communication_time_ms": 40.0,
                "free_time_ms": 20.0
            }
        }
        with mock.patch('msprof_analyze.advisor.analyzer.overall.overall_summary_analyzer.'
                        'OverallSummaryAnalyzer.get_time_category_dict') as mock_get_time_category_dict:
            mock_get_time_category_dict.return_value = {
                "Computing Time": 80.0,
                "Uncovered Communication Time": 40.0,
                "Free Time": 20.0
            }
            analyzer.identify_bottleneck()
        self.assertIn("comparison_result", analyzer.cur_bottleneck)

    @mock.patch(
        'msprof_analyze.advisor.analyzer.overall.overall_summary_analyzer.OverallSummaryAnalyzer.identify_bottleneck')
    @mock.patch(
        'msprof_analyze.advisor.analyzer.overall.overall_summary_analyzer.OverallSummaryAnalyzer.format_bottleneck')
    @mock.patch('msprof_analyze.advisor.analyzer.overall.overall_summary_analyzer.'
                'OverallSummaryAnalyzer.format_over_summary_analysis')
    @mock.patch('msprof_analyze.advisor.analyzer.overall.overall_summary_analyzer.OverallSummaryAnalyzer.make_record')
    @mock.patch('msprof_analyze.advisor.analyzer.overall.overall_summary_analyzer.OverallSummaryAnalyzer.make_render')
    @mock.patch('msprof_analyze.advisor.analyzer.overall.overall_summary_analyzer.OverallSummaryAnalyzer.path_check')
    @mock.patch('msprof_analyze.advisor.analyzer.overall.overall_summary_analyzer.OverallSummaryAnalyzer.process')
    def test_optimize(self, *args):
        """测试optimize方法"""
        m_process, m_path_check, m_make_render, m_make_record, m_format_analysis, m_bottleneck, m_identify = args
        m_path_check.return_value = True
        analyzer = OverallSummaryAnalyzer(self.collection_path)
        analyzer.result = mock.MagicMock()
        result = analyzer.optimize()
        m_path_check.assert_called_once()
        m_process.assert_called_once()
        m_identify.assert_called_once()
        m_bottleneck.assert_called_once()
        m_format_analysis.assert_called_once()
        m_make_record.assert_called_once()
        m_make_render.assert_called_once()
        self.assertEqual(result, analyzer.result)

    def test_format_bottleneck(self):
        """测试format_bottleneck方法"""
        analyzer = OverallSummaryAnalyzer(self.collection_path)
        analyzer.cur_bottleneck = {
            "overall_data": "Overall bottleneck info",
            "comparison_result": "Comparison bottleneck info"
        }
        analyzer.format_bottleneck()
        self.assertIn("Overall bottleneck info", analyzer.bottleneck_str)
        self.assertIn("Comparison bottleneck info", analyzer.bottleneck_str)

    def test_get_analysis_data(self):
        """测试get_analysis_data方法"""
        analyzer = OverallSummaryAnalyzer(self.collection_path)
        data_dict = {
            "overall": {"key1": "value1"},
            "computing_time_disaggregate": {"key2": "value2"},
            "communication_time_disaggregate": {"key3": "value3"},
            "free_time_disaggregate": {"key4": "value4"}
        }
        result = analyzer.get_analysis_data(data_dict)
        expected = {
            "key1": "value1",
            "key2": "value2",
            "key3": "value3",
            "key4": "value4"
        }
        self.assertEqual(result, expected)
        self.assertEqual(analyzer.get_analysis_data({}), {})

    def test_format_analysis_only(self):
        """测试format_analysis_only方法"""
        analyzer = OverallSummaryAnalyzer(self.collection_path)
        analyzer.performance_time_dict = {
            "Time1": "time1_key",
            "Time2": "time2_key"
        }
        performance_data = {
            "e2e_time_ms": 200.0,
            "time1_key": 100.0,
            "time2_key": 50.0
        }
        headers = ['Performance Index', 'Duration(ms)', 'Duration Ratio']
        with mock.patch('msprof_analyze.advisor.analyzer.overall.overall_summary_analyzer.'
                        'OverallSummaryAnalyzer.calculate_ratio') as mock_calculate_ratio:
            mock_calculate_ratio.side_effect = [0.5, 0.25]
            analyzer.format_analysis_only(performance_data, headers)
        self.assertEqual(analyzer.over_summary_analysis["headers"], headers)
        self.assertEqual(len(analyzer.over_summary_analysis["data"]), 2)

    def test_format_analysis_with_benchmark(self):
        """测试format_analysis_with_benchmark方法"""
        analyzer = OverallSummaryAnalyzer(self.collection_path)
        analyzer.performance_time_dict = {
            "Time1": "time1_key",
            "Time2": "time2_key"
        }

        performance_data = {
            "e2e_time_ms": 200.0,
            "time1_key": 100.0,
            "time2_key": 50.0
        }
        benchmark_data = {
            "time1_key": 80.0,
            "time2_key": 40.0
        }
        headers = ['Performance Index', 'Duration(ms)', 'Duration Ratio', 'Diff Duration(ms)']
        with mock.patch('msprof_analyze.advisor.analyzer.overall.overall_summary_analyzer.'
                        'OverallSummaryAnalyzer.calculate_ratio') as mock_calculate_ratio:
            mock_calculate_ratio.side_effect = [0.5, 0.25]
            analyzer.format_analysis_with_benchmark(performance_data, benchmark_data, headers)
        self.assertEqual(analyzer.over_summary_analysis["headers"], headers)
        self.assertEqual(len(analyzer.over_summary_analysis["data"]), 2)

    @mock.patch('msprof_analyze.advisor.result.result.OptimizeResult')
    def test_make_record(self, mock_optimize_result):
        """测试make_record方法"""
        analyzer = OverallSummaryAnalyzer(self.collection_path)
        analyzer.bottleneck_str = "Test bottleneck info"
        analyzer.cur_advices = ["advice1", "advice2"]
        analyzer.over_summary_analyzer = "Overall Summary"
        analyzer.over_summary_analysis = {
            "headers": ["col1", "col2"],
            "data": [["val1", "val2"]]
        }
        mock_result = mock.MagicMock()
        analyzer.result = mock_result
        analyzer.make_record()
        mock_result.add.assert_called_once()
        mock_result.add_detail.assert_any_call("Overall Summary", headers=["col1", "col2"])
        mock_result.add_detail.assert_any_call("Overall Summary", detail=["val1", "val2"])

    def test_make_record_no_data(self):
        """测试make_record方法 - 无瓶颈信息和建议"""
        analyzer = OverallSummaryAnalyzer(self.collection_path)
        analyzer.bottleneck_str = ""
        analyzer.cur_advices = ""
        mock_result = mock.MagicMock()
        analyzer.result = mock_result
        analyzer.make_record()
        mock_result.add.assert_not_called()

    def test_make_render(self):
        """测试make_render方法"""
        analyzer = OverallSummaryAnalyzer(self.collection_path)
        analyzer.bottleneck_str = "line1\nline2"
        analyzer.cur_advices = "test advice"
        analyzer.over_summary_analysis = {
            "headers": ["col1"],
            "data": [["val1"]]
        }
        mock_html_render = mock.MagicMock()
        analyzer.html_render = mock_html_render
        analyzer.make_render()
        mock_html_render.render_template.assert_called_once()
        args, kwargs = mock_html_render.render_template.call_args
        self.assertEqual(kwargs['key'], "overall")
        self.assertEqual(kwargs['title'], "Overall Summary")
        self.assertIn("line1<br />line2", kwargs['result']['Description'])

    def test_make_render_no_data(self):
        """测试make_render方法 - 无瓶颈信息和建议"""
        analyzer = OverallSummaryAnalyzer(self.collection_path)
        analyzer.bottleneck_str = ""
        analyzer.cur_advices = ""
        mock_html_render = mock.MagicMock()
        analyzer.html_render = mock_html_render
        analyzer.make_render()
        mock_html_render.render_template.assert_not_called()

    def test_get_priority(self):
        """测试get_priority方法"""
        analyzer = OverallSummaryAnalyzer(self.collection_path)
        analyzer.get_priority(max_mem_op_dur=100.0)

    @mock.patch('msprof_analyze.prof_common.path_manager.PathManager.limited_depth_walk')
    def test_get_profile_path(self, mock_limited_depth_walk):
        """测试get_profile_path全局函数"""
        mock_limited_depth_walk.return_value = [
            ("/test/path1", ["subdir"], ["file1.txt"]),
            ("/test/path2", [], ["profiler_info_123.json", "other_file.txt"])
        ]

        result = get_profile_path("test_collection_path")
        self.assertEqual(result, "/test/path2")
        mock_limited_depth_walk.assert_called_once_with("test_collection_path")
        mock_limited_depth_walk.reset_mock()
        mock_limited_depth_walk.return_value = [
            ("/test/path1", ["subdir"], ["file1.txt"]),
            ("/test/path2", [], ["other_file.txt"])
        ]
        result = get_profile_path("test_collection_path")
        self.assertEqual(result, "")


if __name__ == '__main__':
    unittest.main()
