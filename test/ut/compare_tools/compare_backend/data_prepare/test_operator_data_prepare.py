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
from unittest.mock import MagicMock, patch

from msprof_analyze.compare_tools.compare_backend.data_prepare.operator_data_prepare import OperatorDataPrepare
from msprof_analyze.prof_common.constant import Constant

NAMESPACE = 'msprof_analyze.compare_tools.compare_backend.data_prepare'


class TestOperatorDataPrepare(unittest.TestCase):
    @staticmethod
    def profiling_result():
        profiling = MagicMock()
        profiling.torch_op_data = []
        profiling.kernel_dict = {}
        profiling.memory_list = []
        return profiling

    def test_get_top_layer_ops_void_step_should_expand_step_nodes(self):
        profiling = self.profiling_result()
        with patch(NAMESPACE + '.operator_data_prepare.TreeBuilder') as mock_tb:
            root = MagicMock()
            step_node = MagicMock()
            step_node.is_step_profiler.return_value = True
            child_a = MagicMock()
            child_b = MagicMock()
            step_node.child_nodes = [child_a, child_b]

            normal_node = MagicMock()
            normal_node.is_step_profiler.return_value = False

            root.child_nodes = [step_node, normal_node]
            mock_tb.build_tree.return_value = [root, step_node, normal_node]

            odp = OperatorDataPrepare(profiling, specified_step_id=Constant.VOID_STEP)
            result = odp.get_top_layer_ops()
            self.assertEqual(result, [child_a, child_b, normal_node])

    def test_get_all_layer_ops_void_step_should_filter_out_step_nodes(self):
        profiling = self.profiling_result()
        with patch(NAMESPACE + '.operator_data_prepare.TreeBuilder') as mock_tb:
            root = MagicMock()
            a = MagicMock()
            a.is_step_profiler.return_value = False
            b = MagicMock()
            b.is_step_profiler.return_value = True
            c = MagicMock()
            c.is_step_profiler.return_value = False

            mock_tb.build_tree.return_value = [root, a, b, c]

            odp = OperatorDataPrepare(profiling, specified_step_id=Constant.VOID_STEP)
            result = odp.get_all_layer_ops()
            self.assertEqual(result, [a, c])

    def test_get_all_layer_ops_specific_step_should_bfs_children(self):
        profiling = self.profiling_result()
        step_id = 3
        with patch(NAMESPACE + '.operator_data_prepare.TreeBuilder') as mock_tb:
            root = MagicMock()
            step_node = MagicMock()
            step_node.is_step_profiler.return_value = True
            step_node.get_step_id.return_value = step_id

            c1 = MagicMock()
            c1.child_nodes = []
            c2 = MagicMock()
            c2.child_nodes = []

            step_node.child_nodes = [c1, c2]

            other = MagicMock()
            other.is_step_profiler.return_value = False

            root.child_nodes = [other, step_node]
            mock_tb.build_tree.return_value = [root, step_node, other]

            odp = OperatorDataPrepare(profiling, specified_step_id=step_id)
            result = odp.get_all_layer_ops()
            self.assertEqual(result, [c1, c2])

    def test_get_all_layer_ops_specific_step_should_warn_and_raise_when_no_data(self):
        profiling = self.profiling_result()
        step_id = 7
        with patch(NAMESPACE + '.operator_data_prepare.TreeBuilder') as mock_tb, \
             patch(NAMESPACE + '.operator_data_prepare.logger') as mock_logger:
            root = MagicMock()
            root.child_nodes = []

            mock_tb.build_tree.return_value = [root]

            odp = OperatorDataPrepare(profiling, specified_step_id=step_id)
            with self.assertRaises(RuntimeError) as ctx:
                _ = odp.get_all_layer_ops()
            self.assertIn(str(step_id), str(ctx.exception))
            mock_logger.warning.assert_called_once()


if __name__ == '__main__':
    unittest.main()
