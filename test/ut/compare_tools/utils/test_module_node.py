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
from unittest.mock import Mock, patch

from msprof_analyze.compare_tools.compare_backend.compare_bean.origin_data_bean.trace_event_bean import \
    TraceEventBean
from msprof_analyze.compare_tools.compare_backend.utils.module_node import ModuleNode


class TestModuleNode(unittest.TestCase):
    def setUp(self):
        self.mock_parent_event = Mock(spec=TraceEventBean)
        self.mock_parent_event.name = "parent_module"
        self.mock_parent_event.dur = 100
        self.mock_parent_event.start_time = 0
        self.mock_parent_event.end_time = 100
        self.mock_parent_event.call_stack = "init"

        self.mock_event = Mock(spec=TraceEventBean)
        self.mock_event.name = "child_module"
        self.mock_event.dur = 50
        self.mock_event.start_time = 10
        self.mock_event.end_time = 60
        self.mock_event.call_stack = "forward"

        self.parent_node = ModuleNode(event=self.mock_parent_event)
        self.child_node = ModuleNode(event=self.mock_event, parent_node=self.parent_node)

        self.mock_kernel1 = Mock(device_dur=10)
        self.mock_kernel2 = Mock(device_dur=20)
        self.kernel_list = [self.mock_kernel1, self.mock_kernel2]

        self.mock_op_event = Mock(spec=TraceEventBean)
        self.mock_op_event.name = "conv2d"
        self.mock_op_event.start_time = 15
        self.mock_op_event.end_time = 25

    def test_initialization(self):
        self.assertEqual(self.child_node.module_level, 2)
        self.assertEqual(self.child_node.name, "child_module")
        self.assertEqual(self.child_node.parent_node, self.parent_node)
        self.assertEqual(self.child_node.dur, 50)
        self.assertEqual(self.child_node.call_stack, "parent_module;\nchild_module")

    def test_module_name_property(self):
        self.assertEqual(self.parent_node.module_name, "parent_module")
        self.assertEqual(self.child_node.module_name, "parent_module/child_module")

    def test_module_class_property(self):
        with patch.object(self.mock_event, 'name', "Linear_42"):
            node = ModuleNode(event=self.mock_event)
            self.assertEqual(node.module_class, "Linear")

    def test_duration_properties(self):
        self.assertEqual(self.child_node.host_self_dur, 50)

        _grandchild = ModuleNode(event=Mock(dur=20), parent_node=self.child_node)
        self.assertEqual(self.child_node.host_self_dur, 50)

    def test_kernel_operations(self):
        ts = 15
        self.child_node.update_kernel_list(ts, self.kernel_list)

        self.assertEqual(len(self.child_node._kernel_self_list), 1)
        self.assertEqual(self.child_node.device_self_dur, 30)

        self.assertEqual(len(self.parent_node._kernel_total_list), 0)
        self.assertEqual(self.parent_node.device_total_dur, 0)

    def test_binary_search(self):
        nodes = [
            Mock(start_time=10, end_time=20),
            Mock(start_time=25, end_time=35),
            Mock(start_time=40, end_time=50)
        ]
        self.child_node._child_nodes = nodes

        found = ModuleNode._binary_search(15, self.child_node)
        self.assertEqual(found, nodes[0])

        not_found = ModuleNode._binary_search(22, self.child_node)
        self.assertIsNone(not_found)

    def test_torch_op_operations(self):
        self.child_node.find_torch_op_call(self.mock_op_event)

        self.assertNotEqual(self.child_node._cur_torch_op_node, self.child_node._root_torch_op_node)
        self.assertEqual(len(self.child_node.toy_layer_api_list), 1)

        ts = 20
        self.child_node.update_kernel_self_list(ts, self.kernel_list)
        self.child_node.update_torch_op_kernel_list()

        op_node = self.child_node.toy_layer_api_list[0]
        self.assertEqual(len(op_node.kernel_list), 2)

    def test_edge_cases(self):
        empty_node = ModuleNode(event=Mock())
        self.assertEqual(empty_node.module_level, 1)
        self.assertEqual(empty_node.call_stack, empty_node.name)

    def test_call_stack_management(self):
        new_stack = "new_stack"
        self.child_node.reset_call_stack(new_stack)
        self.assertEqual(self.child_node.call_stack, new_stack)

        another_node = ModuleNode(event=Mock())
        another_node.reset_call_stack(new_stack)
        self.assertIs(self.child_node._call_stack, another_node._call_stack)

    def test_kernel_detail_generation(self):
        self.mock_kernel1.kernel_details = "kernel1_details"
        self.mock_kernel2.kernel_details = "kernel2_details"

        self.child_node.update_kernel_self_list(10, self.kernel_list)
        details = self.child_node.kernel_details
        self.assertIn("kernel1_details", details)
        self.assertIn("kernel2_details", details)
