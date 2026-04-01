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

from msprof_analyze.cluster_analyse.recipes.slow_rank.slow_rank import (judge_norm, judge_dixon,
                                                                        SlowRankVoteAnalysis, SlowRankAnalysis)
from msprof_analyze.prof_common.constant import Constant


class TestJudgeNorm(unittest.TestCase):
    def test_no_outlier(self):
        data_list = [10] * 120
        res = judge_norm(data_list)
        self.assertEqual(res, [])
    
    def test_with_outlier(self):
        data_with_outlier = [10] * 120
        data_with_outlier.append(0)
        res = judge_norm(data_with_outlier)
        self.assertEqual(res, [120])


class TestJudgeDixon(unittest.TestCase):
    def test_no_outlier(self):
        for i in [6, 8, 12, 30]:
            data_list = [100 + j for j in range(i)]
            res = judge_dixon(data_list)
            self.assertEqual(res, [])
    
    def test_with_outlier(self):
        for i in [6, 8, 12, 30]:
            data_with_outlier = [100 + j for j in range(i)]
            data_with_outlier.append(0)
            res = judge_dixon(data_with_outlier)
            self.assertEqual(res, [i])

    def test_judge_dixon_should_return_empty_list_when_time_list_length_less_than_3(self):
        self.assertEqual(judge_dixon([1, 2]), [])

    def test_judge_dixon_should_return_empty_list_when_the_denominator_maybe_zero(self):
        self.assertEqual(judge_dixon([1, 2, 3, 3, 1]), [])


class TestVoteAnalysis(unittest.TestCase):
    
    @staticmethod
    def init_cmm_ops_df(group_0_op_0_num, group_0_op_1_num, group_1_op_0_num):
        comm_ops_df = pd.DataFrame(columns=["rankId", "groupName", "opName", "communication_times"])
        for i in range(group_0_op_0_num):
            comm_ops_df.loc[len(comm_ops_df)] = [i, "group_0", "op_0", 0]
        for i in range(group_0_op_1_num):
            comm_ops_df.loc[len(comm_ops_df)] = [i, "group_0", "op_1", 0]
        for i in range(group_1_op_0_num):
            comm_ops_df.loc[len(comm_ops_df)] = [i, "group_1", "op_0", 0]
        return comm_ops_df
    
    def test_grouping_ops(self):
        group_0_op_0_num = 10
        group_0_op_1_num = 10
        group_1_op_0_num = 5
        comm_ops_df = self.init_cmm_ops_df(group_0_op_0_num, group_0_op_1_num, group_1_op_0_num)
        analyzer = SlowRankVoteAnalysis(comm_ops_df)
        res = analyzer.grouping_ops()
        res = dict(res)
        for key in res.keys():
            res[key] = dict(res[key])
        golden_res = {
            "group_0": {
                "op_0": [i for i in range(group_0_op_0_num)],
                "op_1": [i + group_0_op_0_num for i in range(group_0_op_1_num)]
            },
            "group_1": {
                "op_0": [i + group_0_op_0_num + group_0_op_1_num for i in range(group_1_op_0_num)]
            }
            }
        self.assertEqual(res, golden_res)

    def test_grouping_ops_with_exclude(self):
        group_0_op_0_num = 10
        group_0_op_1_num = 12
        group_1_op_0_num = 5
        comm_ops_df = self.init_cmm_ops_df(group_0_op_0_num, group_0_op_1_num, group_1_op_0_num)
        analyzer = SlowRankVoteAnalysis(comm_ops_df)
        res = analyzer.grouping_ops()
        res = dict(res)
        for key in res.keys():
            res[key] = dict(res[key])
        golden_res = {
            "group_1": {
                "op_0": [i for i in range(group_1_op_0_num)]
            }
            }
        self.assertEqual(res, golden_res)


    def test_calculate_basic_stats(self):
        time_list = [1.5, 2.5, 3.5, 4.5]
        result = SlowRankVoteAnalysis.calculate_basic_stats(time_list)

        expected = {
            'Count': 4,
            'MeanNs': 3.0,
            'StdNs': 1.290994,
            'MinNs': 1.5,
            'Q1Ns': 2.25,
            'MedianNs': 3.0,
            'Q3Ns': 3.75,
            'MaxNs': 4.5,
            'SumNs': 12.0
        }

        for key in expected:
            if key == 'StdNs':
                self.assertAlmostEqual(result[key], expected[key], places=2)
            else:
                self.assertEqual(result[key], expected[key])


class TestSlowRankAnalysis(unittest.TestCase):

    @patch("msprof_analyze.cluster_analyse.recipes.base_recipe_analysis.BaseRecipeAnalysis.dump_data")
    @patch("msprof_analyze.cluster_analyse.recipes.base_recipe_analysis.BaseRecipeAnalysis.add_helper_file")
    @patch("msprof_analyze.cluster_analyse.recipes.base_recipe_analysis.BaseRecipeAnalysis.create_notebook")
    @patch("msprof_analyze.cluster_analyse.recipes.base_recipe_analysis.BaseRecipeAnalysis.mapper_func")
    def test_run_should_save_db_or_notebook(self, mock_mapper_func, mock_create_notebook,
                                            mock_add_helper_file, mock_dump_data):
        mock_mapper_func.return_value = [
            pd.DataFrame({
                "rankId": [0, 0],
                "groupName": ["100%enp189s0f1_55000_0_1738895521183247", "100%enp189s0f1_55000_0_1738895521183247"],
                "opName": ["hcom_broadcast__559_0_1", "hcom_broadcast__559_0_1"],
                "startNs": [10.0, 20.0],
                "communication_time": [16225.3, 555.7]
            }),
            pd.DataFrame({
                "rankId": [1, 1],
                "groupName": ["100%enp189s0f1_55000_0_1738895521183247", "100%enp189s0f1_55000_0_1738895521183247"],
                "opName": ["hcom_broadcast__559_0_1", "hcom_broadcast__559_0_1"],
                "startNs": [15.0, 22.0],
                "communication_time": [24224.1, 555.6]
            })
        ]
        params = {Constant.EXPORT_TYPE: Constant.DB}
        recipe = SlowRankAnalysis(params)
        recipe.run(context=None)
        recipe._export_type = "notebook"
        recipe.run(context=None)