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
                self.assertIn("ClusterCommunicationBandwidth", tables)
                self.assertEqual(
                    conn.execute("select count(*) from ClusterCommunicationTime").fetchone()[0], 0
                )
                self.assertEqual(
                    conn.execute("select count(*) from ClusterCommunicationBandwidth").fetchone()[0], 0
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
