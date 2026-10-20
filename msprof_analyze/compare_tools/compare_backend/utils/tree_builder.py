# -------------------------------------------------------------------------
# This file is part of the MindStudio project.
# Copyright (c) 2024 Huawei Technologies Co.,Ltd.
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

from queue import Queue

from msprof_analyze.compare_tools.compare_backend.compare_bean.origin_data_bean.trace_event_bean import TraceEventBean
from msprof_analyze.compare_tools.compare_backend.utils.module_node import ModuleNode
from msprof_analyze.compare_tools.compare_backend.utils.torch_op_node import TorchOpNode
from msprof_analyze.compare_tools.compare_backend.compare_bean.origin_data_bean.db_data_bean.framework_api_bean import (
    FrameworkApiBean,
)


class TreeBuilder:
    @classmethod
    def build_tree(cls, event_list: list, kernel_dict: dict, memory_list: list) -> TorchOpNode:
        root_node = TorchOpNode()
        all_nodes = [root_node] + ([None] * len(event_list))
        all_event_list = []
        all_event_list.extend(event_list)
        all_event_list.extend(memory_list)
        all_event_list.sort(key=lambda x: x.start_time)
        last_node = root_node
        index = 1
        for event in all_event_list:
            while last_node:
                if last_node != root_node and event.start_time > last_node.end_time:
                    last_node = last_node.parent
                    continue
                if event.is_torch_op:
                    tree_node = TorchOpNode(event, last_node)
                    all_nodes[index] = tree_node
                    index += 1
                    last_node.add_child_node(tree_node)
                    last_node = tree_node
                    if kernel_dict:
                        if isinstance(event, FrameworkApiBean):
                            tree_node.set_kernel_list(kernel_dict.get(event.cann_connection_id, []))
                        else:
                            tree_node.set_kernel_list(kernel_dict.get(event.start_time, []))
                else:
                    event.set_name(last_node.name)
                    last_node.set_memory_allocated(event)
                break
        return all_nodes[:index]

    @classmethod
    def get_total_kernels(cls, root_node: TorchOpNode) -> list:
        result_list = []
        result_list.extend(root_node.kernel_list)
        node_queue = Queue()
        for child_node in root_node.child_nodes:
            node_queue.put(child_node)
        while not node_queue.empty():
            tree_node = node_queue.get()
            result_list.extend(tree_node.kernel_list)
            for child_node in tree_node.child_nodes:
                node_queue.put(child_node)
        return result_list

    @classmethod
    def get_total_memory(cls, root_node: TorchOpNode) -> list:
        result_list = []
        result_list.extend(root_node.memory_allocated)
        node_queue = Queue()
        for child_node in root_node.child_nodes:
            node_queue.put(child_node)
        while not node_queue.empty():
            tree_node = node_queue.get()
            result_list.extend(tree_node.memory_allocated)
            for child_node in tree_node.child_nodes:
                node_queue.put(child_node)
        return result_list

    @classmethod
    def build_module_tree(cls, event_list: list, kernel_dict: dict):
        root_node = ModuleNode(TraceEventBean({}))
        event_list.sort(key=lambda x: x.start_time)
        last_node = root_node
        for event in event_list:
            while last_node:
                if last_node != root_node and event.start_time > last_node.end_time:
                    last_node = last_node.parent_node
                    continue
                if event.is_x_mode():
                    tree_node = ModuleNode(event, last_node)
                    last_node.update_child_nodes(tree_node)
                    last_node = tree_node
                    break
                if last_node == root_node:
                    break
                kernel_list = kernel_dict.get(event.start_time, [])
                if kernel_list:
                    last_node.update_kernel_list(event.start_time, kernel_list)
                break
        return root_node
