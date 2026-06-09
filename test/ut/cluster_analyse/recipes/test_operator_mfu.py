# pylint: disable=duplicate-code
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

import tempfile
import unittest
from unittest.mock import Mock, patch

import pandas as pd

from msprof_analyze.cluster_analyse.recipes.operator_mfu.operator_mfu import OperatorMfu
from msprof_analyze.cluster_analyse.recipes.operator_mfu.tree_build import (
    KernelNode as OperatorMfuKernelNode,
    TreeBuilder as OperatorMfuTreeBuilder,
)
from msprof_analyze.cluster_analyse.recipes.module_statistic.module_statistic import ModuleStatistic
from msprof_analyze.cluster_analyse.recipes.module_statistic.tree_build import TreeBuilder as ModuleStatisticTreeBuilder
from msprof_analyze.prof_common.constant import Constant


class TestOperatorMfu(unittest.TestCase):
    """测试算子 MFU 分析任务。"""

    def setUp(self):
        """创建使用临时输出目录的分析任务。"""
        self.temp_dir = tempfile.TemporaryDirectory()  # pylint: disable=consider-using-with
        params = {
            Constant.COLLECTION_PATH: self.temp_dir.name,
            Constant.RECIPE_NAME: "operator_mfu",
            Constant.EXPORT_TYPE: Constant.TEXT,
            Constant.CLUSTER_ANALYSIS_OUTPUT_PATH: self.temp_dir.name,
        }
        self.analysis = OperatorMfu(params)

    def tearDown(self):
        """清理临时输出目录。"""
        self.temp_dir.cleanup()

    def test_run_when_save_is_false_then_return_valid_mapper_results(self):
        """测试 save=False 时保留包含 MFU 数据的 rank 结果。"""
        kernel_df = pd.DataFrame({'mfu': [0.5]})
        module_df = pd.DataFrame()
        mapper_res = [
            (0, kernel_df, module_df),
            (1, pd.DataFrame(), pd.DataFrame()),
        ]

        with patch.object(self.analysis, 'mapper_func', return_value=mapper_res):
            result = self.analysis.run(context=None, save=False)

        self.assertEqual([(0, kernel_df, module_df)], result)

    def test_generate_kernel_mfu_list_when_format_text_then_rename_duration_column(self):
        """测试 kernel 时长列能够按文本导出格式重命名。"""
        kernel_df = pd.DataFrame(
            [
                {
                    'op_name': 'op',
                    'kernel_name': 'kernel',
                    'kernel_ts': 10,
                    'kernel_end': 30,
                    'kernel_duration': 20,
                    'mfu': 0.5,
                    'chip_peak': 100 * 1e12,
                }
            ]
        )

        result = self.analysis._generate_kernel_mfu_list(kernel_df, rank_id=0)
        formatted_result = self.analysis._format_kernel_mfu_columns(result, Constant.TEXT)

        self.assertEqual(20, formatted_result.iloc[0]['Kernel Duration(ns)'])
        self.assertNotIn('kernel_duration', formatted_result.columns)

    def test_format_module_mfu_columns_when_export_db_then_keep_module_column(self):
        """测试 DB 导出格式显式保留 module 列。"""
        module_df = pd.DataFrame(
            [
                {
                    'rank_id': 0,
                    'module_parent': 'parent',
                    'module': 'module',
                    'op_name': 'op',
                    'kernel_list': 'kernel',
                    'op_count': 1,
                    'total_kernel_duration': 8,
                    'avg_kernel_duration': 8,
                    'avg_mfu': '50.0%',
                }
            ]
        )

        result = self.analysis._format_module_mfu_columns(module_df, Constant.DB)

        self.assertIn('module', result.columns)
        self.assertIn('parent_module', result.columns)
        self.assertIn('op_name', result.columns)
        self.assertNotIn('parentModule', result.columns)
        self.assertNotIn('opName', result.columns)
        self.assertEqual('module', result.iloc[0]['module'])

    def test_format_kernel_mfu_columns_when_export_db_then_use_snake_case_columns(self):
        """测试 DB 导出格式使用统一的 snake_case 列名。"""
        kernel_df = pd.DataFrame(
            [
                {
                    'rank_id': 0,
                    'op_name': 'op',
                    'kernel_name': 'kernel',
                    'kernel_ts': 10,
                    'kernel_end': 30,
                    'kernel_duration': 20,
                    'mfu': 0.5,
                }
            ]
        )

        result = self.analysis._format_kernel_mfu_columns(kernel_df, Constant.DB)

        self.assertIn('rank_id', result.columns)
        self.assertIn('op_name', result.columns)
        self.assertIn('kernel_start(ns)', result.columns)
        self.assertIn('kernel_duration(ns)', result.columns)
        self.assertNotIn('rankID', result.columns)
        self.assertNotIn('opName', result.columns)

    def test_tree_builder_when_import_from_operator_mfu_then_reuse_module_statistic_builder(self):
        """测试 operator_mfu 复用 module_statistic 的树构建器。"""
        self.assertIs(OperatorMfuTreeBuilder, ModuleStatisticTreeBuilder)

    def test_kernel_node_when_import_from_operator_mfu_then_keep_mfu(self):
        """测试 operator_mfu kernel 节点保留原有 MFU 接口。"""
        node = OperatorMfuKernelNode(0, 10, 'kernel', 0.5)

        self.assertEqual(0.5, node.mfu)

    def test_operator_mfu_then_inherit_module_statistic(self):
        """测试 operator_mfu 通过继承复用 module_statistic 能力。"""
        self.assertIsInstance(self.analysis, ModuleStatistic)
        self.assertIs(OperatorMfu._query_framework_op_to_kernel, ModuleStatistic._query_framework_op_to_kernel)
        self.assertIs(OperatorMfu._build_complete_tree, ModuleStatistic._build_complete_tree)

    def test_generate_module_mfu_stats_then_add_mfu_to_reused_flatten_result(self):
        """测试复用树展开结果后仍能生成 module 级 MFU。"""
        verbose_df = pd.DataFrame(
            [
                {
                    'module_parent': 'parent',
                    'module': 'module',
                    'module_start': 0,
                    'module_end': 100,
                    'op_name': 'op',
                    'op_start': 10,
                    'op_end': 20,
                    'kernel_list': 'kernel',
                    'device_time': 8,
                }
            ]
        )
        kernel_df = pd.DataFrame(
            [
                {
                    'op_name': 'op',
                    'op_ts': 10,
                    'op_end': 20,
                    'mfu': 0.5,
                }
            ]
        )
        self.analysis._flatten_tree_to_dataframe = Mock(return_value=verbose_df)

        result = self.analysis._generate_module_mfu_stats(Mock(), rank_id=1, kernel_df=kernel_df)

        self.assertEqual(1, result.iloc[0]['rank_id'])
        self.assertEqual('50.0%', result.iloc[0]['avg_mfu'])

    def test_aggregate_module_mfu_stats_when_multiple_ranks_then_keep_rank_groups_separate(self):
        """测试 module 级 MFU 聚合不会合并不同 rank 的数据。"""
        df = pd.DataFrame(
            [
                {
                    'rank_id': 0,
                    'module_parent': 'parent',
                    'module': 'module',
                    'module_start': 0,
                    'module_end': 100,
                    'op_name': 'op',
                    'op_start': 10,
                    'kernel_list': 'kernel',
                    'device_time': 8,
                    'mfu_list': [0.5],
                },
                {
                    'rank_id': 1,
                    'module_parent': 'parent',
                    'module': 'module',
                    'module_start': 0,
                    'module_end': 100,
                    'op_name': 'op',
                    'op_start': 10,
                    'kernel_list': 'kernel',
                    'device_time': 8,
                    'mfu_list': [0.7],
                },
            ]
        )

        result = self.analysis._aggregate_module_mfu_stats(df)

        self.assertEqual({0, 1}, set(result['rank_id']))
        self.assertEqual({'50.0%', '70.0%'}, set(result['avg_mfu']))
