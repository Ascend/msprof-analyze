# Copyright (c) 2025, Huawei Technologies Co., Ltd.
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
from unittest import mock
import pandas as pd

from msprof_analyze.cluster_analyse.recipes.cluster_time_summary.cluster_time_summary import ClusterTimeSummary
from msprof_analyze.prof_common.constant import Constant
from msprof_analyze.prof_common.path_manager import PathManager


NAMESPACE_RECIPE = "msprof_analyze.cluster_analyse.recipes.cluster_time_summary.cluster_time_summary"


class FakeFuture:
    def __init__(self, value):
        self._value = value

    def result(self):
        return self._value


class FakeContext:
    def __init__(self, future_dict=None):
        self.future_dict = future_dict or {}

    @classmethod
    def wait_all_futures(cls):
        return


class TestClusterTimeSummary(unittest.TestCase):
    PARAMS = {
        Constant.COLLECTION_PATH: "/data",
        Constant.DATA_MAP: {0: "/rank0", 1: "/rank1"},
        Constant.DATA_TYPE: Constant.DB,
        Constant.CLUSTER_ANALYSIS_OUTPUT_PATH: "./tmp_cluster_time_summary_ut",
        Constant.RECIPE_NAME: "ClusterTimeSummary",
        Constant.RECIPE_CLASS: ClusterTimeSummary,
        Constant.PARALLEL_MODE: Constant.CONCURRENT_MODE,
        Constant.EXPORT_TYPE: Constant.DB,
        Constant.RANK_LIST: Constant.ALL,
    }

    COMMUNICATION_DF = pd.DataFrame({
            "rank": [0, 0, 1, 1],
            "step": [1, 1, 1, 1],
            "groupName": ["group_0", "group_0", "group_0", "group_0"],
            "opName": ["hcom_allGather__672_0_1", "hcom_boardcast__672_2_1",
                       "hcom_allGather__672_0_1", "hcom_boardcast__672_2_1"],
            "communication_time": [10.0, 8.0, 17.0, 6.0],
        })

    RANK_1_DATA_MAP = {
        Constant.RANK_ID: 1,
        Constant.PROFILER_DB_PATH: "/rank0/ascend_pytorch_profiler_1.db",
        Constant.STEP_RANGE: {Constant.START_NS: 10000, Constant.END_NS: 45000}
    }

    def tearDown(self):
        PathManager.remove_path_safety(self.PARAMS.get(Constant.CLUSTER_ANALYSIS_OUTPUT_PATH))

    def test_get_memory_not_overlap_when_intervals_mixed_then_return_expected(self):
        # MEMORY: [0,10], COMPUTE: [5,15], MEMORY: [20,30] => Not Overlapped 5 + 10 = 15 => 15 / 1000
        df = pd.DataFrame([
            {"start": 0, "end": 10, "type": ClusterTimeSummary.MEMORY_TYPE},
            {"start": 5, "end": 15, "type": ClusterTimeSummary.COMPUTING_TYPE},
            {"start": 20, "end": 30, "type": ClusterTimeSummary.MEMORY_TYPE},
        ])
        self.assertAlmostEqual(ClusterTimeSummary.get_memory_not_overlap(df), 15 / Constant.TIME_UNIT_SCALE)

    def test_calculate_memory_time_when_has_memory_rows_then_group_sum(self):
        df = pd.DataFrame([
            {"start": 0, "end": 10, "type": ClusterTimeSummary.MEMORY_TYPE, "step": 1},
            {"start": 15, "end": 25, "type": ClusterTimeSummary.MEMORY_TYPE, "step": 1},
            {"start": 0, "end": 5, "type": ClusterTimeSummary.COMPUTING_TYPE, "step": 1},
        ])
        res = ClusterTimeSummary.calculate_memory_time(df)
        expected = pd.DataFrame({"step": [1], "memory": [(10 - 0 + 25 - 15) / Constant.TIME_UNIT_SCALE]})
        self.assertTrue(res.equals(expected))

    @mock.patch("msprof_analyze.prof_common.database_service.DatabaseService.query_data")
    def test_calculate_step_time_when_has_step_time_table_then_return_valid_df(self, mock_query_data):
        step_df = pd.DataFrame([
            {"id": 0, "startNs": 10000, "endNs": 45000},
            {"id": 1, "startNs": 50000, "endNs": 90000}
        ])
        mock_query_data.return_value = {Constant.TABLE_STEP_TIME: step_df}
        recipe = ClusterTimeSummary(self.PARAMS)
        res = recipe.calculate_step_time(self.RANK_1_DATA_MAP, "ClusterTimeSummary")
        self.assertEqual(res.columns.tolist(), ["rank", "step", "stepTime"])
        self.assertAlmostEqual(res["stepTime"].tolist(), [35.0, 40.0])

    @mock.patch("msprof_analyze.prof_common.database_service.DatabaseService.query_data")
    def test_calculate_step_time_when_step_time_is_not_existed_then_return_df(self, mock_query_data):
        mock_query_data.return_value = {Constant.TABLE_STEP_TIME: pd.DataFrame()}
        recipe = ClusterTimeSummary(self.PARAMS)
        res = recipe.calculate_step_time({Constant.PROFILER_DB_PATH: "/rank0/ascend_pytorch_profiler_0.db",
                                          Constant.RANK_ID: 1}, "ClusterTimeSummary")
        expected_res = pd.DataFrame({"rank": [1], "step": [-1], "stepTime": [None]})
        self.assertTrue(res.equals(expected_res))

    @mock.patch("msprof_analyze.prof_common.database_service.DatabaseService.query_data")
    def test_calculate_step_trace_time_when_query_success_when_return_valid_df(self, mock_query_data):
        step_trace_df = pd.DataFrame({
            "step": [0, 1],
            "computing": [30.0, 40.0],
            "communication_not_overlapped": [20.0, 30.0],
            "overlapped": [5.0, 6.0],
            "communication": [25.0, 36.0],
            "free": [45.0, 124.0],
        })
        expected_df = step_trace_df.copy()
        expected_df.insert(0, "rank", 1)
        expected_df["step"] = expected_df["step"].astype(int)

        mock_query_data.return_value = {Constant.TABLE_STEP_TRACE: step_trace_df}
        recipe = ClusterTimeSummary(self.PARAMS)
        res = recipe.calculate_step_trace_time(self.RANK_1_DATA_MAP, "ClusterTimeSummary")
        self.assertTrue(expected_df.equals(res))

    @mock.patch("msprof_analyze.prof_common.database_service.DatabaseService.query_data")
    def test_calculate_step_trace_time_when_query_fail_then_return_none(self, mock_query_data):
        mock_query_data.return_value = {Constant.TABLE_STEP_TIME: pd.DataFrame()}
        recipe = ClusterTimeSummary(self.PARAMS)
        res = recipe.calculate_step_trace_time(self.RANK_1_DATA_MAP, "ClusterTimeSummary")
        self.assertIsNone(res)

    @mock.patch("msprof_analyze.prof_exports.cluster_time_summary_export.CommunicationOpWithStepExport.read_export_db")
    def test_calculate_communication_time(self, mock_query_data):
        recipe = ClusterTimeSummary(self.PARAMS)
        # export成功时
        mock_query_data.return_value = pd.DataFrame({
            "rank": [0, 0],
            "groupName": ["group_0", "group_0"],
            "opName": ["hcom_allGather__672_0_1", "hcom_boardcast__672_2_1"],
            "communication_time": [10.0, 8.0],
            "step": [1, 1]
        })
        res = recipe.calculate_communication_time(self.RANK_1_DATA_MAP, "ClusterTimeSummary")
        self.assertIsNotNone(res)
        self.assertFalse(res.empty)

        # 如果export失败，函数返回None
        mock_query_data.return_value = None
        recipe = ClusterTimeSummary(self.PARAMS)
        res = recipe.calculate_communication_time(self.RANK_1_DATA_MAP, "ClusterTimeSummary")
        self.assertIsNone(res)

    @mock.patch("msprof_analyze.prof_exports.cluster_time_summary_export.MemoryAndDispatchTimeExport.read_export_db")
    def test_calculate_memory_and_not_overlapped_time(self, mock_export_db):
        mock_export_db.return_value = pd.DataFrame([
            {"start": 0, "end": 5, "type": ClusterTimeSummary.COMPUTING_TYPE, "step": 1},
            {"start": 0, "end": 10, "type": ClusterTimeSummary.MEMORY_TYPE, "step": 1},
            {"start": 15, "end": 25, "type": ClusterTimeSummary.MEMORY_TYPE, "step": 1}
        ])
        expected = pd.DataFrame({"rank": 1, "step": [1], "memory": [20 / Constant.TIME_UNIT_SCALE],
                                 "memoryNotOverlapComputationCommunication": [15 / Constant.TIME_UNIT_SCALE]})
        recipe = ClusterTimeSummary(self.PARAMS)
        res = recipe.calculate_memory_and_not_overlapped_time(self.RANK_1_DATA_MAP, "ClusterTimeSummary")
        self.assertTrue(res.equals(expected))

    def test_calculate_transmit_and_wait_df_when_group_complete_then_compute_wait_and_transmit(self):
        comm_df = self.COMMUNICATION_DF
        recipe = ClusterTimeSummary(self.PARAMS)
        recipe.communication_group_mapping = pd.DataFrame({
            "rank_set": ["(0,1)"],
            "group_name": ["15277154023019599672"],
            "group_id": ["group_0"],
            "pg_name": ["default_group"]
        })
        res = recipe.calculate_transmit_and_wait_df(comm_df)
        expected = pd.DataFrame({
            "rank": [0, 1],
            "step": [1, 1],
            "communicationWaitStageTime": [2.0, 7.0],
            "communicationTransmitStageTime": [16.0, 16.0],
        })
        # order is not guaranteed
        res_sorted = res.sort_values(["rank", "step"]).reset_index(drop=True)
        self.assertTrue(res_sorted.equals(expected))

    @mock.patch("msprof_analyze.prof_common.database_service.DatabaseService.query_data")
    def test_calculate_transmit_and_wait_df_when_group_mapping_missing_then_return_empty(self, mock_query_data):
        mock_query_data.return_value = {Constant.TABLE_COMMUNICATION_GROUP_MAPPING: pd.DataFrame()}
        comm_df = self.COMMUNICATION_DF
        recipe = ClusterTimeSummary(self.PARAMS)
        res = recipe.calculate_transmit_and_wait_df(comm_df)
        self.assertTrue(res.empty)

    def test_aggregate_stats_when_valid_inputs_then_merged_df(self):
        # Inputs
        step_time_df = pd.DataFrame({"rank": [0, 1], "step": [1, 1], "stepTime": [100.0, 200.0]})
        step_trace_df = pd.DataFrame({
            "rank": [0, 1], "step": [1, 1],
            "computing": [30.0, 40.0],
            "communication_not_overlapped": [20.0, 30.0],
            "overlapped": [5.0, 6.0],
            "communication": [25.0, 36.0],
            "free": [45.0, 124.0],
        })
        trans_wait_df = pd.DataFrame({
            "rank": [0, 1], "step": [1, 1],
            "communicationWaitStageTime": [3.0, 4.0],
            "communicationTransmitStageTime": [10.0, 11.0],
        })
        memory_df = pd.DataFrame({
            "rank": [0, 1], "step": [1, 1],
            "memory": [9.0, 8.0],
            "memoryNotOverlapComputationCommunication": [1.0, 2.0],
        })
        context = FakeContext({
            ClusterTimeSummary.STEP_TIME: [FakeFuture(step_time_df)],
            ClusterTimeSummary.STEP_TRACE: [FakeFuture(step_trace_df)],
            ClusterTimeSummary.COMMUNICATION: [FakeFuture(self.COMMUNICATION_DF)],  # 表明不是单卡场景，值无意义
            ClusterTimeSummary.MEMORY: [FakeFuture(memory_df)],
        })
        recipe = ClusterTimeSummary(self.PARAMS)
        # Patch transmit_and_wait to controlled df
        with mock.patch.object(recipe, "calculate_transmit_and_wait_df", return_value=trans_wait_df):
            merged = recipe.aggregate_stats(context)

        expected = pd.DataFrame({
            "rank": [0, 1],
            "step": [1, 1],
            "stepTime": [100.0, 200.0],
            "computation": [30.0, 40.0],
            "communicationNotOverlapComputation": [20.0, 30.0],
            "communicationOverlapComputation": [5.0, 6.0],
            "communication": [25.0, 36.0],
            "free": [44.0, 122.0],  # free minus memoryNotOverlap
            "communicationWaitStageTime": [3.0, 4.0],
            "communicationTransmitStageTime": [10.0, 11.0],
            "memory": [9.0, 8.0],
            "memoryNotOverlapComputationCommunication": [1.0, 2.0],
        }).sort_values(["rank", "step"]).reset_index(drop=True)

        merged_sorted = merged.sort_values(["rank", "step"]).reset_index(drop=True)
        self.assertTrue(merged_sorted.equals(expected))

    def test_aggregate_stats_when_missing_step_time_or_trace_then_return_empty(self):
        context = FakeContext({
            ClusterTimeSummary.STEP_TIME: [FakeFuture(pd.DataFrame())],
            ClusterTimeSummary.STEP_TRACE: [FakeFuture(pd.DataFrame())],
            ClusterTimeSummary.COMMUNICATION: [FakeFuture(pd.DataFrame())],
            ClusterTimeSummary.MEMORY: [FakeFuture(pd.DataFrame())],
        })
        recipe = ClusterTimeSummary(self.PARAMS)
        res = recipe.aggregate_stats(context)
        self.assertTrue(res.empty)

    @mock.patch(NAMESPACE_RECIPE + ".DBManager.check_tables_in_db")
    def test_run_when_export_type_not_db_then_return_without_saving(self, mock_check_tables):
        params = dict(self.PARAMS)
        params[Constant.EXPORT_TYPE] = Constant.NOTEBOOK
        recipe = ClusterTimeSummary(params)
        # ensure not touching db
        with mock.patch(NAMESPACE_RECIPE + ".BaseRecipeAnalysis.dump_data") as mock_dump:
            recipe.run(context=FakeContext())
            mock_dump.assert_not_called()
            mock_check_tables.assert_not_called()

    @mock.patch.object(ClusterTimeSummary, "run_communication_group_map_recipe", return_value=False)
    def test_run_when_comm_group_map_creation_fails_then_return(self, mock_run_group):
        recipe = ClusterTimeSummary(self.PARAMS)
        with mock.patch(NAMESPACE_RECIPE + ".BaseRecipeAnalysis.dump_data") as mock_dump:
            recipe.run(context=FakeContext())
            mock_dump.assert_not_called()
        mock_run_group.assert_called_once()

    @mock.patch(NAMESPACE_RECIPE + ".ClusterTimeSummary.run_communication_group_map_recipe", side_effect=[True])
    def test_run_when_all_ok_then_save_db(self, mock_check_tables):
        recipe = ClusterTimeSummary(self.PARAMS)
        fake_df = pd.DataFrame({"rank": [0], "step": [1], "stepTime": [1.0]})
        with mock.patch.object(recipe, "mapper_func"), \
             mock.patch.object(recipe, "aggregate_stats", return_value=fake_df), \
             mock.patch(NAMESPACE_RECIPE + ".BaseRecipeAnalysis.dump_data") as mock_dump:
            recipe.run(context=FakeContext())
            mock_dump.assert_called_once()  # saved to db

