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

from msprof_analyze.compare_tools.compare_backend.compare_bean.origin_data_bean.trace_event_bean import TraceEventBean
from msprof_analyze.compare_tools.compare_backend.data_prepare.module_data_prepare import ModuleDataPrepare
from msprof_analyze.compare_tools.compare_backend.utils.module_node import ModuleNode

NAMESPACE = 'msprof_analyze.compare_tools.compare_backend.data_prepare'


class TestModuleDataPrepare(unittest.TestCase):
    @staticmethod
    def profiling_result():
        fwdbwd_start_data = {"pid": 1, "tid": 1, "ts": 1, "dur": 0, "ph": "X", "cat": "fwdbwd",
                             "name": "fwdbwd", "args": {}}
        fwdbwd_end_data = {"pid": 1, "tid": 1, "ts": 1, "dur": 0, "ph": "X", "cat": "fwdbwd",
                           "name": "fwdbwd", "args": {}}
        python_func_data = {"pid": 1, "tid": 1, "ts": 1, "dur": 0, "ph": "X", "cat": "python_function",
                            "name": "torch", "args": {'Python id': 11, 'Python parent id': 10}}
        nn_python_func_data = {"pid": 1, "tid": 1, "ts": 1, "dur": 0, "ph": "X", "cat": "nn_python_function",
                               "name": "nn.module:test114514", "args": {'Python id': 11, 'Python parent id': 10}}
        torch_op_data = {"pid": 1, "tid": 1, "ts": 1, "dur": 2, "ph": "X", "cat": "python_function",
                            "name": "torch", "args": {'Call stack': '/torch/_ops.py: __call__;',
                                                      'Fwd thread id': 0, 'Sequence number': -1}}
        profiling_result = MagicMock()
        profiling_result._profiling_type = "NPU"
        profiling_result.python_function_data = [TraceEventBean(python_func_data),
                                                 TraceEventBean(nn_python_func_data)]
        profiling_result.torch_op_data = [TraceEventBean(torch_op_data)]
        profiling_result.kernel_dict = {}
        profiling_result.fwdbwd_dict = {
            1: {'start': TraceEventBean(fwdbwd_start_data),
                'end': TraceEventBean(fwdbwd_end_data)}
        }
        return profiling_result

    def test_build_module_tree_should_return_none_nodes_when_no_nn_modules(self):
        profiling = self.profiling_result()
        profiling.python_function_data = []

        mdp = ModuleDataPrepare(profiling)
        with patch(NAMESPACE + '.module_data_prepare.TreeBuilder') as mock_tb:
            nodes = mdp.build_module_tree()
            self.assertEqual(nodes, [None, None])
            mock_tb.build_module_tree.assert_not_called()

    def test_build_module_tree_should_return_correct_node_when_data_exist(self):
        # Prepare a small tree: root -> child
        res_root_node = ModuleDataPrepare(self.profiling_result()).build_module_tree()
        self.assertEqual(len(res_root_node), 2)
        self.assertIsInstance(res_root_node[0], ModuleNode)
        self.assertIsInstance(res_root_node[1], ModuleNode)

    def test_match_torch_op_should_match_forward_then_backward_and_ignore_optimizer_and_step(self):
        profiling = self.profiling_result()
        # three torch ops: optimizer, step_profiler, normal
        opt = MagicMock()
        opt.is_optimizer.return_value = True
        opt.is_step_profiler.return_value = False
        opt.start_time = 10

        step = MagicMock()
        step.is_optimizer.return_value = False
        step.is_step_profiler.return_value = True
        step.start_time = 20

        normal = MagicMock()
        normal.is_optimizer.return_value = False
        normal.is_step_profiler.return_value = False
        normal.start_time = 30

        profiling.torch_op_data = [normal, opt, step]
        # Sorted by start_time inside the function, order shouldn't matter

        mdp = ModuleDataPrepare(profiling)
        fwd_root = MagicMock()
        bwd_root = MagicMock()
        # forward root doesn't match, backward root does
        fwd_root.find_module_call.return_value = None
        matched_module = MagicMock()
        bwd_root.find_module_call.return_value = matched_module

        mdp.match_torch_op(fwd_root, bwd_root)

        matched_module.find_torch_op_call.assert_called_once_with(normal)
        fwd_root.find_module_call.assert_called()
        bwd_root.find_module_call.assert_called()


if __name__ == '__main__':
    unittest.main()
