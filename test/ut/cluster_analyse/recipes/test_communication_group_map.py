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
from unittest.mock import patch
import pandas as pd

from msprof_analyze.cluster_analyse.recipes.communication_group_map.communication_group_map import CommunicationGroupMap
from msprof_analyze.prof_common.constant import Constant


class TestCommunicationGroupMap(unittest.TestCase):

    @patch("msprof_analyze.prof_common.database_service.DatabaseService.query_data")
    def test__mapper_func_should_return_mstx_stats_df(self, mock_query_data):
        data_map = {
            Constant.RANK_ID: 0,
            Constant.PROFILER_DB_PATH: "",
            Constant.ANALYSIS_DB_PATH: ""
        }
        comm_time_res = {
            "CommAnalyzerTime": pd.DataFrame({
                "hccl_op_name": ["hcom_alltoallv__648_83_1", "hcom_allGather__648_84_1"],
                "group_name": ["5862276097510448909", "5862276097510448909"]
            })
        }
        meta_data_res = {
            "META_DATA": pd.DataFrame({
                "name": ["parallel_group_info"],
                "value": ['{"group_name_1": {"group_name": "dp", "group_rank": 1, "global_ranks":[0, 1]}}'],
            })
        }
        mock_query_data.side_effect = [comm_time_res, meta_data_res]
        recipe = CommunicationGroupMap({})
        comm_time_df, parallel_info_df = recipe._mapper_func(data_map, "CommunicationGroupMap")
        expected_comm_time_df = pd.DataFrame({
            "group_name": ["5862276097510448909"],
            "rank_id": [0],
            "type": ["collective"]
        })
        expected_parallel_info_df = pd.DataFrame({
            "group_name": ["5862276097510448909"],
            "group_id": ["group_name_1"],
            "pg_name": ["dp"],
            "global_ranks": ["(0,1)"]
        })
        self.assertTrue(comm_time_df.equals(expected_comm_time_df))
        self.assertTrue(parallel_info_df.equals(expected_parallel_info_df))

    @patch("msprof_analyze.cluster_analyse.recipes.base_recipe_analysis.BaseRecipeAnalysis.dump_data")
    @patch("msprof_analyze.cluster_analyse.recipes.base_recipe_analysis.BaseRecipeAnalysis.mapper_func")
    def test_run_should_save_db_or_notebook(self, mock_mapper_func, mock_dump_data):
        mock_mapper_func.return_value = [
            (pd.DataFrame({
                "group_name": ["5862276097510448909"],
                "rank_id": [0],
                "type": ["collective"]
            }),
            pd.DataFrame({
                "group_name": ["5862276097510448909"],
                "group_id": ["group_name_1"],
                "pg_name": ["dp"],
                "global_ranks": ["(0,1)"]
            }))
        ]
        expected_group_df = pd.DataFrame({
            "type": ["collective"],
            "rank_set": ["(0,1)"],
            "group_name": ["5862276097510448909"],
            "group_id": ["group_name_1"],
            "pg_name": ["dp"]
        })
        params = {Constant.EXPORT_TYPE: Constant.DB}
        recipe = CommunicationGroupMap(params)
        recipe.run(context=None)
        self.assertTrue(recipe.group_df.equals(expected_group_df))

    def test_update_rank_set_mixed_conditions(self):
        test_data = {
            "type": ["type1", "type2", "type3", "type4", "type5", "type6"],
            "rank_set": ["(1,2,3)", "(4,5,6)", "(7,8,9)", "(10,11)", "(12,13)", "(14,15,16)"],
            "global_ranks": ["(1,2,3,4)", "", None, "(10,11,12)", "(12,13)", []],
            "group_name": ["group1", "group2", "group3", "group4", "group5", "group6"]
        }
        input_df = pd.DataFrame(test_data)
        recipe = CommunicationGroupMap(params={})
        result_df = recipe.update_rank_set(input_df)

        expected_rank_sets = ["(1,2,3,4)", "(4,5,6)", "(7,8,9)", "(10,11,12)", "(12,13)", "(14,15,16)"]
        self.assertEqual(list(result_df["rank_set"]), expected_rank_sets)
