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
from unittest.mock import patch
import pandas as pd

from msprof_analyze.cluster_analyse.recipes.communication_matrix_sum.communication_matrix_sum import CommMatrixSum
from msprof_analyze.prof_common.constant import Constant

NAMESPACE = "msprof_analyze.cluster_analyse.recipes"


class TestCommMatrixSum(unittest.TestCase):
    @patch("msprof_analyze.prof_common.path_manager.PathManager.check_output_directory_path")
    @patch("msprof_analyze.prof_common.database_service.DatabaseService.query_data")
    def test__mapper_func_should_return_mstx_stats_df(self, mock_query_data, mock_check_output_directory_path):
        data_map = {Constant.RANK_ID: 0, Constant.PROFILER_DB_PATH: "", Constant.ANALYSIS_DB_PATH: ""}
        df_dict = {
            "CommAnalyzerMatrix": pd.DataFrame(
                {
                    "hccl_op_name": ["receive-top1"],
                    "group_name": ["3985311255877281648"],
                    "src_rank": [1],
                    "dst_rank": [1],
                    "transport_type": ["LOCAL"],
                    "transit_size": [7.34],
                    "transit_time": [0.0],
                    "bandwidth": [590.02],
                    "step": ["step6"],
                    "type": ["p2p"],
                    "op_name": ["hcom_receive__964_40_1"],
                }
            ),
            "META_DATA": pd.DataFrame(
                {
                    "name": ["parallel_group_info"],
                    "value": [
                        '{"group_name_0":{"group_name":"default_group","group_rank":0,"global_ranks":[0,1,2,3,4,5,6,7,8]}}'
                    ],
                }
            ),
        }
        mock_query_data.return_value = df_dict
        recipe = CommMatrixSum({})
        result = recipe._mapper_func(data_map, "CommMatrixSum")
        self.assertEqual(len(result), 3)

    @patch("msprof_analyze.prof_common.path_manager.PathManager.check_output_directory_path")
    @patch("msprof_analyze.prof_common.database_service.DatabaseService.query_data")
    def test__mapper_func_should_return_mstx_stats_df_when_prof_type_is_not_pytorch(
        self, mock_query_data, mock_check_output_directory_path
    ):
        data_map = {Constant.RANK_ID: 0, Constant.PROFILER_DB_PATH: "", Constant.ANALYSIS_DB_PATH: ""}
        df_dict = {
            "CommAnalyzerMatrix": pd.DataFrame(
                {
                    "hccl_op_name": ["hcom_broadcast__491_0_1"],
                    "group_name": ["3985311255877281648"],
                    "src_rank": [0],
                    "dst_rank": [3],
                    "transport_type": ["HCCS"],
                    "transit_size": [7.34],
                    "transit_time": [0.0],
                    "bandwidth": [590.02],
                }
            )
        }
        mock_query_data.return_value = df_dict
        recipe = CommMatrixSum({})
        recipe._prof_type = Constant.MSPROF
        result = recipe._mapper_func(data_map, "CommMatrixSum")
        self.assertEqual(len(result), 3)

    @patch("msprof_analyze.prof_common.path_manager.PathManager.check_output_directory_path")
    @patch(NAMESPACE + ".base_recipe_analysis.BaseRecipeAnalysis.dump_data")
    @patch(NAMESPACE + ".base_recipe_analysis.BaseRecipeAnalysis.mapper_func")
    def test_run_should_save_db_or_notebook(self, mock_mapper_func, mock_dump_data, mock_check_output_directory_path):
        mock_mapper_func.return_value = [
            {
                "rank_id": 1,
                "rank_map": {3985311255877281648: {0: 0, 1: 1}},
                "matrix_data": pd.DataFrame(
                    {
                        "hccl_op_name": ["receive-top1"],
                        "group_name": ["3985311255877281648"],
                        "src_rank": [1],
                        "dst_rank": [1],
                        "transport_type": ["LOCAL"],
                        "transit_size": [7.34],
                        "transit_time": [0.0],
                        "bandwidth": [590.02],
                        "step": ["step6"],
                        "type": ["p2p"],
                        "op_name": ["hcom_receive__964_40_1"],
                    }
                ),
            }
        ]
        expected_cluster_matrix_df = pd.DataFrame(
            {
                "step": ["step6"],
                "hccl_op_name": ["receive-top1"],
                "group_name": ["3985311255877281648"],
                "src_rank": [1],
                "dst_rank": [1],
                "transport_type": ["LOCAL"],
                "op_name": ["hcom_receive__964_40_1"],
                "transit_size": [7.34],
                "transit_time": [0.0],
                "bandwidth": [0],
            }
        )
        expected_cluster_matrix_df['bandwidth'] = expected_cluster_matrix_df['bandwidth'].astype('object')
        params = {Constant.EXPORT_TYPE: Constant.DB}
        recipe = CommMatrixSum(params)
        recipe.run(context=None)
        pd.testing.assert_frame_equal(
            expected_cluster_matrix_df,
            recipe.cluster_matrix_df,
            check_dtype=False,
            check_exact=False,
            rtol=1e-5,
            atol=1e-8,
            obj="cluster_matrix_df",
        )
