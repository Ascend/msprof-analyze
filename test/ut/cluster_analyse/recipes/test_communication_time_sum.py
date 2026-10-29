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


import os
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
import pandas as pd

from msprof_analyze.cluster_analyse.recipes.communication_time_sum.communication_time_sum import CommunicationTimeSum
from msprof_analyze.prof_common.constant import Constant

NAMESPACE = "msprof_analyze.cluster_analyse.recipes"


class TestCommunicationGroupMap(unittest.TestCase):

    @patch("msprof_analyze.prof_common.database_service.DatabaseService.query_data")
    def test__mapper_func_should_return_mstx_stats_df(self, mock_query_data):
        data_map = {
            Constant.RANK_ID: 0,
            Constant.PROFILER_DB_PATH: "",
            Constant.ANALYSIS_DB_PATH: ""
        }
        df_dict = {
            "CommAnalyzerTime": pd.DataFrame({
                "hccl_op_name": ["hcom_allGather__648_78_1"],
                "group_name": ["3985311255877281648"],
                "start_timestamp": [1747819038106139.0],
                "elapse_time": [22.29027],
                "transit_time": [0.0],
                "wait_time": [0.0],
                "synchronization_time": [0.0],
                "idle_time": [22.29027],
                "step": ["step6"],
                "type": ["collective"]
            }),
            "CommAnalyzerBandwidth": pd.DataFrame({
                "hccl_op_name": ["hcom_allGather__648_78_1"],
                "group_name": ["3985311255877281648"],
                "transport_type": ["HCCS"],
                "transit_size": [0.00006],
                "transit_time": [0.00134],
                "bandwidth": [0.04780],
                "large_packet_ratio": [0],
                "package_size": [0.00006],
                "count": [1],
                "total_duration": [0.00134],
                "step": ["step6"],
                "type": ["collective"]
            })
        }
        mock_query_data.return_value = df_dict
        recipe = CommunicationTimeSum({})
        time_df, bandwidth_df = recipe._mapper_func(data_map, "CommunicationTimeSum")
        self.assertEqual(time_df.shape, (1, 11))
        self.assertEqual(bandwidth_df.shape, (1, 13))

    @patch("msprof_analyze.prof_common.database_service.DatabaseService.query_data")
    def test__mapper_func_should_return_time_data_when_bandwidth_data_is_missing(self, mock_query_data):
        data_map = {
            Constant.RANK_ID: 0,
            Constant.PROFILER_DB_PATH: "",
            Constant.ANALYSIS_DB_PATH: ""
        }
        mock_query_data.return_value = {
            "CommAnalyzerTime": pd.DataFrame({
                "hccl_op_name": ["hcom_allGather__648_78_1"],
                "group_name": ["3985311255877281648"],
                "start_timestamp": [1747819038106139.0],
                "elapse_time": [22.29027],
                "transit_time": [0.0],
                "wait_time": [0.0],
                "synchronization_time": [0.0],
                "idle_time": [22.29027],
                "step": ["step6"],
                "type": ["collective"]
            })
        }

        recipe = CommunicationTimeSum({})
        time_df, bandwidth_df = recipe._mapper_func(data_map, "CommunicationTimeSum")

        self.assertEqual(time_df.shape, (1, 11))
        self.assertIsNone(bandwidth_df)

        mock_query_data.return_value = {
            "CommunicationGroupMapping": pd.DataFrame({
                "rank_set": ["(0)"],
                "group_name": ["3985311255877281648"],
            })
        }
        recipe.reducer_func([(time_df, bandwidth_df)])

        self.assertEqual(recipe.communication_time.shape[0], 2)
        self.assertEqual(recipe.communication_time.iloc[1]["hccl_op_name"], "Total Op Info")
        self.assertTrue(recipe.communication_bandwidth.empty)

    @patch("msprof_analyze.prof_common.database_service.DatabaseService.query_data")
    def test__mapper_func_should_return_none_when_both_stats_are_missing(self, mock_query_data):
        data_map = {
            Constant.RANK_ID: 0,
            Constant.PROFILER_DB_PATH: "",
            Constant.ANALYSIS_DB_PATH: ""
        }
        mock_query_data.return_value = {}

        with tempfile.TemporaryDirectory() as temp_dir:
            recipe = CommunicationTimeSum({
                Constant.EXPORT_TYPE: Constant.DB,
                Constant.CLUSTER_ANALYSIS_OUTPUT_PATH: temp_dir,
            })
            time_df, bandwidth_df = recipe._mapper_func(data_map, "CommunicationTimeSum")
            self.assertIsNone(time_df)
            self.assertIsNone(bandwidth_df)

            recipe.reducer_func([(time_df, bandwidth_df)])
            self.assertTrue(recipe.communication_time.empty)
            self.assertTrue(recipe.communication_bandwidth.empty)

            recipe.save_db()
            db_path = os.path.join(recipe.output_path, "cluster_analysis.db")
            with sqlite3.connect(db_path) as conn:
                tables = {
                    row[0]
                    for row in conn.execute(
                        "select name from sqlite_master where type='table'"
                    )
                }
                self.assertIn("ClusterCommunicationTime", tables)
                self.assertNotIn("ClusterCommunicationBandwidth", tables)
                self.assertEqual(
                    conn.execute("select count(*) from ClusterCommunicationTime").fetchone()[0], 0
                )

    @patch("msprof_analyze.prof_common.database_service.DatabaseService.query_data")
    def test__mapper_func_should_return_bandwidth_data_when_time_data_is_missing(self, mock_query_data):
        data_map = {
            Constant.RANK_ID: 0,
            Constant.PROFILER_DB_PATH: "",
            Constant.ANALYSIS_DB_PATH: ""
        }
        bandwidth_df = pd.DataFrame({
            "hccl_op_name": ["hcom_allGather__648_78_1"],
            "group_name": ["3985311255877281648"],
            "transport_type": ["HCCS"],
            "transit_size": [0.00006],
            "transit_time": [0.00134],
            "bandwidth": [0.04780],
            "large_packet_ratio": [0],
            "package_size": [0.00006],
            "count": [1],
            "total_duration": [0.00134],
            "step": ["step6"],
            "type": ["collective"]
        })
        mock_query_data.side_effect = [
            {"CommAnalyzerBandwidth": bandwidth_df},
            {"CommunicationGroupMapping": pd.DataFrame({
                "rank_set": ["(0)"],
                "group_name": ["3985311255877281648"],
            })},
        ]

        recipe = CommunicationTimeSum({})
        time_df, result_bandwidth_df = recipe._mapper_func(data_map, "CommunicationTimeSum")
        recipe.reducer_func([(time_df, result_bandwidth_df)])

        self.assertIsNone(time_df)
        self.assertEqual(recipe.communication_bandwidth.shape[0], 2)
        self.assertEqual(recipe.communication_bandwidth.iloc[1]["hccl_op_name"], "Total Op Info")
        self.assertTrue(recipe.communication_time.empty)

    @patch("msprof_analyze.prof_common.database_service.DatabaseService.query_data")
    @patch(NAMESPACE + ".communication_time_sum.communication_time_sum.CommunicationTimeSum."
                       "run_communication_group_map_recipe")
    @patch(NAMESPACE + ".base_recipe_analysis.BaseRecipeAnalysis.dump_data")
    @patch(NAMESPACE + ".base_recipe_analysis.BaseRecipeAnalysis.mapper_func")
    def test_run_should_save_db_or_notebook(self, mock_mapper_func, mock_dump_data,
                                            mock_run_communication_group_map_recipe, mock_query_data):
        mock_query_data.return_value = {
            "CommunicationGroupMapping": pd.DataFrame({
                "rank_set": ["(1)"],
                "group_name": ["3985311255877281648"],
            })
        }
        mock_run_communication_group_map_recipe.return_value = True
        mock_mapper_func.return_value = [
            (pd.DataFrame({
                "hccl_op_name": ["hcom_allGather__648_78_1"],
                "group_name": ["3985311255877281648"],
                "start_timestamp": [1747819038106139.0],
                "elapse_time": [22.29027],
                "transit_time": [0.0],
                "wait_time": [0.0],
                "synchronization_time": [0.0],
                "idle_time": [22.29027],
                "step": ["step6"],
                "type": ["collective"],
                "rank_id": [1]
            }),
            pd.DataFrame({
                "hccl_op_name": ["hcom_allGather__648_78_1"],
                "group_name": ["3985311255877281648"],
                "transport_type": ["HCCS"],
                "transit_size": [0.00006],
                "transit_time": [0.00134],
                "bandwidth": [0.04780],
                "large_packet_ratio": [0],
                "package_size": [0.00006],
                "count": [1],
                "total_duration": [0.00134],
                "step": ["step6"],
                "type": ["collective"],
                "rank_id": [1]
            }))
        ]
        expected_communication_time = pd.DataFrame({
            "step": ["step6", "step6"],
            "rank_id": [1, 1],
            "hccl_op_name": ["hcom_allGather__648_78_1", "Total Op Info"],
            "group_name": ["3985311255877281648", "3985311255877281648"],
            "start_timestamp": [1747819038106139.0, 0.0],
            "elapsed_time": [22.29027, 22.29027],
            "transit_time": [0.0, 0.0],
            "wait_time": [0.0, 0.0],
            "synchronization_time": [0.0, 0.0],
            "idle_time": [22.29027, 22.29027],
            "synchronization_time_ratio": [0.0, 0.0],
            "wait_time_ratio": [0.0, 0.0],

        })
        expected_communication_bandwidth = pd.DataFrame({
            "step": ["step6", "step6"],
            "rank_id": [1, 1],
            "hccl_op_name": ["hcom_allGather__648_78_1", "Total Op Info"],
            "group_name": ["3985311255877281648", "3985311255877281648"],
            "band_type": ["HCCS", "HCCS"],
            "transit_size": [0.00006, 0.00006],
            "transit_time": [0.00134, 0.00134],
            "bandwidth": [0.04780, 0.04480],
            "large_packet_ratio": [0, 0],
            "package_size": [0.00006, 0.00006],
            "count": [1, 1],
            "total_duration": [0.00134, 0.00134],
        })
        params = {Constant.EXPORT_TYPE: Constant.DB}
        recipe = CommunicationTimeSum(params)
        recipe.run(context=None)
        is_equal = (recipe.communication_time.reset_index(drop=True).
                    equals(expected_communication_time.reset_index(drop=True)))
        self.assertTrue(is_equal)
        is_equal = (recipe.communication_bandwidth.reset_index(drop=True).
                    equals(expected_communication_bandwidth.reset_index(drop=True)))
        self.assertTrue(is_equal)


class TestLevel0CommunicationTime(unittest.TestCase):
    @staticmethod
    def time_data():
        return pd.DataFrame({
            "step": ["step", "step"],
            "rank_id": [0, 0],
            "hccl_op_name": ["hcom_allReduce__0_0_1", "hcom_allReduce__0_1_1"],
            "group_name": ["5862276093215481612"] * 2,
            "start_timestamp": [1000000.25, 1004000.75],
            "elapse_time": [2.0, 3.0],
            "transit_time": [-1.0, -1.0],
            "wait_time": [-1.0, -1.0],
            "synchronization_time": [-1.0, -1.0],
            "idle_time": [-1.0, -1.0],
        })

    def compute(self, data):
        recipe = CommunicationTimeSum({})
        groups = pd.DataFrame({"group_name": ["5862276093215481612"], "rank_set": ["(0,1)"]})
        recipe._compute_time_info(data, groups)
        return recipe.communication_time.reset_index(drop=True)

    def test_level0_preserves_calls_and_marks_all_breakdown_and_ratios_unavailable(self):
        data = self.time_data()
        result = self.compute(data)
        self.assertEqual(len(result), 3)
        self.assertEqual(result["hccl_op_name"].tolist(), data["hccl_op_name"].tolist() + ["Total Op Info"])
        self.assertEqual(result["elapsed_time"].tolist(), [2.0, 3.0, 5.0])
        self.assertEqual(result["start_timestamp"].tolist(), [1000000.25, 1004000.75, 0.0])
        unavailable = CommunicationTimeSum.TIME_BREAKDOWN_COLUMNS + [
            "synchronization_time_ratio", "wait_time_ratio"
        ]
        self.assertTrue((result[unavailable] == -1).all().all())
        self.assertEqual(result["group_name"].unique().tolist(), ["5862276093215481612"])

    def test_partial_breakdown_sums_valid_values_and_pairs_ratio_inputs(self):
        data = self.time_data()
        data["transit_time"] = [1.0, -1.0]
        data["wait_time"] = [2.0, 3.0]
        data["synchronization_time"] = [0.0, 0.0]
        data["idle_time"] = [-1.0, 0.0]
        for frame in (data, data.iloc[::-1]):
            with self.subTest(order=frame.index.tolist()):
                total = self.compute(frame).iloc[-1]
                self.assertEqual(total["transit_time"], 1.0)
                self.assertEqual(total["wait_time"], 5.0)
                self.assertEqual(total["synchronization_time"], 0.0)
                self.assertEqual(total["idle_time"], 0.0)
                self.assertEqual(total["wait_time_ratio"], 0.6667)
                self.assertEqual(total["synchronization_time_ratio"], 0.0)

    def test_level0_does_not_downgrade_detailed_rank_or_real_zero(self):
        coarse = self.time_data()
        detailed = self.time_data()
        detailed["rank_id"] = 1
        detailed[CommunicationTimeSum.TIME_BREAKDOWN_COLUMNS] = 0.0
        result = self.compute(pd.concat([coarse, detailed], ignore_index=True))
        fields = CommunicationTimeSum.TIME_BREAKDOWN_COLUMNS + ["wait_time_ratio", "synchronization_time_ratio"]
        self.assertTrue((result.loc[result["rank_id"] == 0, fields] == -1).all().all())
        self.assertTrue((result.loc[result["rank_id"] == 1, fields] == 0).all().all())

    def test_null_and_absent_optional_fields_are_unavailable(self):
        data = self.time_data().drop(columns=["idle_time"])
        data["wait_time"] = [None, 0.0]
        result = self.compute(data)
        self.assertTrue((result["idle_time"] == -1).all())
        self.assertEqual(result.iloc[0]["wait_time"], -1)
        self.assertEqual(result.iloc[-1]["wait_time"], 0.0)
        self.assertFalse(result.isna().any().any())

    def test_time_only_db_omits_bandwidth_table_and_reports_only_written_table(self):
        with tempfile.TemporaryDirectory() as output:
            recipe = CommunicationTimeSum({
                Constant.EXPORT_TYPE: Constant.DB,
                Constant.CLUSTER_ANALYSIS_OUTPUT_PATH: output,
            })
            recipe.communication_time = self.compute(self.time_data())
            with patch(NAMESPACE + ".communication_time_sum.communication_time_sum.set_json_success") as success:
                recipe.save_db()
            self.assertEqual(success.call_args.kwargs["msg_dict"]["tables"], ["ClusterCommunicationTime"])
            with sqlite3.connect(os.path.join(recipe.output_path, "cluster_analysis.db")) as conn:
                tables = {row[0] for row in conn.execute("select name from sqlite_master where type='table'")}
                self.assertEqual(tables, {"ClusterCommunicationTime"})
                self.assertEqual(conn.execute("select count(*) from ClusterCommunicationTime").fetchone()[0], 3)
                self.assertEqual(
                    conn.execute("select wait_time,wait_time_ratio from ClusterCommunicationTime "
                                 "where hccl_op_name='Total Op Info'").fetchone(), (-1, -1)
                )

    def test_time_only_csv_omits_bandwidth_file_and_reports_only_written_file(self):
        with tempfile.TemporaryDirectory() as output:
            recipe = CommunicationTimeSum({
                Constant.EXPORT_TYPE: Constant.TEXT,
                Constant.RECIPE_NAME: "CommunicationTimeSum",
                Constant.CLUSTER_ANALYSIS_OUTPUT_PATH: output,
            })
            recipe.communication_time = self.compute(self.time_data())
            with patch(NAMESPACE + ".communication_time_sum.communication_time_sum.set_json_success") as success:
                recipe.save_csv()
            time_csv = os.path.join(recipe.output_path, "cluster_communication_time.csv")
            self.assertTrue(os.path.isfile(time_csv))
            self.assertFalse(os.path.exists(os.path.join(recipe.output_path, "cluster_communication_bandwidth.csv")))
            self.assertEqual(success.call_args.kwargs["msg_dict"]["csv_path"], [time_csv])

    def test_detailed_time_keeps_legacy_empty_bandwidth_table_and_csv(self):
        detailed = self.time_data()
        detailed[CommunicationTimeSum.TIME_BREAKDOWN_COLUMNS] = 0.0
        for export_type in (Constant.DB, Constant.TEXT):
            with self.subTest(export_type=export_type), tempfile.TemporaryDirectory() as output:
                recipe = CommunicationTimeSum({
                    Constant.EXPORT_TYPE: export_type,
                    Constant.CLUSTER_ANALYSIS_OUTPUT_PATH: output,
                })
                recipe.communication_time = self.compute(detailed)
                if export_type == Constant.DB:
                    recipe.save_db()
                    with sqlite3.connect(os.path.join(recipe.output_path, "cluster_analysis.db")) as conn:
                        self.assertEqual(conn.execute("select count(*) from ClusterCommunicationBandwidth").fetchone()[0], 0)
                        columns = [r[1] for r in conn.execute("pragma table_info(ClusterCommunicationBandwidth)")]
                        self.assertEqual(columns, recipe.BANDWIDTH_COLUMNS)
                else:
                    recipe.save_csv()
                    bandwidth = pd.read_csv(os.path.join(recipe.output_path, "cluster_communication_bandwidth.csv"))
                    self.assertTrue(bandwidth.empty)
                    self.assertEqual(bandwidth.columns.tolist(), recipe.BANDWIDTH_COLUMNS)

    def test_ratio_requires_paired_valid_calls_even_when_both_metric_totals_exist(self):
        data = self.time_data()
        data["transit_time"] = [1.0, -1.0]
        data["wait_time"] = [-1.0, 3.0]
        total = self.compute(data).iloc[-1]
        self.assertEqual(total["elapsed_time"], 5.0)
        self.assertEqual(total["transit_time"], 1.0)
        self.assertEqual(total["wait_time"], 3.0)
        self.assertEqual(total["wait_time_ratio"], -1)
