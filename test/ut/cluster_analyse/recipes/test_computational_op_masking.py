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
import argparse
import pandas as pd


from unittest.mock import patch, MagicMock
from msprof_analyze.cluster_analyse.recipes.computational_op_masking.computational_op_masking import ComputationalOpMasking


class TestComputationalOpMasking(unittest.TestCase):
    def setUp(self):
        # Initialize the test environment.
        self.params = {
            "recipe_name": "test_recipe",
            "args": ["--parallel_types", "dp,edp;edp;dp"]
        }
        self.computational_op_masking = ComputationalOpMasking(self.params)

    def test_parse_parallel_type(self):
        # Test empty input.
        self.assertEqual(ComputationalOpMasking.parse_parallel_type(""),  [])

        # Test single item.
        self.assertEqual(ComputationalOpMasking.parse_parallel_type("dp"), [("dp",)])

        # Test multiple items in one group.
        self.assertEqual(ComputationalOpMasking.parse_parallel_type("dp,edp"), [("dp", "edp")])

        # Test multiple groups.
        self.assertEqual(
            ComputationalOpMasking.parse_parallel_type("dp;edp"),
            [("dp", ), ("edp", )]
        )

        # Test multiple groups with multiple items.
        self.assertEqual(
            ComputationalOpMasking.parse_parallel_type("dp,edp;mp,tp"),
            [("dp", "edp"), ("mp", "tp")]
        )

        # Test whitespace handling.
        self.assertEqual(
            ComputationalOpMasking.parse_parallel_type(" dp, edp ; mp , tp "),
            [("dp", "edp"), ("mp", "tp")]
        )

        # Test empty group (should raise error).
        with self.assertRaises(argparse.ArgumentTypeError):
            ComputationalOpMasking.parse_parallel_type("dp;;edp")

        # Test empty item in group (should raise error).
        with self.assertRaises(argparse.ArgumentTypeError):
            ComputationalOpMasking.parse_parallel_type("dp,;edp")

    def test_aggregate_stats(self):
        # Create mock context with future_dict.
        mock_context = MagicMock()
        mock_future1 = MagicMock()
        mock_future2 = MagicMock()

        # Mock future results.
        df1 = pd.DataFrame({"stepId": [1], "time": [100]})
        df2 = pd.DataFrame({"stepId": [2], "time": [200]})

        mock_future1.result.return_value = df1
        mock_future2.result.return_value = df2

        # Mock future_dict.
        mock_context.future_dict = {
            "step_linearity": [mock_future1, mock_future2]
        }
        result = self.computational_op_masking.aggregate_stats(mock_context)
        self.assertEqual(len(result), 2)
        self.assertIn(1, result["stepId"].values)
        self.assertIn(2, result["stepId"].values)

        # Test with empty futures.
        mock_context.future_dict = {
            "step_linearity": []
        }
        result = self.computational_op_masking.aggregate_stats(mock_context)
        self.assertTrue(result.empty)


    @patch(
        'msprof_analyze.cluster_analyse.recipes.computational_op_masking.computational_op_masking.DatabaseService')
    @patch(
        'msprof_analyze.cluster_analyse.recipes.computational_op_masking.computational_op_masking.CommunicationOpWithExport')
    @patch(
        'msprof_analyze.cluster_analyse.recipes.computational_op_masking.computational_op_masking.ComputeTaskInfoWithExport')
    def test_get_linearity_df_valid(self, mock_compute_export, mock_communication_export, mock_db_service):
        # Simulated database service.
        mock_db_service_instance = MagicMock()
        mock_db_service.return_value = mock_db_service_instance

        # Simulate the object returned by the query_data method.
        mock_query_result = MagicMock()
        mock_query_result.get.return_value = pd.DataFrame([{"id": 1, "startNs": 100, "endNs": 200}])
        mock_db_service_instance.query_data.return_value = mock_query_result

        # Simulate CommunicationOpWithExport and ComputeTaskInfoWithExport
        mock_communication_df = pd.DataFrame([
            {"startNs": 110, "endNs": 150, "parallelType": "dp"},
            {"startNs": 160, "endNs": 190, "parallelType": "edp"}
        ])
        mock_communication_export.return_value.read_export_db.return_value = mock_communication_df

        mock_computation_df = pd.DataFrame([
            {"task_start_time": 120, "task_end_time": 130},
            {"task_start_time": 140, "task_end_time": 150}
        ])
        mock_compute_export.return_value.read_export_db.return_value = mock_computation_df

        # Calling the get_linearity_df method
        data_map = {
            "profiler_db_path": "test_db_path",
            "step_range": {}
        }
        result_df = self.computational_op_masking.get_linearity_df(data_map, "test_analysis_class")

        # Verify the result
        self.assertFalse(result_df.empty)
        self.assertEqual(len(result_df), 3)
        self.assertEqual(result_df.iloc[0]["stepId"], 1)
        self.assertEqual(result_df.iloc[0]["parallelType"], "dp+edp")
        self.assertEqual(result_df.iloc[0]["stepStartTime"], 100)
        self.assertEqual(result_df.iloc[0]["stepEndTime"], 200)
        self.assertEqual(result_df.iloc[0]["totalCommunicationOperatorTime"], 70)
        self.assertEqual(result_df.iloc[0]["timeRatioOfStepCommunicationOperator"], 0.7)
        self.assertEqual(result_df.iloc[0]["totalTimeWithoutCommunicationBlackout"], 50)
        self.assertEqual(result_df.iloc[0]["ratioOfUnmaskedCommunication"], round(50 / (200 - 100), 5))

        self.assertEqual(result_df.iloc[1]["stepId"], 1)
        self.assertEqual(result_df.iloc[1]["parallelType"], "edp")
        self.assertEqual(result_df.iloc[1]["stepStartTime"], 100)
        self.assertEqual(result_df.iloc[1]["stepEndTime"], 200)
        self.assertEqual(result_df.iloc[1]["totalCommunicationOperatorTime"], 30)
        self.assertEqual(result_df.iloc[1]["timeRatioOfStepCommunicationOperator"], 0.3)
        self.assertEqual(result_df.iloc[1]["totalTimeWithoutCommunicationBlackout"], 30)
        self.assertEqual(result_df.iloc[1]["ratioOfUnmaskedCommunication"], round(30 / (200 - 100), 5))

    @patch(
        'msprof_analyze.cluster_analyse.recipes.computational_op_masking.computational_op_masking.DatabaseService')
    @patch(
        'msprof_analyze.cluster_analyse.recipes.computational_op_masking.computational_op_masking.CommunicationOpWithExport')
    @patch(
        'msprof_analyze.cluster_analyse.recipes.computational_op_masking.computational_op_masking.ComputeTaskInfoWithExport')
    def test_get_linearity_df_invalid(self, mock_compute_export, mock_communication_export, mock_db_service):
        # Simulated database service.
        mock_db_service_instance = MagicMock()
        mock_db_service.return_value = mock_db_service_instance

        # Simulate the object returned by the query_data method.
        mock_query_result = MagicMock()
        mock_query_result.get.return_value = pd.DataFrame([{"id": 1, "startNs": 100, "endNs": 200}])
        mock_db_service_instance.query_data.return_value = mock_query_result

        # Simulate CommunicationOpWithExport and ComputeTaskInfoWithExport
        mock_communication_df = pd.DataFrame([
            {"startNs": 110, "endNs": 150, "parallelType": "dp"},
            {"startNs": 160, "endNs": 190, "parallelType": "edp"}
        ])
        mock_communication_export.return_value.read_export_db.return_value = mock_communication_df

        mock_computation_df = pd.DataFrame([
            {"task_start_time": 120, "task_end_time": 130},
            {"task_start_time": 140, "task_end_time": 150}
        ])
        mock_compute_export.return_value.read_export_db.return_value = mock_computation_df

        # Calling the get_linearity_df method
        data_map = {
            "profiler_db_path": "test_db_path",
            "step_range": {"id": 1, "startNs": 100, "endNs": 200}
        }
        result_df = self.computational_op_masking.get_linearity_df(data_map, "test_analysis_class")

        # Verify the result
        self.assertFalse(result_df.empty)
        self.assertEqual(len(result_df), 3)
        self.assertEqual(result_df.iloc[0]["stepId"], 1)
        self.assertEqual(result_df.iloc[0]["parallelType"], "dp+edp")
        self.assertEqual(result_df.iloc[0]["stepStartTime"], 100)
        self.assertEqual(result_df.iloc[0]["stepEndTime"], 200)
        self.assertEqual(result_df.iloc[0]["totalCommunicationOperatorTime"], 70)
        self.assertEqual(result_df.iloc[0]["timeRatioOfStepCommunicationOperator"], 0.7)
        self.assertEqual(result_df.iloc[0]["totalTimeWithoutCommunicationBlackout"], 50)
        self.assertEqual(result_df.iloc[0]["ratioOfUnmaskedCommunication"], round(50 / (200 - 100), 5))

        self.assertEqual(result_df.iloc[1]["stepId"], 1)
        self.assertEqual(result_df.iloc[1]["parallelType"], "edp")
        self.assertEqual(result_df.iloc[1]["stepStartTime"], 100)
        self.assertEqual(result_df.iloc[1]["stepEndTime"], 200)
        self.assertEqual(result_df.iloc[1]["totalCommunicationOperatorTime"], 30)
        self.assertEqual(result_df.iloc[1]["timeRatioOfStepCommunicationOperator"], 0.3)
        self.assertEqual(result_df.iloc[1]["totalTimeWithoutCommunicationBlackout"], 30)
        self.assertEqual(result_df.iloc[1]["ratioOfUnmaskedCommunication"], round(30 / (200 - 100), 5))


if __name__ == '__main__':
    unittest.main()