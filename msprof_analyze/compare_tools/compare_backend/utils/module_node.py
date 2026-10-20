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
import re
from math import ceil

from msprof_analyze.compare_tools.compare_backend.compare_bean.origin_data_bean.trace_event_bean import TraceEventBean
from msprof_analyze.compare_tools.compare_backend.utils.torch_op_node import TorchOpNode


class ModuleNode:
    __slots__ = [
        '_event',
        '_parent_node',
        '_child_nodes',
        '_module_level',
        '_kernel_self_list',
        '_kernel_total_list',
        '_call_stack',
        '_root_torch_op_node',
        '_cur_torch_op_node',
    ]
    ts = "ts"
    kernels = "kernels"
    _call_stack_pool = {}

    def __init__(self, event: TraceEventBean, parent_node=None):
        self._event = event
        self._parent_node = parent_node
        self._child_nodes = []
        self._module_level = parent_node.module_level + 1 if parent_node else 1
        self._kernel_self_list = []
        self._kernel_total_list = []
        call_stack = (
            f"{parent_node.call_stack};\n{event.name}" if parent_node and parent_node.call_stack else event.name
        )
        self._call_stack = self._call_stack_pool.setdefault(call_stack, call_stack)
        self._root_torch_op_node = TorchOpNode()
        self._cur_torch_op_node = self._root_torch_op_node

    @property
    def module_name(self):
        return f"{self._parent_node.module_name}/{self._event.name}" if self._parent_node else self._event.name

    @property
    def module_class(self):
        pattern = re.compile('_[0-9]+$')
        return pattern.sub('', self.name.split("/")[-1])

    @property
    def module_level(self):
        return self._module_level

    @property
    def name(self):
        return self._event.name

    @property
    def parent_node(self):
        return self._parent_node

    @property
    def child_nodes(self):
        return self._child_nodes

    @property
    def dur(self):
        return self._event.dur

    @property
    def start_time(self):
        return self._event.start_time

    @property
    def end_time(self):
        return self._event.end_time

    @property
    def host_self_dur(self):
        return self.dur - sum(node.dur for node in self.child_nodes)

    @property
    def device_self_dur(self):
        dur = 0
        for kernel_dict in self._kernel_self_list:
            kernel_list = kernel_dict.get(self.kernels, [])
            dur += sum(kernel.device_dur for kernel in kernel_list)
        return dur

    @property
    def device_total_dur(self):
        dur = 0
        for kernel_dict in self._kernel_total_list:
            kernel_list = kernel_dict.get(self.kernels, [])
            dur += sum(kernel.device_dur for kernel in kernel_list)
        return dur

    @property
    def kernel_details(self):
        kernel_details = ""
        for kernel_dict in self._kernel_self_list:
            kernel_list = kernel_dict.get(self.kernels, [])
            for kernel in kernel_list:
                kernel_details += kernel.kernel_details
        return kernel_details

    @property
    def toy_layer_api_list(self):
        return self._root_torch_op_node.child_nodes

    @property
    def call_stack(self):
        return self._call_stack

    @staticmethod
    def _binary_search(ts_time, parent_node):
        if not parent_node.child_nodes:
            return None
        right = len(parent_node.child_nodes) - 1
        left = 0
        while right > left:
            mid = left + ceil((right - left) / 2)
            if ts_time >= parent_node.child_nodes[mid].start_time:
                left = mid
            else:
                right = mid - 1
        if parent_node.child_nodes[left].start_time < ts_time < parent_node.child_nodes[left].end_time:
            return parent_node.child_nodes[left]
        return None

    def reset_call_stack(self, call_stack):
        self._call_stack = self._call_stack_pool.setdefault(call_stack, call_stack)

    def update_child_nodes(self, node):
        self._child_nodes.append(node)

    def update_kernel_list(self, ts, kernel_list: list):
        self.update_kernel_self_list(ts, kernel_list)
        node = self
        while node.parent_node:
            node.update_kernel_total_list(ts, kernel_list)
            node = node.parent_node

    def find_module_call(self, ts_time):
        call_module = self._binary_search(ts_time, self)
        while call_module:
            module = self._binary_search(ts_time, call_module)
            if not module:
                return call_module
            call_module = module
        return call_module

    def find_torch_op_call(self, event):
        while self._cur_torch_op_node:
            if (
                self._cur_torch_op_node != self._root_torch_op_node
                and event.start_time > self._cur_torch_op_node.end_time
            ):
                self._cur_torch_op_node = self._cur_torch_op_node.parent
                continue
            tree_node = TorchOpNode(event, self._cur_torch_op_node)
            self._cur_torch_op_node.add_child_node(tree_node)
            self._cur_torch_op_node = tree_node
            break

    def update_torch_op_kernel_list(self):
        top_node_list = self._root_torch_op_node.child_nodes
        if not top_node_list:
            return
        top_node_list.sort(key=lambda x: x.start_time)
        cur_index = 0
        self._kernel_self_list.sort(key=lambda x: x.get(self.ts, 0))
        for kernel_dict in self._kernel_self_list:
            ts = kernel_dict.get(self.ts, 0)
            kernel_list = kernel_dict.get(self.kernels, [])
            while cur_index < len(top_node_list):
                if ts > top_node_list[cur_index].end_time:
                    cur_index += 1
                    continue
                if ts < top_node_list[cur_index].start_time:
                    break
                top_node_list[cur_index].update_kernel_list(kernel_list)
                break

    def update_kernel_self_list(self, ts, kernel_list: list):
        self._kernel_self_list.append({self.ts: ts, self.kernels: kernel_list})

    def update_kernel_total_list(self, ts, kernel_list: list):
        self._kernel_total_list.append({self.ts: ts, self.kernels: kernel_list})
