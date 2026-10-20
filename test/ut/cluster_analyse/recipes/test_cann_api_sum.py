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

from msprof_analyze.cluster_analyse.recipes.cann_api_sum.cann_api_sum import CannApiSum
from msprof_analyze.prof_common.constant import Constant


class TestCannApiSum(unittest.TestCase):

    @patch("msprof_analyze.cluster_analyse.recipes.base_recipe_analysis.BaseRecipeAnalysis.dump_data")
    @patch("msprof_analyze.cluster_analyse.recipes.base_recipe_analysis.BaseRecipeAnalysis.add_helper_file")
    @patch("msprof_analyze.cluster_analyse.recipes.base_recipe_analysis.BaseRecipeAnalysis.create_notebook")
    @patch("msprof_analyze.cluster_analyse.recipes.base_recipe_analysis.BaseRecipeAnalysis.mapper_func")
    def test_run_should_save_db_or_notebook(self, mock_mapper_func, mock_create_notebook,
                                            mock_add_helper_file, mock_dump_data):
        mock_mapper_func.return_value = [
            (0, pd.DataFrame({
                    "name": ["aclnnCast"],
                    "durationRatio": [1.05],
                    "totalTimeNs": [761090],
                    "totalCount": [72],
                    "averageNs": [10570.7],
                    "minNs": [5530.0],
                    "Q1Ns": [6892.5],
                    "medNs": [9035.0],
                    "Q3Ns": [12910.0],
                    "maxNs": [28000.0],
                    "stdev": [4755.2]
                })
            ),
            (1, pd.DataFrame({
                    "name": ["aclnnMseLoss"],
                    "durationRatio": [1.09],
                    "totalTimeNs": [271560],
                    "totalCount": [6],
                    "averageNs": [45260.7],
                    "minNs": [29240.0],
                    "Q1Ns": [35815.0],
                    "medNs": [52785.0],
                    "Q3Ns": [53075.0],
                    "maxNs": [53420.0],
                    "stdev": [10981.2]
            }))
        ]
        params = {Constant.EXPORT_TYPE: Constant.DB}
        recipe = CannApiSum(params)
        recipe.run(context=None)
        recipe._export_type = "notebook"
        recipe.run(context=None)
        self.assertEqual(recipe._stats_data.shape, (2, 12))
        self.assertEqual(recipe._stats_rank_data.shape, (2, 12))
        self.assertEqual(recipe._stats_data.iloc[0, 0], 73.7)
        self.assertEqual(recipe._stats_data.iloc[1, 0], 26.3)
