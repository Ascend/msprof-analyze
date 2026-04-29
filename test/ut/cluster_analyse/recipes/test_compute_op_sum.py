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

from msprof_analyze.cluster_analyse.recipes.compute_op_sum.compute_op_sum import ComputeOpSum
from msprof_analyze.prof_common.constant import Constant


class TestComputeOpSum(unittest.TestCase):
    PARAMS = {
        Constant.COLLECTION_PATH: "/data",
        Constant.DATA_MAP: {},
        Constant.DATA_TYPE: Constant.DB,
        Constant.CLUSTER_ANALYSIS_OUTPUT_PATH: "./test_compute_op_sum",
        Constant.RECIPE_NAME: "ComputeOpSum",
        Constant.RECIPE_CLASS: ComputeOpSum,
        Constant.PARALLEL_MODE: Constant.CONCURRENT_MODE,
        Constant.EXPORT_TYPE: Constant.DB,
        ComputeOpSum.RANK_LIST: Constant.ALL,
    }

    def test_reducer_func_when_exclude_op_name_switch_on_given_all_dataframe(self):
        df = pd.DataFrame({
            "OpType": ["ZerosLike", "Cast", "Slice"],
            "TaskType": ["AI_VECTOR_CORE", "AI_VECTOR_CORE", "AI_VECTOR_CORE"],
            "InputShapes": ["1903865856", "4,1025", "4,1025;2;2"],
            "Duration": [2553091.0, 3020.0, 2440.0],
            "Rank": [0, 0, 0]
        })
        params = {Constant.EXTRA_ARGS: ["--exclude_op_name"]}
        params.update(self.PARAMS)
        recipe = ComputeOpSum(params)
        recipe.reducer_func([df])
        self.assertEqual(recipe.all_rank_stats.shape, (3, 9))
        self.assertEqual(recipe.per_rank_stats_by_optype.shape, (3, 10))
        self.assertIsNone(recipe.per_rank_stats_by_opname, None)


    def test_reducer_func_when_exclude_op_name_switch_off_given_all_dataframe(self):
        df = pd.DataFrame({
            "OpName": ["aclnnInplaceZero_ZerosLikeAiCore_ZerosLike", "aclnnCast_CastAiCore_Cast",
                       "aclnnInplaceCopy_SliceAiCore_Slice"],
            "OpType": ["ZerosLike", "Cast", "Slice"],
            "TaskType": ["AI_VECTOR_CORE", "AI_VECTOR_CORE", "AI_VECTOR_CORE"],
            "InputShapes": ["1903865856", "4,1025", "4,1025;2;2"],
            "Duration": [2553091.0, 3020.0, 2440.0],
            "Rank": [0, 0, 0]
        })
        params = {}
        params.update(self.PARAMS)
        recipe = ComputeOpSum(params)
        recipe.reducer_func([df])
        self.assertEqual(recipe.all_rank_stats.shape, (3, 9))
        self.assertEqual(recipe.per_rank_stats_by_optype.shape, (3, 10))
        self.assertEqual(recipe.per_rank_stats_by_opname.shape, (3, 10))

    @patch("msprof_analyze.cluster_analyse.recipes.base_recipe_analysis.BaseRecipeAnalysis.dump_data")
    @patch("msprof_analyze.cluster_analyse.recipes.base_recipe_analysis.BaseRecipeAnalysis.mapper_func")
    def test_run_should_return_early_when_mapper_result_is_empty(self, mock_mapper_func, mock_dump_data):
        mock_mapper_func.return_value = []
        recipe = ComputeOpSum(self.PARAMS)

        recipe.run(context=None)

        mock_dump_data.assert_not_called()
        self.assertIsNone(recipe.all_rank_stats)
        self.assertIsNone(recipe.per_rank_stats_by_optype)
        self.assertIsNone(recipe.per_rank_stats_by_opname)
