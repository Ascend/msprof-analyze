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
from unittest.mock import Mock

from msprof_analyze.compare_tools.compare_backend.compare_bean.origin_data_bean.trace_event_bean import \
    TraceEventBean
from msprof_analyze.compare_tools.compare_backend.compare_bean.origin_data_bean.compare_event import \
    MemoryEvent
from msprof_analyze.compare_tools.compare_backend.utils.torch_op_node import TorchOpNode
from msprof_analyze.prof_common.constant import Constant


class TestTorchOpNode(unittest.TestCase):
    def setUp(self):
        self.mock_event = Mock(spec=TraceEventBean)
        self.mock_event.start_time = 100
        self.mock_event.end_time = 200
        self.mock_event.name = "conv2d"
        self.mock_event.tid = 123
        self.mock_event.input_dims = [1, 3, 224, 224]
        self.mock_event.input_type = "float32"
        self.mock_event.call_stack = "frame1.py:10\nframe2.py:20"
        self.mock_event.dur = 50
        self.mock_event.is_step_profiler.return_value = True

        self.parent_node = TorchOpNode(event=Mock(name="parent_op"))
        self.child_node1 = TorchOpNode(event=Mock(name="child1", dur=10))
        self.child_node2 = TorchOpNode(event=Mock(name="child2", dur=20))

        self.op_node = TorchOpNode(event=self.mock_event, parent_node=self.parent_node)
        self.op_node._child_nodes = [self.child_node1, self.child_node2]

    def test_initialization(self):
        self.assertEqual(self.op_node.start_time, 100)
        self.assertEqual(self.op_node.end_time, 200)
        self.assertEqual(self.op_node.parent, self.parent_node)
        self.assertEqual(len(self.op_node.child_nodes), 2)

    def test_properties(self):
        self.assertEqual(self.op_node.name, "conv2d")
        self.assertEqual(self.op_node.tid, 123)
        self.assertEqual(self.op_node.input_shape, str([1, 3, 224, 224]))
        self.assertEqual(self.op_node.origin_input_shape, [1, 3, 224, 224])
        self.assertEqual(self.op_node.input_type, "float32")
        self.assertEqual(self.op_node.call_stack, "frame1.py:10\nframe2.py:20")

        self.assertEqual(self.op_node.api_dur, 50)
        self.assertEqual(self.op_node.api_self_time, 20)  # 50 - (10 + 20)

    def test_kernel_operations(self):
        mock_kernel1 = Mock(device_dur=30)
        mock_kernel2 = Mock(device_dur=40)

        self.op_node.set_kernel_list([mock_kernel1, mock_kernel2])
        self.assertEqual(len(self.op_node.kernel_list), 2)
        self.assertEqual(self.op_node.kernel_num, 2)
        self.assertEqual(self.op_node.device_dur, 70)

        self.assertEqual(self.parent_node.kernel_num, 0)

        mock_kernel3 = Mock(device_dur=50)
        self.op_node.update_kernel_list([mock_kernel3])
        self.assertEqual(len(self.op_node.kernel_list), 3)
        self.assertEqual(self.op_node.kernel_num, 2)
        self.assertEqual(self.parent_node.kernel_num, 0)

    def test_memory_operations(self):
        mock_mem_event = Mock(spec=MemoryEvent)
        self.op_node.set_memory_allocated(mock_mem_event)
        self.assertEqual(len(self.op_node.memory_allocated), 1)
        self.assertIn(mock_mem_event, self.op_node.memory_allocated)

    def test_step_profiler(self):
        self.assertTrue(self.op_node.is_step_profiler())

        step_event = TraceEventBean({"name": "ProfilerStep#5"})
        step_node = TorchOpNode(event=step_event)
        self.assertEqual(step_node.get_step_id(), 5)

        non_step_event = TraceEventBean({"name": "conv2d"})
        non_step_node = TorchOpNode(event=non_step_event)
        self.assertEqual(non_step_node.get_step_id(), Constant.VOID_STEP)

    def test_add_child_node(self):
        new_child = TorchOpNode(event=Mock(name="new_child", dur=5))
        self.op_node.add_child_node(new_child)
        self.assertEqual(len(self.op_node.child_nodes), 3)
        self.assertEqual(self.op_node.api_self_time, 15)  # 50 - (10 + 20 + 5)

    def test_get_op_info(self):
        expected_info = [
            "conv2d",
            str([1, 3, 224, 224]),
            "float32",
            "frame1.py:10\nframe2.py:20"
        ]
        self.assertEqual(self.op_node.get_op_info(), expected_info)

    def test_empty_initialization(self):
        empty_node = TorchOpNode(TraceEventBean({}))
        self.assertEqual(empty_node.start_time, 0)
        self.assertEqual(empty_node.kernel_num, 0)
        self.assertEqual(empty_node.api_self_time, 0)

    def test_edge_cases(self):
        root_node = TorchOpNode(event=Mock(dur=100))
        mock_kernel = Mock(device_dur=30)
        root_node.set_kernel_list([mock_kernel])
        self.assertEqual(root_node.kernel_num, 0)

        root_node.set_kernel_list([])
        self.assertEqual(root_node.kernel_num, 0)
