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

from collections import deque
from enum import Enum
import pandas as pd
from msprof_analyze.prof_common.logger import get_logger

logger = get_logger()


class NodeType(Enum):
    """树节点类型。"""

    MODULE_EVENT_NODE = 0
    CPU_OP_EVENT = 1
    KERNEL_EVENT = 2


class TreeNode:
    """通用事件树节点。"""

    def __init__(self, start, end, node_type, name):
        """初始化事件树节点。"""
        self.start = start
        self.end = end
        self.node_type = node_type
        self.name = name
        self.children = []

    @classmethod
    def create_from_df(cls, df, node_type, start_col, end_col, name_col):
        """根据 DataFrame 批量创建通用节点。"""
        if df is None or df.empty:
            return []
        return [
            cls(row[start_col], row[end_col], node_type, row[name_col])
            for _, row in df.iterrows()
        ]

    def add_child(self, node):
        """添加子节点。"""
        self.children.append(node)


class ModuleNode(TreeNode):
    """module 事件节点。"""

    MODULE_TYPE_COL_NAME = "module_type"
    BACKWARD = 'Backward'
    FORWARD = 'Forward'

    def __init__(self, start, end, name, module_type=None):
        """初始化 module 节点。"""
        super().__init__(start, end, NodeType.MODULE_EVENT_NODE, name)
        self.module_type = module_type if module_type is not None else self.FORWARD

    @property
    def is_backward(self):
        """判断当前 module 是否属于反向传播。"""
        return self.module_type == self.BACKWARD

    @classmethod
    def create_from_df(cls, df, start_col, end_col, name_col):
        """根据 DataFrame 批量创建 module 节点。"""
        if df is None or df.empty:
            return []
        nodes = []
        for _, row in df.iterrows():
            node = cls(row[start_col], row[end_col], row[name_col])
            if cls.MODULE_TYPE_COL_NAME in row and pd.notna(row[cls.MODULE_TYPE_COL_NAME]):
                node.module_type = row[cls.MODULE_TYPE_COL_NAME]
            nodes.append(node)
        return nodes


class KernelNode(TreeNode):
    """保存 MFU 的 kernel 事件节点。"""

    def __init__(self, start, end, name, mfu):
        """初始化 kernel 节点。"""
        super().__init__(start, end, NodeType.KERNEL_EVENT, name)
        self.mfu = mfu


class TreeBuilder:
    """构建并遍历 module、op 和 kernel 事件树。"""

    @staticmethod
    def create_tree_nodes_from_df(df, node_type, start_col, end_col, name_col):
        """根据节点类型从 DataFrame 创建树节点。"""
        if df is None or df.empty:
            return []
        if node_type == NodeType.MODULE_EVENT_NODE:
            return ModuleNode.create_from_df(df, start_col, end_col, name_col)
        else:
            return TreeNode.create_from_df(df, node_type, start_col, end_col, name_col)

    @staticmethod
    def build_tree_from_events(events, global_start=None, global_end=None):
        """根据事件时间范围构建层级树。"""
        if not events:
            logger.error("Empty events, skipping tree build")
            return None

        # 按开始时间升序、结束时间降序排序
        events.sort(key=lambda x: (x.start, -x.end))

        # 创建根节点
        if global_start is None or global_end is None:
            global_start = min(event.start for event in events)
            global_end = max(event.end for event in events)
        root = ModuleNode(global_start, global_end, "", "forward")

        # 构建树结构
        stack = [root]
        for event in events:
            # 对于CPU_OP_EVENT节点，只能添加到MODULE_EVENT_NODE类型的父节点下
            if event.node_type == NodeType.CPU_OP_EVENT:
                # 找到最近的MODULE_EVENT_NODE类型的父节点
                while (stack[-1].node_type != NodeType.MODULE_EVENT_NODE or
                       stack[-1].start > event.start or
                       stack[-1].end < event.end):
                    stack.pop()
            else:
                while stack[-1].start > event.start or stack[-1].end < event.end:
                    stack.pop()

            stack[-1].add_child(event)

            # 只有MODULE_EVENT_NODE节点才能入栈，CPU_OP_EVENT不入栈
            if event.node_type == NodeType.MODULE_EVENT_NODE:
                stack.append(event)

        return root

    @staticmethod
    def traverse_module_tree(root_node, callback, max_traverse_depth=20):
        """遍历 module 树，并对 module 的直属 op 执行回调。"""

        def _traverse(node, module_node_deque, depth=0):
            """递归遍历 module 节点。"""
            if depth > max_traverse_depth:
                logger.warning(f"Max traversal depth {max_traverse_depth} reached, traversal stopped. "
                               f"Some information may be lost")
                return
            if node.node_type != NodeType.MODULE_EVENT_NODE:
                return

            for child in node.children:
                if child.node_type == NodeType.MODULE_EVENT_NODE:
                    module_node_deque.append(node)  # 存储节点对象而不是名称
                    _traverse(child, module_node_deque, depth + 1)
                    module_node_deque.pop()
                else:
                    callback(node, child, module_node_deque.copy())

        _traverse(root_node, deque(), 0)
