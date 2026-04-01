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
from unittest.mock import patch, Mock
import pandas as pd

from msprof_analyze.cluster_analyse.recipes.module_statistic.backward_module_create import BackwardModuleCreator
from msprof_analyze.cluster_analyse.recipes.module_statistic.tree_build import NodeType, TreeNode, ModuleNode


class TestBackwardModuleCreator(unittest.TestCase):
    def setUp(self):
        self.creator = BackwardModuleCreator(profiler_db_path="/tmp/mock.db")

    def test_run_when_module_dataframe_empty_then_return_empty_dataframe(self):
        module_df = pd.DataFrame(columns=["startNs", "endNs", "name"])
        result = self.creator.run(module_df)
        self.assertTrue(result.empty)

    def test_run_when_no_forward_backward_connections_then_return_empty_dataframe(self):
        module_df = pd.DataFrame([
            {"startNs": 0, "endNs": 10, "name": "module_a"}
        ])
        with patch.object(BackwardModuleCreator, "_query_fwd_bwd_connections", return_value=pd.DataFrame()):
            result = self.creator.run(module_df)
        self.assertTrue(result.empty)

    def test_collect_fwd_module_mappings_when_forward_nodes_exist_then_return_mappings(self):
        root = ModuleNode(0, 100, "")
        parent_module = ModuleNode(5, 95, "parent")
        child_module = ModuleNode(10, 90, "child")
        fwd_node = TreeNode(15, 20, NodeType.CPU_OP_EVENT, "fwd_op")
        child_module.add_child(fwd_node)
        parent_module.add_child(child_module)
        root.add_child(parent_module)

        mappings = self.creator._collect_fwd_module_mappings(root)

        self.assertEqual(len(mappings), 1)
        mapping = mappings[0]
        self.assertEqual(mapping["module_parent"], "parent")
        self.assertEqual(mapping["module"], "child")
        self.assertEqual(mapping["fwd_name"], "fwd_op")
        self.assertEqual(mapping["fwd_ts"], 15)
        self.assertEqual(mapping["module_start"], 10)

    def test_generate_bwd_module_events_when_forward_backward_rows_present_then_create_backward_modules(self):
        fwd_module_mappings = [
            {
                "module_parent": "parent",
                "module": "child",
                "module_start": 10,
                "module_end": 50,
                "fwd_name": "fwd_op_a",
                "fwd_ts": 5,
                "fwd_end": 8,
            },
            {
                "module_parent": "parent",
                "module": "child",
                "module_start": 10,
                "module_end": 50,
                "fwd_name": "fwd_op_b",
                "fwd_ts": 9,
                "fwd_end": 12,
            },
        ]
        fwd_bwd_df = pd.DataFrame([
            {"fwd_name": "fwd_op_a", "fwd_ts": 5, "fwd_end": 8, "bwd_ts": 100, "bwd_end": 120},
            {"fwd_name": "fwd_op_b", "fwd_ts": 9, "fwd_end": 12, "bwd_ts": 130, "bwd_end": 140},
        ])

        new_modules = self.creator._generate_bwd_module_events(fwd_module_mappings, fwd_bwd_df)

        self.assertEqual(set(new_modules["name"]), {"parent", "child"})
        self.assertTrue((new_modules[ModuleNode.MODULE_TYPE_COL_NAME] == ModuleNode.BACKWARD).all())
        child_row = new_modules[new_modules["name"] == "child"].iloc[0]
        parent_row = new_modules[new_modules["name"] == "parent"].iloc[0]
        self.assertEqual(child_row["startNs"], 100)
        self.assertEqual(child_row["endNs"], 140)
        self.assertEqual(parent_row["startNs"], 99)  # min bwd_ts - 1
        self.assertEqual(parent_row["endNs"], 141)   # max bwd_end + 1

    def test_generate_bwd_module_events_when_forward_backward_merge_empty_then_return_empty_dataframe(self):
        fwd_module_mappings = [
            {
                "module_parent": "parent",
                "module": "child",
                "module_start": 10,
                "module_end": 50,
                "fwd_name": "fwd_op_a",
                "fwd_ts": 5,
                "fwd_end": 8,
            },
        ]
        fwd_bwd_df = pd.DataFrame([
            {"fwd_name": "another_op", "fwd_ts": 1, "fwd_end": 2, "bwd_ts": 10, "bwd_end": 20}
        ])

        new_modules = self.creator._generate_bwd_module_events(fwd_module_mappings, fwd_bwd_df)

        self.assertTrue(new_modules.empty)

    def test_create_backward_module_events_time_range_calculation(self):
        module_df = pd.DataFrame({
            'startNs': [100, 500],
            'endNs': [200, 600],
            'name': ['module1', 'module2']
        })

        fwd_bwd_df = pd.DataFrame({
            'fwd_ts': [150, 550],
            'fwd_end': [180, 580],
            'fwd_name': ['fwd1', 'fwd2'],
            'bwd_ts': [300, 700],
            'bwd_end': [400, 800]
        })

        result = self.creator.create_backward_module_events(module_df, fwd_bwd_df)

        expected = [
            {'endNs': 400, 'module_type': 'Backward', 'name': 'module1', 'startNs': 300},
            {'endNs': 800, 'module_type': 'Backward', 'name': 'module2', 'startNs': 700}
        ]

        self.assertEqual(result.to_dict('records'), expected)


