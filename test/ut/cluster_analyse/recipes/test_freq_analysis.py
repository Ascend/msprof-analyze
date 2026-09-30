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


import random
import unittest
from unittest.mock import patch

import pandas as pd

from msprof_analyze.cluster_analyse.recipes.freq_analysis.freq_analysis import FreqAnalysis
from msprof_analyze.prof_common.constant import Constant


NAMESPACE = "msprof_analyze.cluster_analyse.recipes"


class TestFreqAnalysis(unittest.TestCase):

    freq = [1800]
    free_freq = [800, 1800]
    abnormal_freq = [1200, 1300, 1800]

    def test_no_error_freq(self):
        params = {}
        recipe = FreqAnalysis(params)
        mapper_res = [(self.freq, 0)] * 10
        recipe.reducer_func(mapper_res)
        self.assertEqual(recipe.free_freq_ranks, [])
        self.assertEqual(recipe.abnormal_freq_ranks, [])
        self.assertEqual(recipe.abnormal_freq_ranks_map, {})


    def test_free_rank_map(self):
        params = {}
        recipe = FreqAnalysis(params)
        mapper_res = [
            (self.freq, 0),
            (self.free_freq, 1),
            (self.free_freq, 2),
            (self.freq, 3)
        ]
        recipe.reducer_func(mapper_res)
        self.assertEqual(recipe.free_freq_ranks, [1, 2])
        self.assertEqual(recipe.abnormal_freq_ranks, [])
        self.assertEqual(recipe.abnormal_freq_ranks_map, {})

    def test_abnormal_rank_map(self):
        params = {}
        recipe = FreqAnalysis(params)
        mapper_res = [
            (self.freq, 0),
            (self.abnormal_freq, 1),
            (self.abnormal_freq, 2),
            (self.freq, 3)
        ]

        recipe.reducer_func(mapper_res)
        self.assertEqual(recipe.free_freq_ranks, [])
        self.assertEqual(recipe.abnormal_freq_ranks, [1, 2])

    def test_mix_freq_case(self):
        params = {}
        recipe = FreqAnalysis(params)
        mapper_res = []
        rank_case = [[], [], []]
        random_freq = {0: self.freq, 1: self.free_freq, 2: self.abnormal_freq}

        for i in range(1000):
            random_num = random.choice([0, 1, 2])
            mapper_res.append((random_freq.get(random_num, self.freq), i))
            rank_case[random_num].append(i)

        recipe.reducer_func(mapper_res)
        self.assertEqual(recipe.free_freq_ranks, rank_case[1])
        self.assertEqual(recipe.abnormal_freq_ranks, rank_case[2])

    @patch("msprof_analyze.prof_common.path_manager.PathManager.check_output_directory_path")
    @patch("msprof_analyze.prof_common.database_service.DatabaseService.query_data")
    def test__mapper_func_should_return_freq_and_rank_id(self, mock_query_data, mock_check_output_directory_path):
        data_map = {
            Constant.RANK_ID: 0,
            Constant.PROFILER_DB_PATH: "",
            Constant.ANALYSIS_DB_PATH: ""
        }
        df_dict = {
            "AICORE_FREQ": pd.DataFrame({
                "deviceId": [0, 0],
                "freq": [1800, 1800],
            }),
            "RANK_DEVICE_MAP": pd.DataFrame({
                "rankId": [0, 0],
            })
        }
        mock_query_data.return_value = df_dict
        recipe = FreqAnalysis({})
        result = recipe._mapper_func(data_map, "FreqAnalysis")
        self.assertEqual(result, ([1800], 0))

    @patch("msprof_analyze.prof_common.path_manager.PathManager.check_output_directory_path")
    @patch(NAMESPACE + ".base_recipe_analysis.BaseRecipeAnalysis.dump_data")
    @patch(NAMESPACE + ".base_recipe_analysis.BaseRecipeAnalysis.mapper_func")
    def test_run_should_save_db(self, mock_mapper_func, mock_dump_data, mock_check_output_directory_path):
        mock_mapper_func.return_value = [
            ([800, 1800], 0),
            ([800, 1800, 1150], 1),
        ]
        params = {Constant.EXPORT_TYPE: Constant.DB}
        recipe = FreqAnalysis(params)
        recipe.run(context=None)
