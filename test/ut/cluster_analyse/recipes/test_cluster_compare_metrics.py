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
import pandas as pd

from msprof_analyze.cluster_analyse.recipes.cluster_compare_baseline.cluster_compare_metrics import (
    ClusterCompareMetricsMixin,
)


class TestClusterCompareMetricsMixin(unittest.TestCase):
    """ClusterCompareMetricsMixin 单元测试"""

    def setUp(self):
        self.metrics = ClusterCompareMetricsMixin()

    # ---------- _safe_divide ----------
    def test_safe_divide_normal(self):
        self.assertEqual(self.metrics._safe_divide(10, 2), 5)

    def test_safe_divide_zero_denominator(self):
        self.assertEqual(self.metrics._safe_divide(10, 0), 0)

    def test_safe_divide_custom_default(self):
        self.assertEqual(self.metrics._safe_divide(10, 0, default=-1), -1)

    # ---------- _ns_to_ms ----------
    def test_ns_to_ms(self):
        self.assertEqual(self.metrics._ns_to_ms(1_000_000), 1.0)

    def test_ns_to_ms_zero(self):
        self.assertEqual(self.metrics._ns_to_ms(0), 0.0)

    # ---------- _linearity_ratio ----------
    def test_linearity_ratio_empty_df(self):
        self.assertEqual(self.metrics._linearity_ratio(pd.DataFrame(), 1, "dp"), 0)

    def test_linearity_ratio_none_df(self):
        self.assertEqual(self.metrics._linearity_ratio(None, 1, "dp"), 0)

    def test_linearity_ratio_no_match(self):
        df = pd.DataFrame({"stepId": [1], "parallelType": ["tp"], "ratioOfUnmaskedCommunication": [0.5]})
        self.assertEqual(self.metrics._linearity_ratio(df, 1, "dp"), 0)

    def test_linearity_ratio_match(self):
        df = pd.DataFrame({"stepId": [1], "parallelType": ["dp"], "ratioOfUnmaskedCommunication": [0.5]})
        self.assertEqual(self.metrics._linearity_ratio(df, 1, "dp"), 0.5)

    # ---------- compare_by_parallel_type ----------
    def test_compare_by_parallel_type_empty_current(self):
        result = self.metrics.compare_by_parallel_type(pd.DataFrame(), pd.DataFrame())
        self.assertTrue(result.empty)

    def test_compare_by_parallel_type_empty_baseline(self):
        current = pd.DataFrame({
            "parallelType": ["dp"],
            "totalTimeWithoutCommunicationBlackout_sum": [100],
        })
        result = self.metrics.compare_by_parallel_type(current, pd.DataFrame())
        self.assertTrue(result.empty)

    def test_compare_by_parallel_type_diff_sum_zero(self):
        current = pd.DataFrame({
            "parallelType": ["dp"],
            "totalTimeWithoutCommunicationBlackout_sum": [100],
        })
        baseline = pd.DataFrame({
            "parallelType": ["dp"],
            "totalTimeWithoutCommunicationBlackout_sum": [100],
        })
        result = self.metrics.compare_by_parallel_type(current, baseline)
        self.assertFalse(result.empty)
        self.assertEqual(result["diff"].sum(), 0)
        self.assertEqual(result["diff_percent"].sum(), 0)

    def test_compare_by_parallel_type_normal(self):
        current = pd.DataFrame({
            "parallelType": ["dp", "tp"],
            "totalTimeWithoutCommunicationBlackout_sum": [200, 100],
        })
        baseline = pd.DataFrame({
            "parallelType": ["dp", "tp"],
            "totalTimeWithoutCommunicationBlackout_sum": [100, 100],
        })
        result = self.metrics.compare_by_parallel_type(current, baseline)
        self.assertFalse(result.empty)
        self.assertEqual(result["diff"].sum(), 100)
        dp_row = result[result["parallelType"] == "dp"]
        self.assertEqual(dp_row["diff_percent"].values[0], 100.0)

    # ---------- comm_lower_bound ----------
    def test_comm_lower_bound_T0_zero(self):
        result = self.metrics.comm_lower_bound(100, 0)
        self.assertEqual(result["T_total_ms"], 0)
        self.assertEqual(result["ratio"], 0)

    def test_comm_lower_bound_K0_zero(self):
        with self.assertRaises(ValueError):
            self.metrics.comm_lower_bound(100, 1, K0=0)

    def test_comm_lower_bound_B_zero(self):
        with self.assertRaises(ValueError):
            self.metrics.comm_lower_bound(100, 1, B=0)

    def test_comm_lower_bound_r_le_one(self):
        result = self.metrics.comm_lower_bound(100, 10, K0=128, K=64)
        self.assertEqual(result["T_total_ms"], 10)
        self.assertEqual(result["ratio"], 1.0)

    def test_comm_lower_bound_allGather(self):
        result = self.metrics.comm_lower_bound(100, 10, K0=64, K=128, op_type="allGather")
        self.assertGreater(result["T_total_ms"], 10)
        self.assertGreater(result["ratio"], 1.0)

    def test_comm_lower_bound_reduceScatter(self):
        result = self.metrics.comm_lower_bound(100, 10, K0=64, K=128, op_type="reduceScatter")
        self.assertGreater(result["T_total_ms"], 10)

    def test_comm_lower_bound_allReduce(self):
        result = self.metrics.comm_lower_bound(100, 10, K0=64, K=128, op_type="allReduce")
        self.assertGreater(result["T_total_ms"], 10)

    def test_comm_lower_bound_invalid_op_type(self):
        with self.assertRaises(ValueError):
            self.metrics.comm_lower_bound(100, 10, op_type="invalid_op")

    def test_comm_lower_bound_invalid_datatype_uses_default(self):
        result = self.metrics.comm_lower_bound(100, 10, datatype="UNKNOWN")
        self.assertGreater(result["T_total_ms"], 10)

    def test_comm_lower_bound_custom_alpha(self):
        result_default = self.metrics.comm_lower_bound(100, 10, alpha=None)
        result_custom = self.metrics.comm_lower_bound(100, 10, alpha=1e-7)
        self.assertNotEqual(result_default["T_total_ms"], result_custom["T_total_ms"])

    # ---------- sum_by_columns ----------
    def test_sum_by_columns_empty(self):
        result = self.metrics.sum_by_columns(pd.DataFrame(), ["parallelType"], "duration")
        self.assertTrue(result.empty)

    def test_sum_by_columns_step_id_filter(self):
        df = pd.DataFrame({
            "stepId": [1, 1, 2],
            "parallelType": ["dp", "dp", "dp"],
            "duration": [10, 20, 30],
        })
        result = self.metrics.sum_by_columns(df, ["parallelType"], "duration", step_id=1)
        self.assertEqual(result["duration_sum"].values[0], 30)

    def test_sum_by_columns_normal(self):
        df = pd.DataFrame({
            "stepId": [1, 1],
            "parallelType": ["dp", "dp"],
            "duration": [10, 20],
        })
        result = self.metrics.sum_by_columns(df, ["parallelType"], "duration")
        self.assertEqual(result["duration_sum"].values[0], 30)


if __name__ == "__main__":
    unittest.main()
