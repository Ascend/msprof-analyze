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
from enum import Enum
from collections import deque

from msprof_analyze.cluster_analyse.common_func.base_tree_builder import BaseTreeBuilder
from msprof_analyze.cluster_analyse.common_func.base_tree_builder import BaseTreeNode


class MstxSumRecipeNodeType(Enum):
    DEFAULT_NODE = 0


class MstxSumRecipeTreeNode(BaseTreeNode):
    def __init__(self, start, end, name, node_type=None):
        super().__init__(start, end, name, node_type)

    @classmethod
    def create_from_df(cls, df, start_col, end_col, name_col, node_type):
        if df is None or df.empty:
            return []
        nodes = []
        for _, row in df.iterrows():
            node = MstxSumRecipeTreeNode(
                row[start_col],
                row[end_col],
                row[name_col],
                node_type
            )
            nodes.append(node)
        return nodes


class MstxSumRecipeTreeBuilder(BaseTreeBuilder):
    def __init__(self, df):
        super().__init__()
        self.df = df
        self.root = None

    def build_tree(self, start_col, end_col, name_col, node_type):
        self.root = self.create_root_node(start_col, end_col, node_type)
        nodes = MstxSumRecipeTreeNode.create_from_df(self.df, start_col, end_col, name_col, node_type)
        self.build_node_tree(nodes)
        self.update_msg(self.root, "")
        self.flatten_tree(node=self.root, start_col=start_col, end_col=end_col, name_col=name_col)

    def create_root_node(self, start_col, end_col, node_type):
        global_start = self.df[start_col].min()
        global_end = self.df[end_col].max()
        root = MstxSumRecipeTreeNode(global_start, global_end, "", node_type)
        return root

    def build_node_tree(self, nodes):
        nodes.sort(key=lambda x: (x.start, -x.end))
        stack = deque([self.root])
        for node in nodes:
            while stack[-1].start > node.start or stack[-1].end < node.end:
                stack.pop()
            stack[-1].add_child(node)
            stack.append(node)

    def update_msg(self, node, path="", max_depth=100, depth=0):
        if max_depth is not None and depth >= max_depth:
            return
        if node.name and path:
            node.name = path + "::" + node.name
        for child in node.children:
            self.update_msg(child, node.name, max_depth, depth + 1)

    def flatten_tree(self, node, **kwargs):
        start_col = kwargs.get("start_col")
        end_col = kwargs.get("end_col")
        name_col = kwargs.get("name_col")
        max_depth = kwargs.get("max_depth", 100)
        depth = kwargs.get("depth", 0)
        if max_depth is not None and depth >= max_depth:
            return
        if node.name:
            self.df.loc[
                (self.df[start_col] == node.start) & (self.df[end_col] == node.end), name_col] = node.name
        for child in node.children:
            kwargs.update(depth=depth + 1)
            self.flatten_tree(child, **kwargs)