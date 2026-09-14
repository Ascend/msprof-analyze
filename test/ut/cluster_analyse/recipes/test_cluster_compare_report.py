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

from msprof_analyze.cluster_analyse.recipes.cluster_compare_baseline.cluster_compare_report import (
    ClusterCompareReportMixin,
)


class TestClusterCompareReportMixin(unittest.TestCase):
    """ClusterCompareReportMixin 单元测试"""

    def setUp(self):
        self.report = ClusterCompareReportMixin()
        self.report.text_reports = []
        self.report.operator_reports = []
        self.report._current_report_rank_id = 0

    # ---------- _record_text ----------
    def test_record_text_append(self):
        self.report._record_text("hello")
        self.assertEqual(self.report.text_reports, ["hello"])

    def test_record_text_strip_newline(self):
        self.report._record_text("hello\n")
        self.assertEqual(self.report.text_reports, ["hello"])

    def test_record_text_multiple(self):
        self.report._record_text("a")
        self.report._record_text("b")
        self.assertEqual(self.report.text_reports, ["a", "b"])

    # ---------- _record_operator ----------
    def test_record_operator_fields(self):
        row = self.report._record_operator(
            step_id=1,
            phase="阶段一",
            parallel_type="dp",
            op_type="allReduce",
            data_type="FP16",
            count=100,
            group_rank=0,
            start_ns=1000,
            end_ns=2000,
            current_domain=8,
            baseline_domain=4,
            current_duration=1.0,
            baseline_duration=0.5,
            actual_ratio=2.0,
            theoretical_ratio=1.5,
            is_abnormal=True,
            conclusion="test",
            suggestion="test suggestion",
        )
        self.assertEqual(row["step_id"], 1)
        self.assertEqual(row["parallel_type"], "dp")
        self.assertEqual(row["rank_id"], 0)
        self.assertTrue(row["is_abnormal"])

    def test_record_operator_rank_id_injection(self):
        self.report._current_report_rank_id = 5
        row = self.report._record_operator(step_id=1)
        self.assertEqual(row["rank_id"], 5)

    # ---------- _record_operator_table ----------
    def test_record_operator_table_empty(self):
        self.report._record_operator_table("title", [])
        self.assertEqual(self.report.text_reports, [])

    def test_record_operator_table_normal(self):
        rows = [{
            "step_id": 1,
            "phase": "阶段一",
            "parallel_type": "dp",
            "op_type": "allReduce",
            "data_type": "FP16",
            "count": 100,
            "group_rank": 0,
            "current_domain": 8,
            "baseline_domain": 4,
            "current_duration": 1.0,
            "baseline_duration": 0.5,
            "actual_ratio": 2.0,
            "theoretical_ratio": 1.5,
            "is_abnormal": True,
            "conclusion": "test",
        }]
        self.report._record_operator_table("title", rows)
        self.assertIn("title", self.report.text_reports)

    # ---------- _reset_reports ----------
    def test_reset_reports(self):
        self.report._record_text("test")
        self.report._record_operator(step_id=1)
        self.report._reset_reports(3)
        self.assertEqual(self.report.text_reports, [])
        self.assertEqual(self.report.operator_reports, [])
        self.assertEqual(self.report._current_report_rank_id, 3)


if __name__ == "__main__":
    unittest.main()
