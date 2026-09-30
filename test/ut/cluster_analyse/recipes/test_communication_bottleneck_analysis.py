# -------------------------------------------------------------------------
# This file is part of the MindStudio project.
# Copyright (c) 2026 Huawei Technologies Co.,Ltd.
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
from unittest.mock import Mock, patch

import pandas as pd

from msprof_analyze.cluster_analyse.recipes.communication_bottleneck.communication_bottleneck import (
    BottleneckReason,
    CommunicatonBottleneckAnalysis,
)
from msprof_analyze.prof_common.constant import Constant
from msprof_analyze.prof_common.path_manager import PathManager


NAMESPACE_RECIPE = (
    "msprof_analyze.cluster_analyse.recipes.communication_bottleneck.communication_bottleneck"
)


class TestCommunicatonBottleneckAnalysis(unittest.TestCase):
    PARAMS = {
        Constant.COLLECTION_PATH: "/data",
        Constant.DATA_MAP: {0: "/rank0", 1: "/rank1"},
        Constant.CLUSTER_ANALYSIS_OUTPUT_PATH: "./tmp_communication_bottleneck_ut",
        Constant.RECIPE_NAME: "CommunicationBottleneck",
        Constant.PARALLEL_MODE: Constant.CONCURRENT_MODE,
        Constant.EXPORT_TYPE: Constant.DB,
        Constant.RANK_LIST: Constant.ALL,
        Constant.EXTRA_ARGS: [],
        Constant.PROFILING_TYPE: Constant.PYTORCH,
    }

    def setUp(self):
        self.recipe = CommunicatonBottleneckAnalysis(self.PARAMS)

    def tearDown(self):
        PathManager.remove_path_safety(self.PARAMS.get(Constant.CLUSTER_ANALYSIS_OUTPUT_PATH))

    def test_init_when_extra_args_provided_then_set_target_rank_and_top_num(self):
        params = dict(self.PARAMS)
        params[Constant.EXTRA_ARGS] = ["--rank_id", "3", "--top_num", "5"]

        recipe = CommunicatonBottleneckAnalysis(params)

        self.assertEqual(recipe.target_rank_id, 3)
        self.assertEqual(recipe.max_analysis_num, 5)
        self.assertEqual(recipe.slow_npu_happen_threshold, 0.05)
        self.assertEqual(recipe.diff_waiting_time_threshold, 100000)
        self.assertEqual(recipe.start_ns_shifted_threshold, 1000000)
        self.assertEqual(recipe.device_bound_proportion_threshold, 0.5)

    def test_compute_diff_from_fast_and_slow_npu_when_input_empty_then_return_empty_dataframe_and_unaligned(self):
        result_df, is_unaligned = CommunicatonBottleneckAnalysis.compute_diff_from_fast_and_slow_npu(
            None, pd.DataFrame(), 0, 100
        )

        self.assertTrue(result_df.empty)
        self.assertTrue(is_unaligned)
        self.assertEqual(
            list(result_df.columns),
            ["start_ns", "duration", "task_name", "diff_start_ns", "diff_duration"],
        )

    def test_compute_diff_from_fast_and_slow_npu_when_tasks_aligned_then_return_diff_dataframe_and_aligned(self):
        slow_df = pd.DataFrame(
            [
                {"start_ns": 2000, "duration": 600, "task_name": "task_b"},
                {"start_ns": 1000, "duration": 500, "task_name": "task_a"},
            ]
        )
        fast_df = pd.DataFrame(
            [
                {"start_ns": 1500, "duration": 400, "task_name": "task_b"},
                {"start_ns": 900, "duration": 450, "task_name": "task_a"},
            ]
        )

        result_df, is_unaligned = CommunicatonBottleneckAnalysis.compute_diff_from_fast_and_slow_npu(
            slow_df, fast_df, 0, 600
        )

        self.assertFalse(is_unaligned)
        self.assertEqual(len(result_df), 1)
        self.assertEqual(result_df.iloc[0]["task_name"], "task_b")
        self.assertEqual(result_df.iloc[0]["diff_start_ns"], 500)
        self.assertEqual(result_df.iloc[0]["diff_duration"], 200)

    @patch.object(CommunicatonBottleneckAnalysis, "mapper_func")
    def test_analyze_single_comm_op_when_no_valid_mapper_result_then_return_failed_reason(self, mock_mapper_func):
        mock_mapper_func.return_value = [None, pd.DataFrame()]
        comm_row = pd.Series(
            {"start_ns": 1000, "end_ns": 3000, "duration": 2000, "comm_name": "all_reduce"}
        )

        result = self.recipe.analyze_single_comm_op(Mock(), comm_row)

        self.assertEqual(result.comm_name, "all_reduce")
        self.assertEqual(result.reason, "[Failed] No data found for the communication operator")

    @patch.object(CommunicatonBottleneckAnalysis, "mapper_func")
    def test_analyze_single_comm_op_when_duration_diff_below_threshold_then_return_no_slow_npu_reason(
        self, mock_mapper_func
    ):
        mock_mapper_func.return_value = [
            pd.DataFrame(
                [
                    {
                        "rank_id": 0,
                        "start_ns": 1000,
                        "end_ns": 2000,
                        "duration": 1000,
                        "task_name": "all_reduce",
                    },
                    {
                        "rank_id": 1,
                        "start_ns": 1100,
                        "end_ns": 2090,
                        "duration": 990,
                        "task_name": "all_reduce",
                    },
                ]
            )
        ]
        comm_row = pd.Series(
            {"start_ns": 1000, "end_ns": 3000, "duration": 2000, "comm_name": "all_reduce"}
        )

        result = self.recipe.analyze_single_comm_op(Mock(), comm_row)

        self.assertIn("[Completed] No slow NPU detected", result.reason)
        self.assertIsNone(result.slow_rank_id)
        self.assertIsNone(result.fast_rank_id)

    @patch.object(CommunicatonBottleneckAnalysis, "analyze_slow_npu")
    @patch.object(CommunicatonBottleneckAnalysis, "mapper_func")
    def test_analyze_single_comm_op_when_duration_diff_above_threshold_then_analyze_slow_npu(
        self, mock_mapper_func, mock_analyze_slow_npu
    ):
        mock_mapper_func.return_value = [
            pd.DataFrame(
                [
                    {
                        "rank_id": 0,
                        "start_ns": 1000,
                        "end_ns": 3000,
                        "duration": 2000,
                        "task_name": "all_reduce",
                    },
                    {
                        "rank_id": 1,
                        "start_ns": 1200,
                        "end_ns": 2200,
                        "duration": 1000,
                        "task_name": "all_reduce",
                    },
                ]
            )
        ]
        comm_row = pd.Series(
            {"start_ns": 1000, "end_ns": 3000, "duration": 2000, "comm_name": "all_reduce"}
        )

        result = self.recipe.analyze_single_comm_op(Mock(), comm_row)

        self.assertEqual(result.fast_rank_id, 0)
        self.assertEqual(result.slow_rank_id, 1)
        mock_analyze_slow_npu.assert_called_once_with(result, 800, 1000, 1200, 2200)

    def test_locate_anomaly_reasons_when_comm_df_empty_then_return_none(self):
        result = self.recipe.locate_anomaly_reasons(Mock(), pd.DataFrame())

        self.assertIsNone(result)

    @patch.object(CommunicatonBottleneckAnalysis, "analyze_single_comm_op")
    def test_locate_anomaly_reasons_when_comm_df_valid_then_return_reason_list(self, mock_analyze_single_comm_op):
        comm_df = pd.DataFrame(
            [
                {"comm_name": "op_1", "start_ns": 100, "end_ns": 200, "duration": 100},
                {"comm_name": "op_2", "start_ns": 300, "end_ns": 600, "duration": 300},
            ]
        )
        reason_1 = BottleneckReason()
        reason_1.reason = "reason_1"
        reason_2 = BottleneckReason()
        reason_2.reason = "reason_2"
        mock_analyze_single_comm_op.side_effect = [reason_1, reason_2]

        result = self.recipe.locate_anomaly_reasons(Mock(), comm_df)

        self.assertEqual(result, [reason_1, reason_2])
        self.assertEqual(mock_analyze_single_comm_op.call_count, 2)

    def test_judge_bottleneck_type_when_device_waiting_dominates_then_return_device_and_true(self):
        slow_task_df = pd.DataFrame(
            [
                {
                    "pytorch_end_ns": 0,
                    "cann_start_ns": 10,
                    "cann_end_ns": 20,
                    "device_start_ns": 200030,
                },
                {
                    "pytorch_end_ns": 100,
                    "cann_start_ns": 110,
                    "cann_end_ns": 120,
                    "device_start_ns": 200130,
                },
            ]
        )
        reason = BottleneckReason()
        reason.slow_rank_id = 1

        with patch.object(self.recipe, "get_rank_profile_db_path", return_value="/path/to/db"), patch(
            f"{NAMESPACE_RECIPE}.AllDeviceNodeLaunchPytorchTaskExport"
        ) as mock_export:
            mock_export.return_value.read_export_db.return_value = slow_task_df

            bottleneck, has_data = self.recipe._judge_bottleneck_type(reason, 0, 1000)

        self.assertEqual(bottleneck, "Device")
        self.assertTrue(has_data)

    def test_judge_bottleneck_type_when_device_waiting_not_dominates_then_return_host_and_true(self):
        slow_task_df = pd.DataFrame(
            [
                {
                    "pytorch_end_ns": 0,
                    "cann_start_ns": 100000,
                    "cann_end_ns": 150000,
                    "device_start_ns": 150100,
                },
                {
                    "pytorch_end_ns": 10,
                    "cann_start_ns": 100010,
                    "cann_end_ns": 150010,
                    "device_start_ns": 150110,
                },
            ]
        )
        reason = BottleneckReason()
        reason.slow_rank_id = 1

        with patch.object(self.recipe, "get_rank_profile_db_path", return_value="/path/to/db"), patch(
            f"{NAMESPACE_RECIPE}.AllDeviceNodeLaunchPytorchTaskExport"
        ) as mock_export:
            mock_export.return_value.read_export_db.return_value = slow_task_df

            bottleneck, has_data = self.recipe._judge_bottleneck_type(reason, 0, 1000)

        self.assertEqual(bottleneck, "Host")
        self.assertTrue(has_data)

    @patch.object(CommunicatonBottleneckAnalysis, "compute_diff_from_fast_and_slow_npu")
    def test_build_task_diff_summary_when_tasks_unaligned_then_return_none(self, mock_compute_diff):
        mock_compute_diff.return_value = (pd.DataFrame(), True)

        result = self.recipe._build_task_diff_summary(pd.DataFrame(), pd.DataFrame(), 0, "Device")

        self.assertIsNone(result)

    @patch.object(CommunicatonBottleneckAnalysis, "compute_diff_from_fast_and_slow_npu")
    def test_build_task_diff_summary_when_tasks_aligned_then_return_summary(self, mock_compute_diff):
        mock_compute_diff.return_value = (
            pd.DataFrame(
                [
                    {
                        "start_ns": 1000,
                        "duration": 500,
                        "task_name": "task_a",
                        "diff_start_ns": 100,
                        "diff_duration": 50,
                    },
                    {
                        "start_ns": 2000,
                        "duration": 800,
                        "task_name": "task_b",
                        "diff_start_ns": 200,
                        "diff_duration": 300,
                    },
                ]
            ),
            False,
        )

        result = self.recipe._build_task_diff_summary(pd.DataFrame(), pd.DataFrame(), 0, "Device")

        self.assertIsNotNone(result)
        self.assertEqual(result.level, "Device")
        self.assertEqual(result.max_start_diff_task["task_name"], "task_b")
        self.assertEqual(result.max_duration_task["task_name"], "task_b")

    @patch.object(CommunicatonBottleneckAnalysis, "_build_task_diff_summary")
    @patch.object(CommunicatonBottleneckAnalysis, "query_device_task_before_time")
    def test_analyze_device_bound_when_summary_missing_then_set_unaligned_reason(
        self, mock_query_device_task_before_time, mock_build_task_diff_summary
    ):
        reason = BottleneckReason()
        reason.slow_rank_id = 1
        reason.fast_rank_id = 0
        mock_query_device_task_before_time.side_effect = [pd.DataFrame(), pd.DataFrame()]
        mock_build_task_diff_summary.return_value = None

        self.recipe._analyze_device_bound(reason, 1000, 1200, 50)

        self.assertEqual(
            reason.reason,
            "[Device-bound] Tasks are not aligned between slow and fast NPU from the beginning",
        )

    @patch.object(CommunicatonBottleneckAnalysis, "_build_task_diff_summary")
    @patch.object(CommunicatonBottleneckAnalysis, "query_device_task_before_time")
    def test_analyze_device_bound_when_reason_string_missing_then_set_failed_reason(
        self, mock_query_device_task_before_time, mock_build_task_diff_summary
    ):
        reason = BottleneckReason()
        reason.slow_rank_id = 1
        reason.fast_rank_id = 0
        mock_query_device_task_before_time.side_effect = [pd.DataFrame(), pd.DataFrame()]
        mock_summary = Mock()
        mock_summary.to_reason_string.return_value = None
        mock_build_task_diff_summary.return_value = mock_summary

        self.recipe._analyze_device_bound(reason, 1000, 1200, 50)

        self.assertEqual(reason.reason, "[Device-bound] Failed to find device task differences")

    @patch.object(CommunicatonBottleneckAnalysis, "_build_task_diff_summary")
    @patch.object(CommunicatonBottleneckAnalysis, "query_device_task_before_time")
    def test_analyze_device_bound_when_summary_valid_then_set_device_bound_reason(
        self, mock_query_device_task_before_time, mock_build_task_diff_summary
    ):
        reason = BottleneckReason()
        reason.slow_rank_id = 1
        reason.fast_rank_id = 0
        mock_query_device_task_before_time.side_effect = [pd.DataFrame(), pd.DataFrame()]
        mock_summary = Mock()
        mock_summary.to_reason_string.return_value = "Device: reason detail"
        mock_build_task_diff_summary.return_value = mock_summary

        self.recipe._analyze_device_bound(reason, 1000, 1200, 50)

        self.assertEqual(reason.reason, "[Device-bound]Device: reason detail")

    @patch.object(CommunicatonBottleneckAnalysis, "_build_task_diff_summary")
    @patch.object(CommunicatonBottleneckAnalysis, "query_host_task_before_time")
    def test_analyze_host_bound_when_pytorch_summary_missing_then_set_unaligned_reason(
        self, mock_query_host_task_before_time, mock_build_task_diff_summary
    ):
        reason = BottleneckReason()
        reason.slow_rank_id = 1
        reason.fast_rank_id = 0
        mock_query_host_task_before_time.side_effect = [(pd.DataFrame(), pd.DataFrame()),
                                                        (pd.DataFrame(), pd.DataFrame())]
        mock_build_task_diff_summary.side_effect = [None, Mock()]

        self.recipe._analyze_host_bound(reason, 1000, 1200, 50)

        self.assertEqual(
            reason.reason,
            "[Host-bound] Tasks are not aligned between slow and fast NPU from the beginning",
        )

    @patch.object(CommunicatonBottleneckAnalysis, "_build_task_diff_summary")
    @patch.object(CommunicatonBottleneckAnalysis, "query_host_task_before_time")
    def test_analyze_host_bound_when_no_reason_strings_then_set_failed_reason(
        self, mock_query_host_task_before_time, mock_build_task_diff_summary
    ):
        reason = BottleneckReason()
        reason.slow_rank_id = 1
        reason.fast_rank_id = 0
        mock_query_host_task_before_time.side_effect = [(pd.DataFrame(), pd.DataFrame()),
                                                        (pd.DataFrame(), pd.DataFrame())]
        mock_pytorch_summary = Mock()
        mock_pytorch_summary.to_reason_string.return_value = None
        mock_cann_summary = Mock()
        mock_cann_summary.to_reason_string.return_value = None
        mock_build_task_diff_summary.side_effect = [mock_pytorch_summary, mock_cann_summary]

        self.recipe._analyze_host_bound(reason, 1000, 1200, 50)

        self.assertEqual(reason.reason, "[Host-bound] Failed to find host task differences")

    @patch.object(CommunicatonBottleneckAnalysis, "_build_task_diff_summary")
    @patch.object(CommunicatonBottleneckAnalysis, "query_host_task_before_time")
    def test_analyze_host_bound_when_pytorch_and_cann_have_reasons_then_join_reason_strings(
        self, mock_query_host_task_before_time, mock_build_task_diff_summary
    ):
        reason = BottleneckReason()
        reason.slow_rank_id = 1
        reason.fast_rank_id = 0
        mock_query_host_task_before_time.side_effect = [(pd.DataFrame(), pd.DataFrame()),
                                                        (pd.DataFrame(), pd.DataFrame())]
        mock_pytorch_summary = Mock()
        mock_pytorch_summary.to_reason_string.return_value = "PyTorch: reason detail"
        mock_cann_summary = Mock()
        mock_cann_summary.to_reason_string.return_value = "CANN: reason detail"
        mock_build_task_diff_summary.side_effect = [mock_pytorch_summary, mock_cann_summary]

        self.recipe._analyze_host_bound(reason, 1000, 1200, 50)

        self.assertEqual(
            reason.reason,
            "[Host-bound] PyTorch: reason detail | CANN: reason detail",
        )

    def test_save_db_when_comm_reasons_empty_then_do_nothing(self):
        self.recipe.comm_reasons = []

        with patch.object(self.recipe, "dump_data") as mock_dump:
            self.recipe.save_db()

        mock_dump.assert_not_called()

    def test_save_csv_when_comm_reasons_valid_then_rename_columns_and_dump_data(self):
        reason = BottleneckReason()
        reason.start_ns = 1000
        reason.end_ns = 3000
        reason.duration = 2000
        reason.comm_name = "all_reduce"
        reason.slow_rank_id = 1
        reason.fast_rank_id = 0
        reason.reason = "device bound"
        self.recipe.comm_reasons = [reason]

        with patch.object(self.recipe, "dump_data") as mock_dump:
            self.recipe.save_csv()

        mock_dump.assert_called_once()
        csv_df = mock_dump.call_args[0][0]
        self.assertIn("Start Time(us)", csv_df.columns)
        self.assertIn("End Time(us)", csv_df.columns)
        self.assertIn("Communication Op", csv_df.columns)
        self.assertEqual(mock_dump.call_args[0][1], "communication_bottleneck.csv")

    def test_run_when_target_rank_not_found_then_do_nothing(self):
        params = dict(self.PARAMS)
        params[Constant.DATA_MAP] = {1: "/rank1"}
        params[Constant.EXTRA_ARGS] = ["--rank_id", "0"]
        recipe = CommunicatonBottleneckAnalysis(params)

        with patch.object(recipe, "obtain_top_communication_ops") as mock_obtain_top_comm, patch.object(
            recipe, "locate_anomaly_reasons"
        ) as mock_locate_reasons, patch.object(recipe, "save_db") as mock_save_db, patch.object(
            recipe, "save_csv"
        ) as mock_save_csv:
            recipe.run(Mock())

        mock_obtain_top_comm.assert_not_called()
        mock_locate_reasons.assert_not_called()
        mock_save_db.assert_not_called()
        mock_save_csv.assert_not_called()

    def test_run_when_export_type_db_then_obtain_reason_and_save_db(self):
        comm_df = pd.DataFrame([{"comm_name": "all_reduce"}])
        reasons = [BottleneckReason()]

        with patch.object(self.recipe, "obtain_top_communication_ops", return_value=comm_df) as mock_obtain_top_comm, \
                patch.object(self.recipe, "locate_anomaly_reasons", return_value=reasons) as mock_locate_reasons, \
                patch.object(self.recipe, "save_db") as mock_save_db, \
                patch.object(self.recipe, "save_csv") as mock_save_csv:
            self.recipe.run(Mock())

        mock_obtain_top_comm.assert_called_once_with(self.recipe.target_rank_id)
        mock_locate_reasons.assert_called_once_with(unittest.mock.ANY, comm_df)
        self.assertEqual(self.recipe.comm_reasons, reasons)
        mock_save_db.assert_called_once()
        mock_save_csv.assert_not_called()

    def test_run_when_export_type_text_then_obtain_reason_and_save_csv(self):
        self.recipe._export_type = Constant.TEXT
        comm_df = pd.DataFrame([{"comm_name": "all_reduce"}])
        reasons = [BottleneckReason()]

        with patch.object(self.recipe, "obtain_top_communication_ops", return_value=comm_df) as mock_obtain_top_comm, \
                patch.object(self.recipe, "locate_anomaly_reasons", return_value=reasons) as mock_locate_reasons, \
                patch.object(self.recipe, "save_db") as mock_save_db, \
                patch.object(self.recipe, "save_csv") as mock_save_csv:
            self.recipe.run(Mock())

        mock_obtain_top_comm.assert_called_once_with(self.recipe.target_rank_id)
        mock_locate_reasons.assert_called_once_with(unittest.mock.ANY, comm_df)
        self.assertEqual(self.recipe.comm_reasons, reasons)
        mock_save_csv.assert_called_once()
        mock_save_db.assert_not_called()

    def test_run_when_export_type_unknown_then_do_not_save(self):
        self.recipe._export_type = "unknown"

        with patch.object(self.recipe, "obtain_top_communication_ops", return_value=pd.DataFrame()) as mock_obtain_top_comm, \
                patch.object(self.recipe, "locate_anomaly_reasons", return_value=None) as mock_locate_reasons, \
                patch.object(self.recipe, "save_db") as mock_save_db, \
                patch.object(self.recipe, "save_csv") as mock_save_csv:
            self.recipe.run(Mock())

        mock_obtain_top_comm.assert_called_once_with(self.recipe.target_rank_id)
        mock_locate_reasons.assert_called_once()
        mock_save_db.assert_not_called()
        mock_save_csv.assert_not_called()


if __name__ == "__main__":
    unittest.main()
