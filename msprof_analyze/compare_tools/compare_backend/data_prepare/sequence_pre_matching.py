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
from collections import deque

from msprof_analyze.compare_tools.compare_backend.utils.name_function import NameFunction
from msprof_analyze.compare_tools.compare_backend.utils.common_func import longest_common_subsequence_matching
from msprof_analyze.compare_tools.compare_backend.utils.torch_op_node import TorchOpNode
from msprof_analyze.compare_tools.compare_backend.utils.module_node import ModuleNode
from msprof_analyze.prof_common.constant import Constant


class SequencePreMatching:
    OP_TYPE = 1
    MODULE_TYPE = 2

    def __init__(self, args, base_bwd_tid=None, comparison_bwd_tid=None):
        self._args = args
        self._base_bwd_tid = base_bwd_tid
        self._comparison_bwd_tid = comparison_bwd_tid

    @staticmethod
    def _match_none_subsequence(base_ops: list, comparison_ops: list) -> list:
        op_compare_result = [[op, None] for op in iter(base_ops)]
        op_compare_result.extend([[None, op] for op in iter(comparison_ops)])
        return op_compare_result

    @staticmethod
    def _split_operator_data(data_list, bwd_tid):
        split_result = []
        if not data_list:
            return split_result
        data_list.sort(key=lambda x: x.start_time)
        pre_tid = data_list[0].tid
        part_data_dict = {Constant.IS_BWD: pre_tid == bwd_tid, Constant.OPS: []}
        for op in data_list:
            if op.tid == pre_tid or bwd_tid not in (pre_tid, op.tid):
                part_data_dict[Constant.OPS].append(op)
            else:
                split_result.append(part_data_dict)
                part_data_dict = {Constant.IS_BWD: op.tid == bwd_tid, Constant.OPS: [op]}
            pre_tid = op.tid
        split_result.append(part_data_dict)
        return split_result

    def run(self, matching_type, base_data, comparison_data):
        if matching_type == self.MODULE_TYPE:
            return self._match_nn_module(base_data, comparison_data)

        if self._base_bwd_tid is None or self._comparison_bwd_tid is None:
            return self._match_torch_op(base_data, comparison_data)

        base_data = self._split_operator_data(base_data, self._base_bwd_tid)
        comparison_data = self._split_operator_data(comparison_data, self._comparison_bwd_tid)
        if not base_data:
            comparison_data_list = []
            for data in comparison_data:
                comparison_data_list.extend(data.get(Constant.OPS, []))
            return self._match_torch_op([], comparison_data_list)
        if not comparison_data:
            base_data_list = []
            for data in base_data:
                base_data_list.extend(data.get(Constant.OPS, []))
            return self._match_torch_op(base_data_list, [])

        result_data = []
        base_data_len, comparison_data_len = len(base_data), len(comparison_data)
        if base_data[0].get(Constant.IS_BWD) == comparison_data[0].get(Constant.IS_BWD):
            base_index, comparison_index = 0, 0
        elif base_data_len > comparison_data_len:
            result_data.extend(self._match_torch_op(base_data[0].get(Constant.OPS, []), []))
            base_index, comparison_index = 1, 0
        else:
            result_data.extend(self._match_torch_op([], comparison_data[0].get(Constant.OPS, [])))
            base_index, comparison_index = 0, 1
        while base_index < base_data_len:
            comparison_ops = (
                []
                if comparison_index >= comparison_data_len
                else comparison_data[comparison_index].get(Constant.OPS, [])
            )
            result_data.extend(self._match_torch_op(base_data[base_index].get(Constant.OPS, []), comparison_ops))
            base_index += 1
            comparison_index += 1
        while comparison_index < comparison_data_len:
            result_data.extend(self._match_torch_op([], comparison_data[comparison_index].get(Constant.OPS, [])))
            comparison_index += 1
        return result_data

    def _match_torch_op(self, base_ops, comparison_ops) -> list:
        if not base_ops and not comparison_ops:
            return []
        name_func = NameFunction(self._args).get_name_func()
        op_compare_result = (
            longest_common_subsequence_matching(base_ops, comparison_ops, name_func)
            if not self._args.disable_details
            else self._match_none_subsequence(base_ops, comparison_ops)
        )
        if self._args.max_kernel_num is not None:
            op_compare_result = self._drill_down(op_compare_result, name_func)
        return op_compare_result

    def _drill_down(self, compare_result_data: list, name_func: any) -> list:
        drill_down_result = []
        compare_result_data.reverse()
        op_deque = deque(compare_result_data)
        while op_deque:
            match_data = op_deque.pop()
            base_op = match_data[0] if match_data[0] else TorchOpNode()
            comparison_op = match_data[1] if match_data[1] else TorchOpNode()
            if not base_op.child_nodes or not comparison_op.child_nodes:
                drill_down_result.append(match_data)
                continue
            if max(base_op.kernel_num, comparison_op.kernel_num) <= self._args.max_kernel_num:
                drill_down_result.append(match_data)
                continue
            match_list = (
                longest_common_subsequence_matching(base_op.child_nodes, comparison_op.child_nodes, name_func)
                if not self._args.disable_details
                else self._match_none_subsequence(base_op.child_nodes, comparison_op.child_nodes)
            )
            match_list.reverse()
            op_deque.extend(match_list)

        return drill_down_result

    def _match_nn_module(self, base_root_node, comparison_root_node) -> list:
        module_compare_result = []
        for index, base_node in enumerate(base_root_node):
            comparison_node = comparison_root_node[index] if index < len(comparison_root_node) else None
            if not base_node or not comparison_node:
                continue
            module_compare_result.extend(self._matching_all_modules(base_node, comparison_node))
        return module_compare_result

    def _matching_all_modules(self, base_node: ModuleNode, comparison_node: ModuleNode):
        all_matched_modules = []
        matched_queue = deque()
        matched_queue.append([base_node, comparison_node])
        while matched_queue:
            matched_base_node, matched_comparison_node = matched_queue.popleft()
            matched_node_list = self._matching_common_subsequence(matched_base_node, matched_comparison_node)
            all_matched_modules.extend(matched_node_list)
            for matched_node in matched_node_list:
                matched_queue.append(matched_node)
        return all_matched_modules

    def _matching_common_subsequence(self, base_node: ModuleNode, comparison_node: ModuleNode):
        base_modules = base_node.child_nodes if base_node else []
        comparison_modules = comparison_node.child_nodes if comparison_node else []
        if not base_modules and not comparison_modules:
            return []
        name_func = NameFunction(self._args).get_module_name
        result = (
            longest_common_subsequence_matching(base_modules, comparison_modules, name_func)
            if not self._args.disable_details
            else self._match_none_subsequence(base_modules, comparison_modules)
        )
        return result
