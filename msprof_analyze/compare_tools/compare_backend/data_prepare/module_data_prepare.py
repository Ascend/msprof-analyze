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
import copy
from queue import Queue

from msprof_analyze.compare_tools.compare_backend.compare_bean.origin_data_bean.trace_event_bean import TraceEventBean
from msprof_analyze.compare_tools.compare_backend.profiling_parser.base_profiling_parser import ProfilingResult
from msprof_analyze.compare_tools.compare_backend.utils.module_node import ModuleNode
from msprof_analyze.compare_tools.compare_backend.utils.tree_builder import TreeBuilder
from msprof_analyze.prof_common.constant import Constant

from msprof_analyze.compare_tools.compare_backend.compare_bean.origin_data_bean.db_data_bean.framework_api_bean import (
    FrameworkApiBean,
)


class ModuleDataPrepare:
    def __init__(self, profiling_data: ProfilingResult):
        self.profiling_data = profiling_data
        self._nn_module_list = []
        self._call_function = []
        for event in profiling_data.python_function_data:
            if event.lower_name.startswith("nn.module:"):
                self._nn_module_list.append(event)
            else:
                self._call_function.append(event)
        self._bwd_dict = {}
        self._bwd_pid = self._get_bwd_pid()

    @staticmethod
    def update_module_node_info(fwd_root_node, bwd_root_node, func_root_node):
        queue = Queue()
        queue.put(fwd_root_node)
        queue.put(bwd_root_node)
        while not queue.empty():
            module_node = queue.get()
            module_node.update_torch_op_kernel_list()
            call_function = func_root_node.find_module_call(module_node.start_time)
            if call_function:
                module_node.reset_call_stack(call_function.call_stack)
            for sub_module_node in module_node.child_nodes:
                queue.put(sub_module_node)

    def build_module_tree(self):
        class Event:
            def __init__(self, start_time):
                self.start_time = start_time
                self.x_mode = False

            def is_x_mode(self):
                return self.x_mode

        if not self._nn_module_list:
            return [None, None]
        self._dispatch_torch_op()
        if isinstance(self._nn_module_list[0], FrameworkApiBean):
            kernel_dict = {}
            for torch_op in self.profiling_data.torch_op_data:
                kernel_list = self.profiling_data.kernel_dict.get(torch_op.cann_connection_id)
                if kernel_list:
                    kernel_dict[torch_op.start_time] = kernel_list
            event_list = [Event(start_time) for start_time in kernel_dict]
        else:
            event_list = [TraceEventBean({"ts": ts}) for ts in self.profiling_data.kernel_dict.keys()]
            kernel_dict = self.profiling_data.kernel_dict
        self._nn_module_list.extend(event_list)
        root_node = TreeBuilder.build_module_tree(self._nn_module_list, kernel_dict)
        func_root_node = TreeBuilder.build_module_tree(self._call_function, {})
        bwd_module_list = self.get_bwd_module(root_node)
        if bwd_module_list:
            bwd_module_list.extend(event_list)
        bwd_root_node = TreeBuilder.build_module_tree(bwd_module_list, kernel_dict)
        self.match_torch_op(root_node, bwd_root_node)
        self.update_module_node_info(root_node, bwd_root_node, func_root_node)
        return [root_node, bwd_root_node]

    def get_bwd_module(self, root_node: ModuleNode):
        bwd_module_list = []
        for flow in self.profiling_data.fwdbwd_dict.values():
            start_point = flow.get("start")
            end_point = flow.get("end")
            if not start_point or not end_point:
                continue
            end_event = self._bwd_dict.get(end_point.start_time)
            if not end_event:
                continue
            call_module = root_node.find_module_call(start_point.start_time)
            if call_module:
                bwd_event = copy.deepcopy(end_event)
                bwd_event.reset_name(f"[ BACKWARD ]{call_module.module_name}")
                bwd_module_list.append(bwd_event)
        return bwd_module_list

    def match_torch_op(self, fwd_root_node, bwd_root_node):
        torch_op_list = sorted(self.profiling_data.torch_op_data, key=lambda x: x.start_time)
        for torch_op in torch_op_list:
            if torch_op.is_optimizer():
                continue
            if torch_op.is_step_profiler():
                continue
            matched_module = fwd_root_node.find_module_call(torch_op.start_time)
            if matched_module:
                matched_module.find_torch_op_call(torch_op)
                continue
            matched_module = bwd_root_node.find_module_call(torch_op.start_time)
            if matched_module:
                matched_module.find_torch_op_call(torch_op)

    def _dispatch_torch_op(self):
        for torch_op in self.profiling_data.torch_op_data:
            if torch_op.is_optimizer():
                self._nn_module_list.append(torch_op)
                continue
            if torch_op.pid == self._bwd_pid:
                self._bwd_dict[torch_op.start_time] = torch_op

    def _get_bwd_pid(self):
        for flow in self.profiling_data.fwdbwd_dict.values():
            end_point = flow.get("end")
            if end_point:
                return end_point.pid
        return Constant.INVALID_VALUE
