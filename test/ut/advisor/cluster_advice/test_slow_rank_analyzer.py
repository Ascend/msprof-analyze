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

from msprof_analyze.advisor.analyzer.cluster.slow_rank_analyzer import SlowRankAnalyzer
from msprof_analyze.advisor.dataset.cluster.cluster_dataset import ClusterStepTraceTimeDataset


class TestSlowRankAnalyzer(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.collection_path = "test_collection_path"
        cls.mock_step_trace_dict = {
            '-1_0': [59862.52, 115034.42, 1252571.94],
            '-1_1': [60029.1, 971241.44, 396442.14],
            '-1_2': [60123.45, 116789.32, 1256789.12],
            '-1_3': [59987.32, 115678.90, 1253456.78]
        }
        cls.mock_stages = [[0, 1, 2, 3]]

        # Create mock dataset
        cls.mock_dataset = MagicMock()
        cls.mock_dataset.get_key.return_value = ClusterStepTraceTimeDataset.get_key()
        cls.mock_dataset.get_data.return_value = cls.mock_step_trace_dict
        cls.mock_dataset.get_stages.return_value = cls.mock_stages

    def setUp(self):
        # Create analyzer instance for each test
        with patch('msprof_analyze.advisor.analyzer.base_analyzer.BaseAnalyzer.init_dataset_list'), \
             patch('msprof_analyze.advisor.analyzer.base_analyzer.BaseAnalyzer.get_first_data_by_key',
                   return_value=self.mock_dataset):
            self.analyzer = SlowRankAnalyzer(self.collection_path)

    def test_init_with_valid_data_then_initialize_correctly(self):
        # Verify initialization
        self.assertEqual(self.analyzer.step_trace_dict, self.mock_step_trace_dict)
        self.assertEqual(self.analyzer.stages, self.mock_stages)
        self.assertEqual(self.analyzer.bottelneck, '')
        self.assertEqual(self.analyzer.suggestion, '')
        self.assertEqual(self.analyzer._steps, set(['-1']))

    def test_compute_max_gap_ratio_with_non_zero_mean_then_return_correct_ratio(self):
        # Test with non-zero mean
        data = [14242056.739999993, 14311412.460000006]  # min and max compute times
        mean = (14242056.739999993 + 14311412.460000006) / 2
        expected_ratio = (14311412.460000006 - 14242056.739999993) / mean
        self.assertAlmostEqual(self.analyzer.compute_max_gap_ratio(data, mean), expected_ratio)

    def test_compute_max_gap_ratio_with_zero_mean_then_return_zero(self):
        # Test with zero mean
        data = [0, 0, 0, 0]
        mean = 0
        self.assertEqual(self.analyzer.compute_max_gap_ratio(data, mean), 0)

    def test_format_details_with_valid_data_then_return_formatted_details(self):
        details = self.analyzer.format_details()

        # Verify headers
        expected_headers = ["step", "rank_id", "compute(us)", "communication(us)", "free(us)"]
        self.assertEqual(details["headers"], expected_headers)

        # Verify data format
        self.assertEqual(len(details["data"]), 4)  # 4 entries in mock data
        self.assertEqual(len(details["data"][0]), 5)  # 5 columns per row

        # Verify steps are collected
        self.assertEqual(self.analyzer._steps, {'-1'})

    def test_get_step_duration_with_valid_rank_then_return_correct_duration(self):
        # Test with valid rank and step
        duration = self.analyzer.get_step_duration(0, -1)
        expected_duration = 59862.52 + 115034.42 + 1252571.94
        self.assertAlmostEqual(duration, expected_duration)

    def test_get_step_duration_with_invalid_rank_then_return_zero(self):
        # Test with invalid rank
        duration = self.analyzer.get_step_duration(999)
        self.assertEqual(duration, 0.0)

    def test_get_global_step_rank_with_free_dimension_then_return_rank_info(self):
        # Test with free dimension
        result = self.analyzer.get_global_step_rank("free(us)")
        self.assertIn("maximum", result)
        self.assertIn("minimum", result)

        self.assertEqual(result["maximum"]["rank_id"], 2)
        self.assertEqual(result["minimum"]["rank_id"], 1)

    def test_process_with_significant_differences_then_identify_bottlenecks(self):
        # Test process method with mock data that has significant differences
        self.analyzer.process()

        # Verify bottleneck message contains expected content
        self.assertIn("通信", self.analyzer.bottelneck)
        self.assertIn("空闲", self.analyzer.bottelneck)

        # Verify specific bottleneck messages
        self.assertIn("集群中的通信有问题", self.analyzer.bottelneck)
        self.assertIn("因为通信时间的最大差距已经达到", self.analyzer.bottelneck)
        self.assertIn("856.207ms", self.analyzer.bottelneck)

        self.assertIn("集群中的空闲有问题", self.analyzer.bottelneck)
        self.assertIn("因为空闲时间的最大差距已经达到", self.analyzer.bottelneck)
        self.assertIn("860.347ms", self.analyzer.bottelneck)

    def test_process_with_no_significant_differences_then_report_no_issues(self):
        # Test with data that has no significant differences
        mock_no_diff = {
            '-1_0': [100, 100, 100],
            '-1_1': [100, 100, 100],
            '-1_2': [100, 100, 100],
            '-1_3': [100, 100, 100]
        }
        self.analyzer.step_trace_dict = mock_no_diff
        self.analyzer.bottelneck = ''
        self.analyzer.process()
        self.assertIn("没有慢节点问题", self.analyzer.bottelneck)

    def test_optimize_with_valid_data_then_return_optimize_result(self):
        expected_problem_header = ['category', 'description', 'suggestion', 'problem count', 'total_time(us)',
                                   'time ratio', 'income(us)', 'income ratio']
        expected_details_header = ['step', 'rank_id', 'compute(us)', 'communication(us)', 'free(us)']
        # Test optimize with valid data
        result = self.analyzer.optimize(template_key="overall")
        slow_rank_res = dict(result.data)
        problems = slow_rank_res.get("问题综述", {})
        self.assertEqual(len(problems), 2)
        self.assertEqual(problems.get("headers"), expected_problem_header)


        details = slow_rank_res.get("慢卡分析", {})
        self.assertEqual(len(details), 2)
        self.assertEqual(details.get("headers"), expected_details_header)

    def test_get_stage_step_rank_with_free_dimension_then_return_stage_rank_info(self):
        # Test with free dimension
        _details = self.analyzer.format_details()
        result = self.analyzer.get_stage_step_rank("free(us)")
        # Verify result structure
        self.assertIn("stage-0", result)
        stage_result = result["stage-0"]

        # Verify maximum and minimum entries exist
        self.assertIn("maximum", stage_result)
        self.assertIn("minimum", stage_result)

        # Verify rank_id and step are present
        self.assertIn("rank_id", stage_result["maximum"])
        self.assertIn("step", stage_result["maximum"])
        self.assertIn("rank_id", stage_result["minimum"])
        self.assertIn("step", stage_result["minimum"])

        # Verify specific values
        self.assertEqual(stage_result["maximum"]["rank_id"], 2)
        self.assertEqual(stage_result["maximum"]["step"], -1)
        self.assertEqual(stage_result["minimum"]["rank_id"], 1)
        self.assertEqual(stage_result["minimum"]["step"], -1)


    def test_get_stage_step_rank_with_invalid_dimension_then_return_empty_dict(self):
        # Test with invalid dimension
        result = self.analyzer.get_stage_step_rank("invalid_dimension")
        self.assertEqual(result, {})

    def test_get_stage_step_rank_with_empty_format_datas_then_return_empty_dict(self):
        # Test with empty format_datas
        self.analyzer.format_datas = {}
        result = self.analyzer.get_stage_step_rank("compute(us)")
        self.assertEqual(result, {})

    def test_get_stage_step_rank_no_significant_difference(self):
        # Create mock data with no significant differences
        mock_no_diff = {
            '-1_0': [100, 100, 100],
            '-1_1': [100, 100, 100],
            '-1_2': [100, 100, 100],
            '-1_3': [100, 100, 100]
        }
        self.analyzer.step_trace_dict = mock_no_diff
        self.analyzer.format_datas = self.analyzer.format_details()

        # Test with compute dimension
        result = self.analyzer.get_stage_step_rank("compute(us)")

        # Verify empty result when no significant differences
        self.assertEqual(result, {})
