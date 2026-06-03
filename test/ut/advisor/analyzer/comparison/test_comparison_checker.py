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
from unittest.mock import MagicMock, patch

from msprof_analyze.advisor.analyzer.comparison.comparison_checker import ComparisonChecker
from msprof_analyze.advisor.result.result import OptimizeResult
from msprof_analyze.prof_common.constant import Constant


NAMESPACE = "msprof_analyze.advisor.analyzer.comparison.comparison_checker"


class TestComparisonChecker(unittest.TestCase):
    def test_get_valid_step_should_handle_none_negative_numeric_and_invalid_types(self):
        self.assertEqual(ComparisonChecker.get_valid_step(None), "")
        self.assertEqual(ComparisonChecker.get_valid_step(-1), "")
        self.assertEqual(ComparisonChecker.get_valid_step(3), "3")
        self.assertEqual(ComparisonChecker.get_valid_step(4.8), "4")
        self.assertEqual(ComparisonChecker.get_valid_step("step1"), "")

    def test_compare_should_return_early_when_compare_mode_none(self):
        checker = ComparisonChecker("profiling", "benchmark")

        checker.compare(None)

        self.assertIsNone(checker.compare_mode)
        self.assertEqual(checker.format_result, {})

    @patch(f"{NAMESPACE}.logger")
    def test_compare_should_skip_api_compare_for_mindspore_benchmark(self, mock_logger):
        checker = ComparisonChecker("profiling", "/tmp/benchmark_ascend_ms")

        checker.compare("Api Compare")

        self.assertEqual(checker.compare_mode, "Api Compare")
        self.assertEqual(checker.format_result, {})
        mock_logger.info.assert_called_once()

    @patch(f"{NAMESPACE}.ComparisonInterface")
    def test_compare_should_format_headers_and_rows_for_kernel_compare(self, mock_compare_interface_cls):
        compare_result = {
            Constant.KERNEL_TYPE_COMPARE: {
                "headers": [
                    {"name": "Op Name"},
                    {"name": "Duration"},
                    {"name": "Duration"},
                    {"name": "Diff Avg Ratio"},
                ],
                "rows": [["MatMul", "10", "8", "1.25"]]
            }
        }
        mock_compare_interface = MagicMock()
        mock_compare_interface.compare.return_value = compare_result
        mock_compare_interface_cls.return_value = mock_compare_interface
        checker = ComparisonChecker("profiling", "benchmark", step=2, benchmark_step=3)

        checker.compare(Constant.KERNEL_COMPARE)

        mock_compare_interface_cls.assert_called_once_with(
            "profiling", "benchmark", "2", "3", use_kernel_type=True
        )
        self.assertEqual(
            checker.format_result[Constant.KERNEL_COMPARE]["headers"],
            ["Op Name", "Duration", "Benchmark  Duration", "Diff Avg Ratio"]
        )
        self.assertEqual(
            checker.format_result[Constant.KERNEL_COMPARE]["rows"],
            [["MatMul", "10", "8", "1.25"]]
        )

    @patch(f"{NAMESPACE}.ComparisonInterface")
    def test_compare_should_use_compare_mode_key_for_non_kernel_compare(self, mock_compare_interface_cls):
        compare_result = {
            Constant.API_COMPARE: {
                "headers": [{"name": "API Name"}, {"name": "Diff Avg Ratio"}],
                "rows": [["aclnnCast", "1.50"]]
            }
        }
        mock_compare_interface = MagicMock()
        mock_compare_interface.compare.return_value = compare_result
        mock_compare_interface_cls.return_value = mock_compare_interface
        checker = ComparisonChecker("profiling", "benchmark")

        checker.compare(Constant.API_COMPARE)

        mock_compare_interface_cls.assert_called_once_with(
            "profiling", "benchmark", "", "", use_kernel_type=False
        )
        self.assertEqual(
            checker.format_result[Constant.API_COMPARE],
            {"headers": ["API Name", "Diff Avg Ratio"], "rows": [["aclnnCast", "1.50"]]}
        )

    @patch(f"{NAMESPACE}.ComparisonInterface")
    def test_compare_should_skip_store_when_rows_empty(self, mock_compare_interface_cls):
        mock_compare_interface = MagicMock()
        mock_compare_interface.compare.return_value = {
            Constant.API_COMPARE: {"headers": [{"name": "API Name"}], "rows": []}
        }
        mock_compare_interface_cls.return_value = mock_compare_interface
        checker = ComparisonChecker("profiling", "benchmark")

        checker.compare(Constant.API_COMPARE)

        self.assertEqual(checker.format_result, {})

    def test_make_record_should_return_when_no_format_result(self):
        checker = ComparisonChecker("profiling", "benchmark")
        result = MagicMock(spec=OptimizeResult)

        checker.make_record(result)

        result.add.assert_not_called()
        result.add_detail.assert_not_called()

    def test_make_record_should_add_overview_and_detail_rows(self):
        checker = ComparisonChecker("profiling", "benchmark", step=1, benchmark_step=2, rank=0, benchmark_rank=1)
        checker.compare_mode = Constant.KERNEL_COMPARE
        checker.format_result = {
            Constant.KERNEL_COMPARE: {
                "headers": ["Op Name", "Diff Avg Ratio"],
                "rows": [["MatMul", "1.25"], ["Add", "1.10"]]
            }
        }
        result = MagicMock(spec=OptimizeResult)

        checker.make_record(result)

        self.assertEqual(checker.desc, "Kernel compare of Rank0 Step1 and Rank1 Step2")
        self.assertEqual(result.add.call_count, 1)
        result.add_detail.assert_any_call(
            "Kernel compare of Rank0 Step1 and Rank1 Step2",
            headers=["Op Name", "Diff Avg Ratio"]
        )
        result.add_detail.assert_any_call(
            "Kernel compare of Rank0 Step1 and Rank1 Step2",
            detail=["MatMul", "1.25"]
        )
        result.add_detail.assert_any_call(
            "Kernel compare of Rank0 Step1 and Rank1 Step2",
            detail=["Add", "1.10"]
        )

    def test_make_render_should_return_when_no_format_result(self):
        checker = ComparisonChecker("profiling", "benchmark")
        html_render = MagicMock()

        checker.make_render(html_render)

        html_render.render_template.assert_not_called()

    @patch(f"{NAMESPACE}.logger")
    def test_make_render_should_skip_when_diff_avg_ratio_header_missing(self, mock_logger):
        checker = ComparisonChecker("profiling", "benchmark")
        checker.compare_mode = Constant.API_COMPARE
        checker.desc = "Api compare of Target and Benchmark"
        checker.format_result = {
            Constant.API_COMPARE: {"headers": ["API Name"], "rows": [["aclnnCast"]]}
        }
        html_render = MagicMock()

        checker.make_render(html_render)

        html_render.render_template.assert_not_called()
        mock_logger.warning.assert_called_once()

    def test_make_render_should_sort_rows_by_diff_avg_ratio_and_limit_topk(self):
        checker = ComparisonChecker("profiling", "benchmark", rank=0)
        checker.compare_mode = Constant.API_COMPARE
        checker.desc = "Api compare of Rank0 and Target and Benchmark"
        rows = [[f"api_{idx}", str(idx / 10)] for idx in range(12)]
        checker.format_result = {
            Constant.API_COMPARE: {
                "headers": ["API Name", "Diff Avg Ratio"],
                "rows": rows
            }
        }
        html_render = MagicMock()

        checker.make_render(html_render)

        html_render.render_template.assert_called_once()
        call_kwargs = html_render.render_template.call_args.kwargs
        self.assertEqual(call_kwargs["key"], "comparison")
        self.assertEqual(call_kwargs["template_name"], "comparison.html")
        self.assertEqual(call_kwargs["sheet_name"], "Api compare of Rank0 and ")
        self.assertEqual(len(call_kwargs["rows"]), checker.SHOW_TOPK)
        self.assertEqual(call_kwargs["rows"][0], ["api_11", "1.1"])
        self.assertEqual(call_kwargs["rows"][-1], ["api_2", "0.2"])
        self.assertIn("Only show 10 rows here", call_kwargs["desc"])

    def test_make_render_should_skip_when_headers_or_topk_rows_empty(self):
        checker = ComparisonChecker("profiling", "benchmark")
        checker.compare_mode = Constant.API_COMPARE
        checker.desc = "Api compare of Target and Benchmark"
        checker.format_result = {
            Constant.API_COMPARE: {"headers": ["Diff Avg Ratio"], "rows": []}
        }
        html_render = MagicMock()

        checker.make_render(html_render)

        html_render.render_template.assert_not_called()

    def test_get_sheet_name_should_compose_target_benchmark_rank_and_step(self):
        checker = ComparisonChecker("profiling", "benchmark", step=3, benchmark_step=5, rank=0, benchmark_rank=2)
        checker.compare_mode = Constant.API_COMPARE

        self.assertEqual(checker._get_sheet_name(), "Api compare of Rank0 Step3 and Rank2 Step5")

    def test_get_sheet_name_should_fallback_to_target_and_benchmark(self):
        checker = ComparisonChecker("profiling", "benchmark")
        checker.compare_mode = Constant.KERNEL_COMPARE

        self.assertEqual(checker._get_sheet_name(), "Kernel compare of Target and Benchmark")


if __name__ == "__main__":
    unittest.main()
