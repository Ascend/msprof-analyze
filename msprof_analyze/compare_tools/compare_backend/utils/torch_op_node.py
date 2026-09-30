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
from msprof_analyze.compare_tools.compare_backend.compare_bean.origin_data_bean.compare_event import MemoryEvent
from msprof_analyze.compare_tools.compare_backend.compare_bean.origin_data_bean.trace_event_bean import TraceEventBean
from msprof_analyze.prof_common.constant import Constant


class TorchOpNode:
    __slots__ = ['_event', '_parent_node', '_child_nodes', '_kernel_list', '_kernel_num', '_memory_allocated_list']

    def __init__(self, event=TraceEventBean, parent_node=None):
        self._event = event
        self._parent_node = parent_node
        self._child_nodes = []
        self._kernel_list = []
        self._kernel_num = 0
        self._memory_allocated_list = []

    @property
    def start_time(self):
        return self._event.start_time

    @property
    def end_time(self):
        return self._event.end_time

    @property
    def name(self):
        return self._event.name

    @property
    def tid(self):
        return self._event.tid

    @property
    def input_shape(self):
        return str(self._event.input_dims)

    @property
    def origin_input_shape(self):
        return self._event.input_dims

    @property
    def input_type(self):
        return str(self._event.input_type)

    @property
    def call_stack(self):
        return str(self._event.call_stack)

    @property
    def parent(self):
        return self._parent_node

    @property
    def child_nodes(self):
        return self._child_nodes

    @property
    def kernel_list(self):
        return self._kernel_list

    @property
    def kernel_num(self):
        return self._kernel_num

    @property
    def memory_allocated(self):
        return self._memory_allocated_list

    @property
    def device_dur(self):
        return sum(kernel.device_dur for kernel in self._kernel_list)

    @property
    def api_dur(self):
        return self._event.dur

    @property
    def api_self_time(self):
        return self.api_dur - sum(child.api_dur for child in self._child_nodes)

    def add_child_node(self, child_node):
        self._child_nodes.append(child_node)

    def set_kernel_list(self, kernel_list: list):
        if not kernel_list:
            return
        self._kernel_list.extend(kernel_list)
        kernel_num = len(kernel_list)
        cur_node = self
        while cur_node.parent:
            cur_node._kernel_num += kernel_num
            cur_node = cur_node.parent

    def update_kernel_list(self, kernel_list: list):
        if not kernel_list:
            return
        self._kernel_list.extend(kernel_list)

    def set_memory_allocated(self, memory_allocated: MemoryEvent):
        self._memory_allocated_list.append(memory_allocated)

    def is_step_profiler(self) -> bool:
        return self._event.is_step_profiler()

    def get_step_id(self) -> int:
        if self.is_step_profiler():
            return int(self._event.name.split("#")[1])
        return Constant.VOID_STEP

    def get_op_info(self) -> list:
        return [self.name, self.input_shape, self.input_type, self.call_stack]
