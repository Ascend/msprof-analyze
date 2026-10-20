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
from msprof_analyze.compare_tools.compare_backend.profiling_parser.base_profiling_parser import ProfilingResult
from msprof_analyze.compare_tools.compare_backend.utils.tree_builder import TreeBuilder
from msprof_analyze.prof_common.constant import Constant
from msprof_analyze.prof_common.logger import get_logger

logger = get_logger()


class OperatorDataPrepare:
    def __init__(self, profiling_data: ProfilingResult, specified_step_id: int = Constant.VOID_STEP):
        self.profiling_data = profiling_data
        self._all_nodes = self._build_tree()
        self._root_node = self._all_nodes[0]
        self._specified_step_id = specified_step_id

    def get_top_layer_ops(self) -> any:
        if len(self._all_nodes) < 1:
            return []
        return self._get_top_layers_ops_from_root_node(self._root_node.child_nodes)

    def get_all_layer_ops(self) -> any:
        result_data = []
        if len(self._all_nodes) < 1:
            return result_data
        if self._specified_step_id == Constant.VOID_STEP:
            return list(filter(lambda x: not x.is_step_profiler(), self._all_nodes[1:]))
        node_queue = self._get_top_layers_ops_from_root_node(self._root_node.child_nodes)
        while len(node_queue) > 0:
            node = node_queue.pop(0)
            result_data.append(node)
            if node.child_nodes:
                node_queue.extend(node.child_nodes)
        if not result_data:
            msg = (
                f"There is no operator event data for step {self._specified_step_id}, "
                "please check whether the data contains this step."
            )
            raise RuntimeError(msg)
        return result_data

    def _build_tree(self):
        return TreeBuilder.build_tree(
            self.profiling_data.torch_op_data, self.profiling_data.kernel_dict, self.profiling_data.memory_list
        )

    def _get_top_layers_ops_from_root_node(self, top_layers_nodes: list) -> list:
        result_data = []
        for level1_node in top_layers_nodes:
            if self._specified_step_id == Constant.VOID_STEP:
                if level1_node.is_step_profiler():
                    result_data.extend(level1_node.child_nodes)
                else:
                    result_data.append(level1_node)
            elif level1_node.is_step_profiler() and level1_node.get_step_id() == self._specified_step_id:
                result_data.extend(level1_node.child_nodes)
        if not result_data and self._specified_step_id != Constant.VOID_STEP:
            logger.warning(
                "[WARNING] There is no operator infomation for step %s, "
                "please check whether the data contains this step.",
                self._specified_step_id,
            )
        return result_data
