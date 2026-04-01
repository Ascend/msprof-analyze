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
from msprof_analyze.cluster_analyse.recipes.mstx_sum.mstx_sum import MstxSum
from msprof_analyze.prof_common.constant import Constant


class TestMstxSum(unittest.TestCase):

    @patch("msprof_analyze.prof_common.db_manager.DBManager.check_tables_in_db")
    @patch("msprof_analyze.prof_exports.mstx_step_export.MstxStepExport.read_export_db")
    @patch("msprof_analyze.prof_exports.mstx_event_export.MstxMarkExport.read_export_db")
    @patch("msprof_analyze.prof_exports.mstx_event_export.MstxRangeExport.read_export_db")
    def test__mapper_func_should_return_mstx_stats_df(self, mock_read_export_db_range, mock_read_export_db_mark,
                                                      mock_read_export_db_step, mock_check_tables_in_db):
        data_map = {
            Constant.RANK_ID: 0,
            Constant.PROFILER_DB_PATH: "",
            Constant.ANALYSIS_DB_PATH: ""
        }
        step_df = pd.DataFrame({
            "step_id": [2, 3],
            "start_ns": [17373590271969746900, 1737359077257118820],
            "end_ns": [1737359077257169490, 1737359127323172440],
        })
        mark_df = pd.DataFrame({
            "msg": ['event_start', 'event_stop'],
            "cann_ts": [1737359047220383570, 1737359047220384570],
            "device_ts": [1737359047220483570, 1737359047220484570],
            "framework_ts": [1737359047220583570, 1737359047220584570],
            "tid": [1479977011069833, 1479977011069833]
        })
        range_df = pd.DataFrame({
            "msg": ['{"streamId": "36","count": "8"}', '{"streamId": "36","count": "9"}'],
            "cann_start_ts": [1737359047220383570, 1737359067238388560],
            "cann_end_ts": [1737359047220826170, 1737359067238792580],
            "device_start_ts": [1737359047220912568, 1737359067239429618],
            "device_end_ts": [1737359047221347417, 1737359067240932028],
            "tid": [1479977011069833, 1479977011069833]
        })
        mock_check_tables_in_db.return_value = True
        mock_read_export_db_range.return_value = range_df
        mock_read_export_db_mark.return_value = mark_df
        mock_read_export_db_step.return_value = step_df
        recipe = MstxSum({})
        result = recipe._mapper_func(data_map, "MstxSum")
        expected_result = pd.DataFrame({
            "FrameworkDurationNs": [1000.0, 0.0, 0.0],
            "CannDurationNs": [1000.0, 442600.0, 404020.0],
            "DeviceDurationNs": [1000.0, 434849.0, 1502410.0],
            "Rank": [0, 0, 0],
            "StepId": [0, 0, 0],
        }, index=['event', '{"streamId": "36","count": "8"}', '{"streamId": "36","count": "9"}'])
        self.assertTrue(result.equals(expected_result))

    def test_reduce_func_should_calculate_all_stats_df(self):
        index = pd.Index(
            data=['{"streamId": "36","count": "8"}', '{"streamId": "36","count": "9"}'],
            name="Name"
        )
        mapper_res = [
            pd.DataFrame({
                "FrameworkDurationNs": [0.0, 0.0],
                "CannDurationNs": [442600.0, 404020.0],
                "DeviceDurationNs": [434849.0, 1502410.0],
                "Rank": [0, 0],
                "StepId": [0, 0],
            }, index=index)
        ]
        expected_all_fwk_stats = pd.DataFrame({
            "FrameworkDurationNs": [0.0, 0.0],
            "CannDurationNs": [442600.0, 404020.0],
            "DeviceDurationNs": [434849.0, 1502410.0],
            "Rank": [0, 0],
            "StepId": [0, 0],
        })
        recipe = MstxSum({})
        recipe.reducer_func(mapper_res)
        self.assertEqual(recipe.all_fwk_stats.shape, (2, 13))
        self.assertEqual(recipe.all_device_stats.shape, (2, 13))
        self.assertEqual(recipe.all_cann_stats.shape, (2, 13))

    @patch("msprof_analyze.cluster_analyse.recipes.base_recipe_analysis.BaseRecipeAnalysis.dump_data")
    @patch("msprof_analyze.cluster_analyse.recipes.base_recipe_analysis.BaseRecipeAnalysis.add_helper_file")
    @patch("msprof_analyze.cluster_analyse.recipes.base_recipe_analysis.BaseRecipeAnalysis.create_notebook")
    @patch("msprof_analyze.cluster_analyse.recipes.hccl_sum.hccl_sum.HcclSum.reducer_func")
    @patch("msprof_analyze.cluster_analyse.recipes.base_recipe_analysis.BaseRecipeAnalysis.mapper_func")
    def test_run_should_save_db_or_notebook(self, mock_mapper_func, mock_reducer_func, mock_create_notebook,
                                            mock_add_helper_file, mock_dump_data):
        params = {Constant.EXPORT_TYPE: Constant.DB}
        recipe = MstxSum(params)
        recipe.run(context=None)
        recipe._export_type = "notebook"
        recipe.run(context=None)
