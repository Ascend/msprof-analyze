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

from msprof_analyze.advisor.analyzer.cluster.slow_link_analyzer import SlowLinkAnalyzer
from msprof_analyze.advisor.dataset.cluster.cluster_dataset import ClusterCommunicationDataset


class TestSlowLinkAnalyzer(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.collection_path = "test_collection_path"
        cls.mock_rank_bw_dict = {
            '0_0': {
                'RDMA bandwidth(GB/s)': 100.0,
                'SDMA bandwidth(GB/s)': 80.0,
                'RDMA time(ms)': 10.5,
                'SDMA time(ms)': 12.3,
                'RDMA size(mb)': 1024.0,
                'SDMA size(mb)': 896.0
            },
            '0_1': {
                'RDMA bandwidth(GB/s)': 95.0,
                'SDMA bandwidth(GB/s)': 85.0,
                'RDMA time(ms)': 11.2,
                'SDMA time(ms)': 11.8,
                'RDMA size(mb)': 1024.0,
                'SDMA size(mb)': 896.0
            },
            '0_2': {
                'RDMA bandwidth(GB/s)': 105.0,
                'SDMA bandwidth(GB/s)': 75.0,
                'RDMA time(ms)': 9.8,
                'SDMA time(ms)': 13.5,
                'RDMA size(mb)': 1024.0,
                'SDMA size(mb)': 896.0
            }
        }

        # Create mock dataset
        cls.mock_dataset = MagicMock()
        cls.mock_dataset.get_key.return_value = ClusterCommunicationDataset.get_key()
        cls.mock_dataset.get_data.return_value = cls.mock_rank_bw_dict

    def setUp(self):
        # Create analyzer instance for each test with patches
        with patch('msprof_analyze.advisor.analyzer.base_analyzer.BaseAnalyzer.init_dataset_list'), \
                patch('msprof_analyze.advisor.analyzer.base_analyzer.BaseAnalyzer.get_first_data_by_key',
                      return_value=self.mock_dataset), \
                patch('msprof_analyze.prof_common.additional_args_manager.AdditionalArgsManager') as mock_args_manager:
            mock_args_manager.return_value.language = "cn"
            self.analyzer = SlowLinkAnalyzer(self.collection_path)
            # avoid real rendering during optimize/make_render
            self.analyzer.html_render = MagicMock()

    def test_init_with_valid_data_then_initialize_correctly(self):
        self.assertEqual(self.analyzer.rank_bw_dict, self.mock_rank_bw_dict)
        self.assertEqual(self.analyzer.bottelneck, '')
        self.assertEqual(self.analyzer.suggestion, '')
        self.assertIsNotNone(self.analyzer.result)
        self.assertIsNotNone(self.analyzer.format_datas)

    def test_init_with_none_data_then_initialize_with_empty_format_datas(self):
        mock_dataset_none = MagicMock()
        mock_dataset_none.get_key.return_value = ClusterCommunicationDataset.get_key()
        mock_dataset_none.get_data.return_value = None

        with patch('msprof_analyze.advisor.analyzer.base_analyzer.BaseAnalyzer.init_dataset_list'), \
                patch('msprof_analyze.advisor.analyzer.base_analyzer.BaseAnalyzer.get_first_data_by_key',
                      return_value=mock_dataset_none):
            analyzer = SlowLinkAnalyzer(self.collection_path)
            self.assertIsNone(analyzer.rank_bw_dict)
            self.assertEqual(analyzer.format_datas, {})

    def test_compute_max_gap_ratio_with_non_zero_mean_then_return_correct_ratio(self):
        data = [95.0, 100.0, 105.0]
        mean = sum(data) / len(data)
        expected_ratio = (max(data) - min(data)) / mean
        actual_ratio = SlowLinkAnalyzer.compute_max_gap_ratio(data, mean)
        self.assertAlmostEqual(actual_ratio, expected_ratio, places=6)

    def test_process_with_valid_data_then_process_bottlenecks(self):
        self.analyzer.process()
        self.assertIn("RDMA bandwidth(GB/s)", self.analyzer.bottelneck)
        self.assertIn("SDMA bandwidth(GB/s)", self.analyzer.bottelneck)

    def test_produce_bottleneck_with_rdma_bandwidth_then_generate_bottleneck_message(self):
        with patch('msprof_analyze.prof_common.additional_args_manager.AdditionalArgsManager') as mock_args_manager:
            mock_args_manager.return_value.language = "cn"
            self.analyzer.produce_bottleneck(SlowLinkAnalyzer.RDMA_BANDWIDTH)
            self.assertIn("RDMA bandwidth(GB/s)", self.analyzer.bottelneck)
            self.assertIn("平均值是", self.analyzer.bottelneck)
            self.assertIn("最大值是", self.analyzer.bottelneck)
            self.assertIn("最小值是", self.analyzer.bottelneck)
            self.assertIn("差距为", self.analyzer.bottelneck)

    def test_format_details_with_valid_data_then_return_formatted_details(self):
        details = self.analyzer.format_details()
        self.assertIn("headers", details)
        self.assertIn("data", details)
        expected_headers = ["step", "rank_id", "RDMA bandwidth(GB/s)", "RDMA size(mb)",
                            "RDMA time(ms)", "SDMA bandwidth(GB/s)", "SDMA size(mb)", "SDMA time(ms)"]
        self.assertEqual(details["headers"], expected_headers)
        self.assertEqual(len(details["data"]), 3)
        self.assertEqual(len(details["data"][0]), 8)
        for i in range(len(details["data"]) - 1):
            current = details["data"][i]
            next_item = details["data"][i + 1]
            self.assertLessEqual((current[0], current[1]), (next_item[0], next_item[1]))


    def test_make_record_with_valid_data_then_add_record_to_result(self):
        self.analyzer.bottelneck = "Test bottleneck"
        self.analyzer.suggestion = "Test suggestion"
        with patch('msprof_analyze.prof_common.additional_args_manager.AdditionalArgsManager') as mock_args_manager:
            mock_args_manager.return_value.language = "cn"
            self.analyzer.make_record()
            self.assertIsNotNone(self.analyzer.result)

    def test_make_record_with_english_language_then_use_english_title(self):
        with patch('msprof_analyze.prof_common.additional_args_manager.AdditionalArgsManager') as mock_args_manager:
            mock_args_manager.return_value.language = "en"
            self.analyzer.make_record()
            self.assertIsNotNone(self.analyzer.result)

    def test_make_render_with_valid_data_then_call_html_render(self):
        self.analyzer.bottelneck = "Test bottleneck"
        self.analyzer.suggestion = "Test suggestion"
        self.analyzer.make_render(template_key="cluster")
        self.analyzer.html_render.render_template.assert_called_once()
        call_args = self.analyzer.html_render.render_template.call_args
        self.assertEqual(call_args.kwargs['key'], "cluster")
        self.assertEqual(call_args.kwargs['title'], SlowLinkAnalyzer.SLOW_LINK_ANALYSIS)

    def test_get_global_step_rank_with_rdma_bandwidth_then_return_rank_info(self):
        result = self.analyzer.get_global_step_rank(SlowLinkAnalyzer.RDMA)
        self.assertIn("maximum", result)
        self.assertIn("minimum", result)
        self.assertIn("rank_id", result["maximum"])
        self.assertIn("step", result["maximum"])
        self.assertIn("rank_id", result["minimum"])
        self.assertIn("step", result["minimum"])
        self.assertEqual(result["maximum"]["rank_id"], 2)
        self.assertEqual(result["minimum"]["rank_id"], 1)

if __name__ == '__main__':
    unittest.main()
