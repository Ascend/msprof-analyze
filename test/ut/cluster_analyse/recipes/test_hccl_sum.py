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

from msprof_analyze.cluster_analyse.recipes.hccl_sum.hccl_sum import HcclSum
from msprof_analyze.prof_common.constant import Constant


class TestHcclSum(unittest.TestCase):

    def test_reduce_func_should_calculate_all_stats_df(self):
        mapper_res = [
            pd.DataFrame({
                "OpName": ["hcom_allReduce__659_0_1"],
                "OpType": ["hcom_allReduce"],
                "Duration": [20400.0],
                "GroupName": ["123%enp123abc_600001_1_17375465987622656"],
                "Rank": [0],
            }),
            pd.DataFrame({
                "OpName": ["hcom_allReduce__659_0_1"],
                "OpType": ["hcom_allReduce"],
                "Duration": [881780.0],
                "GroupName": ["123%enp123abc_600001_1_17375465987622656"],
                "Rank": [1],
            })
        ]
        recipe = HcclSum({})
        recipe.reducer_func(mapper_res)
        self.assertEqual(recipe.all_rank_stats.shape, (1, 9))
        self.assertEqual(recipe.per_rank_stats.shape, (2, 10))
        self.assertEqual(recipe.top_op_stats.shape, (1, 11))
        self.assertEqual(recipe.group_name_map.shape, (1, 2))

    @patch("msprof_analyze.cluster_analyse.recipes.base_recipe_analysis.BaseRecipeAnalysis.dump_data")
    @patch("msprof_analyze.cluster_analyse.recipes.base_recipe_analysis.BaseRecipeAnalysis.add_helper_file")
    @patch("msprof_analyze.cluster_analyse.recipes.base_recipe_analysis.BaseRecipeAnalysis.create_notebook")
    @patch("msprof_analyze.cluster_analyse.recipes.hccl_sum.hccl_sum.HcclSum.reducer_func")
    @patch("msprof_analyze.cluster_analyse.recipes.base_recipe_analysis.BaseRecipeAnalysis.mapper_func")
    def test_run_should_save_db_or_notebook(self, mock_mapper_func, mock_reducer_func, mock_create_notebook,
                                            mock_add_helper_file, mock_dump_data):
        params = {Constant.EXPORT_TYPE: Constant.DB}
        recipe = HcclSum(params)
        recipe.run(context=None)
        recipe._export_type = "notebook"
        recipe.run(context=None)
