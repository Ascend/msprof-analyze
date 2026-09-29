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
from unittest import mock

from msprof_analyze.advisor.advisor_backend.overall_advice.overall_summary_advice import OverallSummaryAdvice

NAMESPACE = 'msprof_analyze.advisor.advisor_backend.overall_advice.overall_summary_advice'


class TestOverallSummaryAdvice(unittest.TestCase):

    def setUp(self):
        self.collection_path = "test_collection"
        self.base_collection_path = "test_base_collection"
        self.kwargs = {"base_collection_path": self.base_collection_path}
        self.mock_prompt_class = mock.MagicMock()
        self.mock_prompt_class.PERFORMANCE_TIME_DICT = {
            "Computing Time": ['Cube Time(Num)'],
            "Uncovered Communication Time(Wait Time)": [],
            "Free Time": []
        }
        self.mock_prompt_class.TIME_NAME_MAP = {
            "Computing Time": "computing",
            "Cube Time(Num)": "Cube Time",
            "Free Time": "free",
            "Uncovered Communication Time": "communication"
        }
        self.mock_prompt_class.ADVICE_MAP = {
            "Computing Time": "advice1",
            "Free Time": "advice2",
            "Uncovered Communication Time": "advice3"
        }

    def test_split_duration_and_num(self):
        duration, num = OverallSummaryAdvice.split_duration_and_num("0.229s(1756)")
        self.assertEqual(duration, 0.229)
        self.assertEqual(num, 1756)
        duration, num = OverallSummaryAdvice.split_duration_and_num("0.5s")
        self.assertEqual(duration, 0.5)
        self.assertIsNone(num)
        duration, num = OverallSummaryAdvice.split_duration_and_num("invalid")
        self.assertEqual(duration, 0.0)

    def test_calculate_ratio(self):
        self.assertEqual(OverallSummaryAdvice.calculate_ratio(10, 2), 5.0)
        self.assertEqual(OverallSummaryAdvice.calculate_ratio(10, 0), float("inf"))

    def test_path_check(self):
        with mock.patch('os.path.exists') as mock_exists, \
             mock.patch(NAMESPACE + '.BasePrompt') as mock_prompt:
            mock_prompt.get_prompt_class.return_value = self.mock_prompt_class

            def mock_exists_side_effect(p):
                return p == self.collection_path

            mock_exists.side_effect = mock_exists_side_effect
            advice = OverallSummaryAdvice(self.collection_path, self.kwargs)
            self.assertFalse(advice.path_check())
            self.assertFalse(advice._has_base_collection)

            def mock_return_true(p):
                return True

            mock_exists.side_effect = mock_return_true
            advice = OverallSummaryAdvice(self.collection_path, self.kwargs)
            self.assertTrue(advice.path_check())
            self.assertTrue(advice._has_base_collection)
            advice = OverallSummaryAdvice(self.collection_path, {})
            self.assertTrue(advice.path_check())

    def test_process(self):
        with mock.patch(NAMESPACE + '.ComparisonInterface') as mock_interface, \
             mock.patch(NAMESPACE + '.BasePrompt') as mock_prompt, \
             mock.patch('os.path.exists', return_value=True):
            mock_prompt.get_prompt_class.return_value = self.mock_prompt_class
            advice = OverallSummaryAdvice(self.collection_path, {})
            mock_interface.return_value.compare.return_value = {}
            advice.process()
            self.assertEqual(advice.cur_data, {})
            mock_interface.return_value.compare.return_value = {
                "Overall Performance": {
                    "headers": ["Computing Time", "Free Time", "E2E Time"],
                    "rows": [["10.5s", "5.0s"], ["11.0s", "4.5s"]]
                }
            }
            advice.process()
            self.assertIn("overall_data", advice.cur_data)
            self.assertTrue(advice._is_minimal_profiling)
            mock_interface.return_value.compare.return_value = {
                "Overall Performance": {
                    "headers": ["Computing Time", "E2E Time(Not minimal profiling)"],
                    "rows": [["10.5s"], ["11.0s"]]
                }
            }
            advice.process()
            self.assertFalse(advice._is_minimal_profiling)
            mock_interface.return_value.compare.return_value = {
                "Overall Performance": {
                    "headers": [],
                    "rows": [["10.5s"]]
                }
            }
            advice.process()
            self.assertEqual(advice.cur_data.get("overall_data"), {'Computing Time': 11.0})
            advice._has_base_collection = True
            mock_interface.return_value.compare.return_value = {
                "Overall Performance": {
                    "headers": ["Computing Time"],
                    "rows": [["10.5s"], ["11.0s"]]
                }
            }
            advice.process()
            self.assertIn("comparison_result", advice.cur_data)

    def test_identify_bottleneck(self):
        with mock.patch(NAMESPACE + '.OverallSummaryAdvice.calculate_ratio') as mock_calc, \
             mock.patch(NAMESPACE + '.BasePrompt') as mock_prompt, \
             mock.patch('os.path.exists', return_value=True):
            mock_prompt.get_prompt_class.return_value = self.mock_prompt_class
            mock_calc.return_value = 0.05
            advice = OverallSummaryAdvice(self.collection_path, {})
            advice.identify_bottleneck()
            self.assertEqual(advice.cur_bottleneck, {})
            advice.cur_data = {"overall_data": {"Computing Time": 10.0, "Free Time": 5.0}}
            advice._is_minimal_profiling = True
            advice._headers = ["Computing Time", "Free Time"]
            advice._comparison_data = ["10.0s", "5.0s"]
            advice.identify_bottleneck()
            self.assertIn("overall_data", advice.cur_bottleneck)
            mock_calc.return_value = 0.15
            advice.cur_data = {"overall_data": {"Free Time": 20.0}}
            advice._headers = ["Free Time"]
            advice._comparison_data = ["20.0s"]
            advice.identify_bottleneck()
            self.assertIn("percentage of free time exceed the threshold 10%", advice.cur_bottleneck["overall_data"])
            advice = OverallSummaryAdvice(self.collection_path, self.kwargs)
            advice._has_base_collection = True
            advice.cur_data = {"overall_data": {"Computing Time": 15.0}}
            advice._headers = ["Computing Time"]
            advice._base_data = ["10.0s"]
            advice._comparison_data = ["15.0s"]
            advice.identify_bottleneck()
            self.assertIn("comparison_result", advice.cur_bottleneck)
            self.assertIn("exceeds the benchmark", advice.cur_bottleneck["comparison_result"])
            advice.cur_data = {"overall_data": {"Computing Time": 5.0, "Free Time": 2.0}}
            advice._headers = ["Computing Time", "Free Time"]
            advice._base_data = ["10.0s", "3.0s"]
            advice._comparison_data = ["5.0s", "2.0s"]
            advice.identify_bottleneck()
            self.assertEqual(advice.cur_bottleneck["comparison_result"], "")
            advice.cur_data = {"overall_data": {"Uncovered Communication Time": 15.0}}
            advice._headers = ["Uncovered Communication Time(Wait Time)"]
            advice._base_data = ["10.0s"]
            advice._comparison_data = ["15.0s"]
            advice.identify_bottleneck()
            self.assertIn("comparison_result", advice.cur_bottleneck)

    def test_output_and_run(self):
        with mock.patch(NAMESPACE + '.ComparisonInterface') as mock_interface, \
             mock.patch(NAMESPACE + '.BasePrompt') as mock_prompt, \
             mock.patch('os.path.exists', return_value=True):
            mock_prompt.get_prompt_class.return_value = self.mock_prompt_class
            advice = OverallSummaryAdvice(self.collection_path, {})
            advice.cur_data = {"test": "data"}
            advice.cur_bottleneck = {"test": "bottleneck"}
            advice.cur_advices = "test advice"
            advice.output()
            self.assertEqual(advice.output_format_data[advice.DATA], advice.cur_data)
            self.assertEqual(advice.output_format_data[advice.BOTTLENECK], advice.cur_bottleneck)
            self.assertEqual(advice.output_format_data[advice.ADVICE], advice.cur_advices)
            mock_interface.return_value.compare.return_value = {
                "Overall Performance": {
                    "headers": ["Computing Time"],
                    "rows": [["10.5s"], ["11.0s"]]
                }
            }
            result = advice.run()
            self.assertIn(advice.DATA, result)
            self.assertIn(advice.BOTTLENECK, result)
            self.assertIn(advice.ADVICE, result)


if __name__ == '__main__':
    unittest.main()
