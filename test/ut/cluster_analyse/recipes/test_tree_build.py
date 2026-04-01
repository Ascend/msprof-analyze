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
from collections import deque
import pandas as pd

from msprof_analyze.cluster_analyse.recipes.module_statistic.tree_build import (
    TreeBuilder,
    ModuleNode,
    TreeNode,
    NodeType
)


class TestTreeBuilder(unittest.TestCase):
    def test_create_tree_nodes_from_df_when_df_is_none_then_return_empty_list(self):
        nodes = TreeBuilder.create_tree_nodes_from_df(
            df=None,
            node_type=NodeType.MODULE_EVENT_NODE,
            start_col="startNs",
            end_col="endNs",
            name_col="name",
        )

        self.assertEqual(nodes, [])

    def test_create_tree_nodes_from_df_when_df_is_empty_then_return_empty_list(self):
        empty_df = pd.DataFrame(columns=["startNs", "endNs", "name"])

        nodes = TreeBuilder.create_tree_nodes_from_df(
            df=empty_df,
            node_type=NodeType.MODULE_EVENT_NODE,
            start_col="startNs",
            end_col="endNs",
            name_col="name",
        )

        self.assertEqual(nodes, [])

    def test_create_tree_nodes_from_df_when_node_type_is_module_then_create_module_nodes(self):
        df = pd.DataFrame(
            [
                {"startNs": 0, "endNs": 10, "name": "module_a"},
                {"startNs": 20, "endNs": 30, "name": "module_b", ModuleNode.MODULE_TYPE_COL_NAME: ModuleNode.BACKWARD},
            ]
        )

        nodes = TreeBuilder.create_tree_nodes_from_df(
            df=df,
            node_type=NodeType.MODULE_EVENT_NODE,
            start_col="startNs",
            end_col="endNs",
            name_col="name",
        )

        self.assertEqual(len(nodes), 2)
        self.assertIsInstance(nodes[0], ModuleNode)
        self.assertEqual(nodes[0].start, 0)
        self.assertEqual(nodes[0].end, 10)
        self.assertEqual(nodes[0].name, "module_a")
        self.assertEqual(nodes[0].module_type, ModuleNode.FORWARD)  # 默认类型为 Forward

        self.assertIsInstance(nodes[1], ModuleNode)
        self.assertEqual(nodes[1].name, "module_b")
        self.assertEqual(nodes[1].module_type, ModuleNode.BACKWARD)

    def test_create_tree_nodes_from_df_when_node_type_is_not_module_then_create_basic_tree_nodes(self):
        df = pd.DataFrame(
            [
                {"startNs": 5, "endNs": 15, "name": "cpu_op_a"},
                {"startNs": 16, "endNs": 18, "name": "cpu_op_b"},
            ]
        )

        nodes = TreeBuilder.create_tree_nodes_from_df(
            df=df,
            node_type=NodeType.CPU_OP_EVENT,
            start_col="startNs",
            end_col="endNs",
            name_col="name",
        )

        self.assertEqual(len(nodes), 2)
        self.assertIsInstance(nodes[0], TreeNode)
        self.assertEqual(nodes[0].node_type, NodeType.CPU_OP_EVENT)
        self.assertEqual(nodes[0].name, "cpu_op_a")

    def test_build_tree_from_events_when_events_is_empty_then_return_none(self):
        root = TreeBuilder.build_tree_from_events([])
        self.assertIsNone(root)

    def test_build_tree_from_events_when_events_have_modules_and_cpu_ops_then_build_correct_hierarchy(self):
        """
        root(0, 50)
             module_a(0, 50)
                module_b(5, 30)
                    cpu_op_1(10, 12)
                    cpu_op_2(20, 25)
        """
        module_a = ModuleNode(0, 50, "module_a")
        module_b = ModuleNode(5, 30, "module_b")
        cpu_op_1 = TreeNode(10, 12, NodeType.CPU_OP_EVENT, "cpu_op_1")
        cpu_op_2 = TreeNode(20, 25, NodeType.CPU_OP_EVENT, "cpu_op_2")

        events = [module_a, module_b, cpu_op_1, cpu_op_2]

        root = TreeBuilder.build_tree_from_events(events)

        self.assertIsNotNone(root)

        self.assertEqual(len(root.children), 1)
        self.assertIs(root.children[0], module_a)  # 第一级子节点为 module_a
        self.assertIn(module_b, module_a.children)  # module_a 的子节点包含 module_b
        self.assertEqual({c.name for c in module_b.children}, {"cpu_op_1", "cpu_op_2"})  # module_b 的子节点包含两个 CPU 节点

        # CPU_OP_EVENT 不入栈，无子节点
        for cpu_node in module_b.children:
            self.assertEqual(cpu_node.children, [])

    def test_build_tree_from_events_when_cpu_op_out_of_any_module_then_attach_to_root_module(self):
        # cpu_op 时间覆盖整个区间但没有模块包裹，直接挂在 root 下
        cpu_op = TreeNode(0, 100, NodeType.CPU_OP_EVENT, "global_cpu_op")
        root = TreeBuilder.build_tree_from_events([cpu_op], global_start=0, global_end=100)

        self.assertIsNotNone(root)
        self.assertEqual(len(root.children), 1)
        self.assertIs(root.children[0], cpu_op)

    def test_traverse_module_tree_when_tree_contains_module_and_cpu_nodes_then_callback_invoked_correctly(self):
        """
        root
         └─ parent (module)
             └─ child (module)
                  ├─ cpu_op_1 (cpu)
                  └─ cpu_op_2 (cpu)
        """
        root = ModuleNode(0, 50, "")
        parent = ModuleNode(0, 50, "parent")
        child = ModuleNode(10, 30, "child")
        cpu_op_1 = TreeNode(12, 15, NodeType.CPU_OP_EVENT, "cpu_op_1")
        cpu_op_2 = TreeNode(20, 22, NodeType.CPU_OP_EVENT, "cpu_op_2")

        child.add_child(cpu_op_1)
        child.add_child(cpu_op_2)
        parent.add_child(child)
        root.add_child(parent)
        records = []

        def callback(module_node, leaf_node, module_node_deque: deque):
            records.append(
                {
                    "module": module_node.name,
                    "leaf": leaf_node.name,
                    "path": [n.name for n in module_node_deque],
                }
            )

        TreeBuilder.traverse_module_tree(root, callback)

        self.assertEqual(len(records), 2)
        self.assertTrue(all(item["module"] == "child" for item in records))
        self.assertTrue(all(item["path"] == ["", "parent"] for item in records))
        self.assertEqual({item["leaf"] for item in records}, {"cpu_op_1", "cpu_op_2"})


