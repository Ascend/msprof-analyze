# -------------------------------------------------------------------------
# This file is part of the MindStudio project.
# Copyright (c) 2026 Huawei Technologies Co.,Ltd.
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
import argparse
import pandas as pd

from unittest.mock import MagicMock, patch
from msprof_analyze.cluster_analyse.recipes.computational_op_masking.computational_op_masking import (
    ComputationalOpMasking,
)


class TestComputationalOpMasking(unittest.TestCase):
    def setUp(self):
        # Initialize the test environment.
        self.params = {"recipe_name": "test_recipe", "args": ["--parallel_types", "dp,edp;edp;dp"]}
        self.computational_op_masking = ComputationalOpMasking(self.params)

    def test_parse_parallel_type(self):
        # Test empty input.
        self.assertEqual(ComputationalOpMasking.parse_parallel_type(""), [])

        # Test single item.
        self.assertEqual(ComputationalOpMasking.parse_parallel_type("dp"), [("dp",)])

        # Test multiple items in one group.
        self.assertEqual(ComputationalOpMasking.parse_parallel_type("dp,edp"), [("dp", "edp")])

        # Test multiple groups.
        self.assertEqual(ComputationalOpMasking.parse_parallel_type("dp;edp"), [("dp",), ("edp",)])

        # Test multiple groups with multiple items.
        self.assertEqual(ComputationalOpMasking.parse_parallel_type("dp,edp;mp,tp"), [("dp", "edp"), ("mp", "tp")])

        # Test whitespace handling.
        self.assertEqual(
            ComputationalOpMasking.parse_parallel_type(" dp, edp ; mp , tp "), [("dp", "edp"), ("mp", "tp")]
        )

        # Test empty group (should raise error).
        with self.assertRaises(argparse.ArgumentTypeError):
            ComputationalOpMasking.parse_parallel_type("dp;;edp")

        # Test empty item in group (should raise error).
        with self.assertRaises(argparse.ArgumentTypeError):
            ComputationalOpMasking.parse_parallel_type("dp,;edp")

    def test_aggregate_stats(self):
        # Create mock context with future_dict.
        mock_context = MagicMock()
        mock_future1 = MagicMock()
        mock_future2 = MagicMock()

        # Mock future results.
        df1 = pd.DataFrame({"stepId": [1], "time": [100]})
        df2 = pd.DataFrame({"stepId": [2], "time": [200]})

        mock_future1.result.return_value = df1
        mock_future2.result.return_value = df2

        # Mock future_dict.
        mock_context.future_dict = {"step_linearity": [mock_future1, mock_future2]}
        result = self.computational_op_masking.aggregate_stats(mock_context)
        self.assertEqual(len(result), 2)
        self.assertIn(1, result["stepId"].values)
        self.assertIn(2, result["stepId"].values)

        # Test with empty futures.
        mock_context.future_dict = {"step_linearity": []}
        result = self.computational_op_masking.aggregate_stats(mock_context)
        self.assertTrue(result.empty)

    def test_base_dir(self):
        """测试 base_dir 属性"""
        self.assertEqual(self.computational_op_masking.base_dir, "computational_op_masking")

    def test_init_with_default_parallel_types(self):
        """测试默认并行类型初始化"""
        params = {"extra_args": {}}
        analyzer = ComputationalOpMasking(params)
        # 验证默认值不为空且是列表
        self.assertIsInstance(analyzer.parallel_types, list)
        self.assertTrue(len(analyzer.parallel_types) > 0)
        # 验证每个元素都是元组
        for pt in analyzer.parallel_types:
            self.assertIsInstance(pt, tuple)
        # 验证默认值包含预期的并行类型
        expected_default = [("dp", "edp"), ("edp",), ("dp",), ("ep",), ("pp",), ("mp",), ("tp",)]
        self.assertEqual(analyzer.parallel_types, expected_default)

    def test_init_with_custom_parallel_types(self):
        """测试自定义并行类型初始化"""
        analyzer = ComputationalOpMasking(self.params)
        # 注意：_extra_args 中存储的可能是原始值，也可能是转换后的值
        # 我们直接验证 parallel_types 是否被正确设置
        expected = [("dp", "edp"), ("edp",), ("dp",)]
        self.assertEqual(analyzer.parallel_types, expected)

    def test_init_with_empty_extra_args(self):
        """测试空 extra_args 的情况"""
        params = {}
        analyzer = ComputationalOpMasking(params)
        # 应该使用默认值
        expected_default = [("dp", "edp"), ("edp",), ("dp",), ("ep",), ("pp",), ("mp",), ("tp",)]
        self.assertEqual(analyzer.parallel_types, expected_default)

    @patch('msprof_analyze.cluster_analyse.recipes.computational_op_masking.computational_op_masking.LinearityUtils')
    def test_get_linearity_df(self, mock_linearity_utils):
        """测试 get_linearity_df 方法"""
        # 创建 mock 对象
        mock_linearity_utils.compute_linearity_df.return_value = pd.DataFrame(
            {"stepId": [1], "parallelType": ["dp"], "ratioOfUnmaskedCommunication": [0.5]}
        )

        data_map = {"profiler_db_path": "test.db", "step_range": {"startNs": 0, "endNs": 100}}
        analysis_class = "test_analysis"

        result = self.computational_op_masking.get_linearity_df(data_map, analysis_class)

        # 验证 LinearityUtils.compute_linearity_df 被正确调用
        mock_linearity_utils.compute_linearity_df.assert_called_once()
        call_args = mock_linearity_utils.compute_linearity_df.call_args[1]
        self.assertEqual(call_args["data_map"], data_map)
        self.assertEqual(call_args["analysis_class"], analysis_class)
        self.assertEqual(call_args["parallel_types"], self.computational_op_masking.parallel_types)
        self.assertEqual(call_args["step_columns"], ["id", "startNs", "endNs"])
        self.assertEqual(call_args["parallel_col_name"], "parallelType")
        self.assertEqual(call_args["target_step_id"], None)  # _step_id = -1 时返回 None
        self.assertTrue(call_args["use_merge"])

        # 验证返回值
        self.assertIsInstance(result, pd.DataFrame)
        self.assertEqual(len(result), 1)

    @patch('msprof_analyze.cluster_analyse.recipes.computational_op_masking.computational_op_masking.LinearityUtils')
    def test_get_linearity_df_with_step_id(self, mock_linearity_utils):
        """测试 get_linearity_df 方法（指定 step_id）"""
        # 设置 _step_id
        self.computational_op_masking._step_id = 5

        mock_linearity_utils.compute_linearity_df.return_value = pd.DataFrame(
            {"stepId": [5], "parallelType": ["dp"], "ratioOfUnmaskedCommunication": [0.3]}
        )

        data_map = {"profiler_db_path": "test.db", "step_range": {"startNs": 0, "endNs": 100}}
        analysis_class = "test_analysis"

        result = self.computational_op_masking.get_linearity_df(data_map, analysis_class)

        # 验证 target_step_id 被正确传递
        call_args = mock_linearity_utils.compute_linearity_df.call_args[1]
        self.assertEqual(call_args["target_step_id"], 5)

        self.assertEqual(len(result), 1)
        self.assertEqual(result.iloc[0]["stepId"], 5)


if __name__ == '__main__':
    unittest.main(verbosity=2)
