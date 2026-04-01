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
from unittest.mock import patch, MagicMock, Mock
import pandas as pd

from msprof_analyze.cluster_analyse.recipes.module_statistic.module_statistic import ModuleStatistic
from msprof_analyze.cluster_analyse.recipes.module_statistic.tree_build import (NodeType, TreeNode,
                                                                                ModuleNode, KernelNode)
from msprof_analyze.prof_common.constant import Constant


class TestModuleStatistic(unittest.TestCase):
    def setUp(self):
        self.params = {
            Constant.COLLECTION_PATH: "/tmp",
            Constant.DATA_MAP: {},
            Constant.RECIPE_NAME: "ModuleStatistic",
            Constant.PARALLEL_MODE: "concurrent",
            Constant.EXPORT_TYPE: Constant.DB,
            Constant.CLUSTER_ANALYSIS_OUTPUT_PATH: "/tmp/output",
            Constant.RANK_LIST: Constant.ALL,
        }
        self.analysis = ModuleStatistic(self.params)
        self.recipe_name = "test_module_statistic"
        self.mock_module_data = pd.DataFrame({
            'startNs': [1000, 2000, 3000],
            'endNs': [1500, 2500, 3500],
            'name': ['module1', 'module2', 'module3'],
            'pid': [123, 123, 123],
            'tid': [456, 456, 456]
        })

        self.mock_kernel_data = pd.DataFrame({
            'kernel_ts': [1100, 2100, 3100],
            'kernel_end': [1200, 2200, 3200],
            'op_ts': [1050, 2050, 3050],
            'op_end': [1250, 2250, 3250],
            'kernel_name': ['kernel1', 'kernel2', 'kernel3']
        })

        self.mock_data_map = {
            'profiler_db_path': '/fake/path/to/profiler.db',
            'rank_id': '0'
        }

    @patch("msprof_analyze.cluster_analyse.recipes.module_statistic.module_statistic.ModuleStatistic.mapper_func")
    @patch("msprof_analyze.cluster_analyse.recipes.module_statistic.module_statistic.ModuleStatistic.save_db")
    @patch("msprof_analyze.cluster_analyse.recipes.module_statistic.module_statistic.ModuleStatistic.save_excel")
    def test_run_when_export_type_is_db_then_save_db_called(self, mock_save_excel, mock_save_db, mock_mapper_func):
        """测试run方法，export_type为DB时应调用save_db"""
        self.analysis._export_type = Constant.DB
        mock_mapper_func.return_value = [(0, pd.DataFrame({"a": [1]}))]
        self.analysis.run(context=None)
        mock_save_db.assert_called()
        mock_save_excel.assert_not_called()

    @patch("msprof_analyze.cluster_analyse.recipes.module_statistic.module_statistic.ModuleStatistic.mapper_func")
    @patch("msprof_analyze.cluster_analyse.recipes.module_statistic.module_statistic.ModuleStatistic.save_db")
    @patch("msprof_analyze.cluster_analyse.recipes.module_statistic.module_statistic.ModuleStatistic.save_excel")
    def test_run_when_export_type_is_text_then_save_csv_called(self, mock_save_excel, mock_save_db, mock_mapper_func):
        """测试run方法，export_type为TEXT时应调用save_csv"""
        self.analysis._export_type = Constant.TEXT
        mock_mapper_func.return_value = [(0, pd.DataFrame({"a": [1]}))]
        self.analysis.run(context=None)
        mock_save_excel.assert_called()
        mock_save_db.assert_not_called()

    @patch("msprof_analyze.cluster_analyse.recipes.module_statistic.module_statistic.ModuleStatistic.mapper_func")
    @patch("msprof_analyze.cluster_analyse.recipes.module_statistic.module_statistic.ModuleStatistic.save_db")
    @patch("msprof_analyze.cluster_analyse.recipes.module_statistic.module_statistic.ModuleStatistic.save_excel")
    @patch("msprof_analyze.cluster_analyse.recipes.module_statistic.module_statistic.logger")
    def test_run_when_export_type_is_notebook_then_error(self, mock_logger, mock_save_excel, mock_save_db,
                                                         mock_mapper_func):
        """测试run方法，export_type为notebook时应save_csv/save_db都不调用，logger有error打屏"""
        self.analysis._export_type = Constant.NOTEBOOK
        mock_mapper_func.return_value = [(0, pd.DataFrame({"a": [1]}))]
        self.analysis.run(context=None)
        self.assertTrue(mock_logger.error.called)
        mock_save_excel.assert_not_called()
        mock_save_db.assert_not_called()

    def test_reducer_func_when_mapper_res_is_empty_then_return_none(self):
        """测试reducer_func，输入为空时应返回None"""
        result = self.analysis.reducer_func([])
        self.assertIsNone(result)

    def test_reducer_func_when_mapper_res_has_valid_df_then_concat(self):
        """测试reducer_func，输入有有效DataFrame时应返回拼接结果"""
        df1 = pd.DataFrame({"a": [1]})
        df2 = pd.DataFrame({"a": [2]})
        res = [(0, df1), (1, df2)]
        out = self.analysis.reducer_func(res)
        self.assertEqual(len(out), 2)
        self.assertIn("rankID", out.columns)

    def test_reducer_func_when_mapper_res_has_empty_df_then_skip_concat_this_df(self):
        """测试reducer_func，输入有DataFrame Empty时返回的拼接结果不包含对应Rank"""
        df1 = pd.DataFrame({"a": [1]})
        df2 = pd.DataFrame(columns=["a"])
        res = [(0, df1), (1, df2)]
        out = self.analysis.reducer_func(res)
        self.assertEqual(len(out), 1)
        self.assertIn(0, out["rankID"].tolist())
        self.assertNotIn(1, out["rankID"].tolist())

    @patch("msprof_analyze.cluster_analyse.recipes.module_statistic.module_statistic.logger")
    def test_save_db_when_df_is_none_or_empty_then_warn(self, mock_logger):
        """测试save_db，df为None或empty时应记录warning"""
        self.analysis.save_db(None)
        self.analysis.save_db(pd.DataFrame())
        self.assertTrue(mock_logger.warning.called)

    @patch("msprof_analyze.cluster_analyse.recipes.module_statistic.module_statistic.ExcelUtils")
    @patch("msprof_analyze.cluster_analyse.recipes.module_statistic.module_statistic.logger")
    def test_save_csv_when_stat_df_empty_then_warn(self, mock_logger, mock_excel_utils):
        """测试save_csv，stat_df为空时应记录warning"""
        mock_excel = MagicMock()
        mock_excel_utils.return_value = mock_excel
        self.analysis._output_path = "/tmp"
        mapper_res = [(0, pd.DataFrame())]
        self.analysis.save_excel(mapper_res)
        self.assertTrue(mock_logger.warning.called)

    def test_format_stat_df_columns_when_export_type_db_then_rename(self):
        """测试_format_stat_df_columns，export_type为DB时应重命名列"""
        self.analysis._export_type = Constant.DB
        stat_df = pd.DataFrame({
            'module_parent': ['a'],
            'op_name': ['b'],
            'kernel_list': ['c'],
            'op_count': [1],
            'total_kernel_duration': [2],
            'avg_kernel_duration': [3],
            'avg_mfu': ['50.0%']
        })
        out = self.analysis._format_stat_df_columns(stat_df)
        self.assertIn('parentModule', out.columns)
        self.assertIn('opName', out.columns)

    def test_format_stat_df_columns_when_export_type_text_then_rename(self):
        """测试_format_stat_df_columns，export_type为text时应重命名列"""
        self.analysis._export_type = Constant.TEXT
        stat_df = pd.DataFrame({
            'module_parent': ['a'],
            'module': ['b'],
            'op_name': ['c'],
            'kernel_list': ['d'],
            'op_count': [1],
            'total_kernel_duration': [2],
            'avg_kernel_duration': [3],
            'avg_mfu': ['50.0%']
        })
        out = self.analysis._format_stat_df_columns(stat_df)
        self.assertIn('Parent Module', out.columns)
        self.assertIn('Module', out.columns)

    def test_build_node_tree_when_module_and_kernel_df_valid_then_tree_structure_correct(self):
        """测试_build_node_tree，输入有效module_df和kernel_df时应正确构建树结构"""
        module_df = pd.DataFrame([
            {"startNs": 0, "endNs": 100, "name": "mod1"},
            {"startNs": 10, "endNs": 90, "name": "mod2"}
        ])
        kernel_df = pd.DataFrame([
            {"kernel_name": "k1", "kernel_ts": 20, "kernel_end": 30, 'mfu': -1.0,
             "op_name": "op1", "op_ts": 15, "op_end": 40},
            {"kernel_name": "k2", "kernel_ts": 31, "kernel_end": 35, 'mfu': -1.0,
             "op_name": "op1", "op_ts": 15, "op_end": 40},
            {"kernel_name": "k3", "kernel_ts": 50, "kernel_end": 60, 'mfu': -1.0,
             "op_name": "op2", "op_ts": 45, "op_end": 70}
        ])
        root = self.analysis._build_complete_tree(module_df, kernel_df)
        # 根节点应有1个子module节点mod1
        self.assertTrue(hasattr(root, 'children'))
        root_child = [c.name for c in root.children]
        self.assertEqual(['mod1'], root_child)

        # mod1节点，子节点为mod2
        mod1_node = root.children[0]
        self.assertTrue(hasattr(mod1_node, 'children'))
        mod1_child = [c.name for c in mod1_node.children]
        self.assertEqual(['mod2'], mod1_child)

        # op节点为mod2的子节点
        mod2_node = mod1_node.children[0]
        op_names = [c.name for c in mod2_node.children if c.node_type == NodeType.CPU_OP_EVENT]
        self.assertEqual(['op1', 'op2'], op_names)
        # op节点的children为kernel
        op1_nodes = [c for c in mod2_node.children if c.node_type == NodeType.CPU_OP_EVENT and c.name == 'op1']
        self.assertEqual(len(op1_nodes), 1)
        op1_kernels = [child.name for child in op1_nodes[0].children]
        self.assertEqual(['k1', 'k2'], op1_kernels)

    def test_build_node_tree_when_no_nodes_then_return_none(self):
        """测试_build_node_tree，module_df和kernel_df都为空时应返回None"""
        module_df = pd.DataFrame(columns=["startNs", "endNs", "name"])
        kernel_df = pd.DataFrame(columns=["kernel_name", "kernel_ts", "kernel_end", "op_name", "op_ts", "op_end"])
        root = self.analysis._build_complete_tree(module_df, kernel_df)
        self.assertIsNone(root)

    def test_flatten_tree_to_dataframe_when_tree_has_data_then_return_df(self):
        """测试_flatten_tree_to_dataframe，树结构有数据时应返回DataFrame"""
        # 构造简单树：root->module->op->kernel
        root = ModuleNode(0, 100, "")
        mod_parent = ModuleNode(10, 90, "mod_parent")
        mod = ModuleNode(15, 50, "mod")
        op = TreeNode(20, 30, NodeType.CPU_OP_EVENT, "op")
        kernel = KernelNode(21, 29, "k", -1.0)
        op.add_child(kernel)
        mod.add_child(op)
        mod_parent.add_child(mod)
        root.add_child(mod_parent)
        df = self.analysis._flatten_tree_to_dataframe(root)
        self.assertFalse(df.empty)
        self.assertIn('module', df.columns)
        self.assertIn('op_name', df.columns)
        self.assertEqual(df.iloc[0]['kernel_list'], 'k')
        self.assertEqual(df.iloc[0]['device_time'], 8)
        self.assertEqual(df.iloc[0]['module_parent'], 'mod_parent')

    def test_flatten_tree_to_dataframe_when_tree_is_empty_then_return_empty_df(self):
        """测试_flatten_tree_to_dataframe，树无有效数据时应返回空DataFrame"""
        root = TreeNode(0, 100, NodeType.MODULE_EVENT_NODE, "root")
        df = self.analysis._flatten_tree_to_dataframe(root)
        self.assertTrue(df.empty)

    def test_aggregate_module_operator_stats_when_df_is_empty_then_return_empty(self):
        """测试_aggregate_module_operator_stats，df为空时应返回空DataFrame"""
        df = pd.DataFrame()
        out = self.analysis._aggregate_module_operator_stats(df)
        self.assertTrue(out.empty)

    def test_aggregate_module_operator_stats_when_df_valid_then_stat_df_shape_and_columns(self):
        """测试_aggregate_module_operator_stats，验证聚合和分组逻辑"""
        # 输入有4条数据能聚合成2个想同的seq
        df1 = pd.DataFrame({
            'module_parent': ['p', 'p', 'p', 'p'],
            'module': ['m', 'm', 'm', 'm'],
            'module_start': [0, 0, 20, 20],
            'module_end': [10, 10, 40, 40],
            'op_name': ['op1', 'op2', 'op1', 'op2'],
            'op_start': [1, 5, 25, 30],
            'op_end': [4, 8, 29, 33],
            'kernel_list': ['k1', 'k2', 'k1', 'k2'],
            'device_time': [2.0, 2.0, 3.0, 2.0],
            'mfu_list': [[0.5], [0.2], [0.5], [0.3]]
        })
        self.analysis._export_type = Constant.TEXT
        out1 = self.analysis._aggregate_module_operator_stats(df1)
        self.assertEqual(len(out1), 2)
        self.assertIn('Op Name', out1.columns)
        self.assertIn('Total Kernel Duration(ns)', out1.columns)
        self.assertIn('Avg Kernel Duration(ns)', out1.columns)

        op1_row = out1[out1['Op Name'] == 'op1'].iloc[0]
        op2_row = out1[out1['Op Name'] == 'op2'].iloc[0]
        self.assertEqual(op1_row['Total Kernel Duration(ns)'], 5.0)
        self.assertEqual(op1_row['Op Count'], 2)
        self.assertEqual(op1_row['Avg MFU'], '50.0%')
        self.assertEqual(op2_row['Total Kernel Duration(ns)'], 4.0)
        self.assertEqual(op2_row['Op Count'], 2)
        self.assertEqual(op2_row['Avg MFU'], '25.0%')

        # 输入有4条数据不能聚合
        df2 = pd.DataFrame({
            'module_parent': ['p', 'p', 'p', 'p'],
            'module': ['m', 'm', 'm', 'm'],
            'module_start': [0, 0, 20, 20],
            'module_end': [10, 10, 40, 40],
            'op_name': ['op1', 'op2', 'op1', 'op3'],
            'op_start': [1, 5, 25, 30],
            'op_end': [4, 8, 29, 33],
            'kernel_list': ['k1', 'k2', 'k1', 'k3'],
            'device_time': [2.0, 2.0, 3.0, 2.0],
            'mfu_list': [[0.5], [0.2], [0.5], [0.3]]
        })
        expected_stat_df = pd.DataFrame({
            'Parent Module': ['p', 'p', 'p', 'p'],
            'Module': ['m_0', 'm_0', 'm_1', 'm_1'],
            'Op Name': ['op1', 'op2', 'op1', 'op3'],
            'Kernel List': ['k1', 'k2', 'k1', 'k3'],
            'Total Kernel Duration(ns)': [2.0, 2.0, 3.0, 2.0],
            'Avg Kernel Duration(ns)': [2.0, 2.0, 3.0, 2.0],
            'Op Count': [1, 1, 1, 1],
            'Avg MFU': ['50.0%', '20.0%', '50.0%', '30.0%']
        })
        out2 = self.analysis._aggregate_module_operator_stats(df2)
        self.assertEqual(len(out2), 4)
        # 逐项对比out2和expected_stat_df内容
        self.assertEqual(list(out2.columns), list(expected_stat_df.columns))
        self.assertEqual(len(out2), len(expected_stat_df))
        for i in range(len(out2)):
            for col in out2.columns:
                self.assertEqual(out2.at[i, col], expected_stat_df.at[i, col],
                                 msg=f"Row {i}, column '{col}' not equal: "
                                     f"{out2.at[i, col]} != {expected_stat_df.at[i, col]}")

    @patch('msprof_analyze.cluster_analyse.recipes.module_statistic.module_statistic.ModuleMstxRangeExport')
    def test_query_all_data_success(self, mock_module_export):
        mock_module_instance = Mock()
        mock_module_instance.read_export_db.return_value = self.mock_module_data
        mock_module_export.return_value = mock_module_instance
        self.analysis._query_framework_op_to_kernel = Mock(return_value=self.mock_kernel_data)

        profiler_db_path = self.mock_data_map.get('profiler_db_path')
        rank_id = self.mock_data_map.get('rank_id')
        module_df, kernel_df = self.analysis._query_all_data(profiler_db_path, rank_id)

        self.assertIsNotNone(module_df)
        self.assertIsNotNone(kernel_df)
        self.assertEqual(len(module_df), 3)
        self.assertEqual(len(kernel_df), 3)

    @patch('msprof_analyze.cluster_analyse.recipes.module_statistic.module_statistic.ModuleMstxRangeExport')
    def test_query_all_data_when_no_module_when_empty_module(self, mock_module_export):
        mock_module_instance = Mock()
        mock_module_instance.read_export_db.return_value = pd.DataFrame()
        mock_module_export.return_value = mock_module_instance

        profiler_db_path = self.mock_data_map.get('profiler_db_path')
        rank_id = self.mock_data_map.get('rank_id')
        module_df, kernel_df = self.analysis._query_all_data(profiler_db_path, rank_id)

        self.assertIsNone(module_df)
        self.assertIsNone(kernel_df)

    @patch('msprof_analyze.cluster_analyse.recipes.module_statistic.module_statistic.DBManager.check_tables_in_db')
    @patch('msprof_analyze.cluster_analyse.recipes.module_statistic.module_statistic.FrameworkOpToKernelExport')
    def test_query_framework_op_to_kernel_when_table_exist_then_success(self, mock_framework_export, mock_check_tables):
        mock_check_tables.return_value = True

        mock_export_instance = Mock()
        mock_export_instance.read_export_db.return_value = self.mock_kernel_data
        mock_framework_export.return_value = mock_export_instance

        self.analysis.KERNEL_RELATED_TABLE_LIST = ['table1', 'table2', 'table3']
        profiler_db_path = self.mock_data_map.get('profiler_db_path')
        result = self.analysis._query_framework_op_to_kernel(profiler_db_path)

        self.assertIsNotNone(result)
        self.assertEqual(len(result), 9)
        self.assertEqual(mock_framework_export.call_count, 3)

    @patch('msprof_analyze.cluster_analyse.recipes.module_statistic.module_statistic.DBManager.check_tables_in_db')
    def test_query_framework_op_to_kernel_when_no_tables_then_return_none(self, mock_check_tables):
        mock_check_tables.return_value = False
        profiler_db_path = self.mock_data_map.get('profiler_db_path')
        result = self.analysis._query_framework_op_to_kernel(profiler_db_path)
        self.assertIsNone(result)

    @patch('msprof_analyze.cluster_analyse.recipes.module_statistic.module_statistic.MFUCalculator')
    @patch('msprof_analyze.cluster_analyse.recipes.module_statistic.module_statistic.BackwardModuleCreator')
    @patch('msprof_analyze.cluster_analyse.recipes.module_statistic.module_statistic.ModuleMstxRangeExport')
    def test_mapper_func_success(self, mock_module_export, mock_backward_creator_class, mock_mfu_calculator):
        mock_module_instance = Mock()
        mock_module_instance.read_export_db.return_value = self.mock_module_data
        mock_module_export.return_value = mock_module_instance

        mock_mfu_calculator.return_value.run.return_value = pd.DataFrame()

        self.analysis._query_framework_op_to_kernel = Mock(return_value=self.mock_kernel_data)

        mock_backward_creator = Mock()
        mock_backward_creator.run.return_value = pd.DataFrame()  # 空的反向传播数据
        mock_backward_creator_class.return_value = mock_backward_creator

        mock_root = Mock()
        self.analysis._build_complete_tree = Mock(return_value=mock_root)
        self.analysis._flatten_tree_to_dataframe = Mock(return_value=pd.DataFrame({
            'module_name': ['module1', 'module2'],
            'duration': [100, 200]
        }))
        self.analysis._aggregate_module_operator_stats = Mock(return_value=pd.DataFrame({
            'module_name': ['module1', 'module2'],
            'total_duration': [100, 200]
        }))

        analysis_class = Mock()
        rank_id, result_df = self.analysis._mapper_func(self.mock_data_map, analysis_class)

        self.assertEqual(rank_id, '0')
        self.assertIsNotNone(result_df)
        self.assertEqual(len(result_df), 2)
        self.analysis._build_complete_tree.assert_called_once()
        self.analysis._flatten_tree_to_dataframe.assert_called_once_with(mock_root)

    @patch('msprof_analyze.cluster_analyse.recipes.module_statistic.module_statistic.ModuleMstxRangeExport')
    def test_mapper_func_when_empty_module_data_when_return_empty_dataframe(self, mock_module_export):
        mock_module_instance = Mock()
        mock_module_instance.read_export_db.return_value = pd.DataFrame()
        mock_module_export.return_value = mock_module_instance

        analysis_class = Mock()
        rank_id, result_df = self.analysis._mapper_func(self.mock_data_map, analysis_class)

        self.assertEqual(rank_id, '0')
        self.assertTrue(result_df.empty)

    @patch('msprof_analyze.cluster_analyse.recipes.module_statistic.module_statistic.MFUCalculator')
    @patch('msprof_analyze.cluster_analyse.recipes.module_statistic.module_statistic.BackwardModuleCreator')
    @patch('msprof_analyze.cluster_analyse.recipes.module_statistic.module_statistic.ModuleMstxRangeExport')
    def test_mapper_func_with_backward_data(self, mock_module_export, mock_backward_creator_class, mock_mfu_calculator):
        # 准备mock
        mock_module_instance = Mock()
        mock_module_instance.read_export_db.return_value = self.mock_module_data
        mock_module_export.return_value = mock_module_instance

        mock_mfu_calculator.return_value.run.return_value = pd.DataFrame()

        self.analysis._query_framework_op_to_kernel = Mock(return_value=self.mock_kernel_data)

        backward_data = pd.DataFrame({
            'startNs': [4000, 5000],
            'endNs': [4500, 5500],
            'name': ['bwd_module1', 'bwd_module2']
        })

        mock_backward_creator = Mock()
        mock_backward_creator.run.return_value = backward_data
        mock_backward_creator_class.return_value = mock_backward_creator

        mock_root = Mock()
        self.analysis._build_complete_tree = Mock(return_value=mock_root)
        self.analysis._flatten_tree_to_dataframe = Mock(return_value=pd.DataFrame({
            'module_name': ['module1', 'module2', 'bwd_module1', 'bwd_module2'],
            'duration': [100, 200, 150, 250]
        }))
        self.analysis._aggregate_module_operator_stats = Mock(return_value=pd.DataFrame({
            'module_name': ['module1', 'module2', 'bwd_module1', 'bwd_module2'],
            'total_duration': [100, 200, 150, 250]
        }))

        analysis_class = Mock()
        rank_id, result_df = self.analysis._mapper_func(self.mock_data_map, analysis_class)

        mock_backward_creator.run.assert_called_once_with(self.mock_module_data)
        self.assertEqual(rank_id, '0')
        self.assertIsNotNone(result_df)
        self.assertEqual(len(result_df), 4)
