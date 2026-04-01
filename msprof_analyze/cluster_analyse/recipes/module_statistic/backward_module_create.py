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

import pandas as pd

from msprof_analyze.cluster_analyse.recipes.module_statistic.tree_build import NodeType, ModuleNode, TreeBuilder
from msprof_analyze.prof_exports.module_statistic_export import FwdBwdFlowExport
from msprof_analyze.cluster_analyse.common_func.utils import ensure_numeric_columns
from msprof_analyze.prof_common.logger import get_logger

logger = get_logger()


class BackwardModuleCreator:
    PARENT_MODULE_EXTEND_TIME = 1

    def __init__(self, profiler_db_path):
        self.profiler_db_path = profiler_db_path
        self.tree_builder = TreeBuilder()

    def run(self, module_df):
        logger.info(f"Start to create backward module events.")
        if module_df.empty:
            logger.info(f"No module event. Skip backward module creation.")
            return pd.DataFrame()

        fwd_bwd_df = self._query_fwd_bwd_connections()
        if fwd_bwd_df.empty:
            logger.info(f"No fwd-bwd connections. Skip backward module creation.")
            return pd.DataFrame()

        backward_events = self.create_backward_module_events(module_df, fwd_bwd_df)
        logger.info(f"Created {len(backward_events)} backward module events.")

        return backward_events

    def create_backward_module_events(self, module_df, fwd_bwd_df):
        # 创建模块节点和前向节点
        module_nodes = self.tree_builder.create_tree_nodes_from_df(
            module_df, NodeType.MODULE_EVENT_NODE, 'startNs', 'endNs', 'name')

        fwd_nodes = self.tree_builder.create_tree_nodes_from_df(
            fwd_bwd_df, NodeType.CPU_OP_EVENT, 'fwd_ts', 'fwd_end', 'fwd_name')

        # 构建树
        all_nodes = module_nodes + fwd_nodes
        global_start = min(module_df['startNs'].min(), fwd_bwd_df['fwd_ts'].min())
        global_end = max(module_df['endNs'].max(), fwd_bwd_df['fwd_end'].max())
        root = self.tree_builder.build_tree_from_events(all_nodes, global_start, global_end)

        # 根据建树结果，得到前向算子归属的模块
        fwd_module_mappings = self._collect_fwd_module_mappings(root)
        if not fwd_module_mappings:
            return pd.DataFrame()

        # 合并前向反向数据并创建新的模块事件
        return self._generate_bwd_module_events(fwd_module_mappings, fwd_bwd_df)

    def _collect_fwd_module_mappings(self, root):
        # 创建前向算子与模型层级的映射关系
        results = []

        def process_fwd_node(module_node, fwd_node, module_node_deque):
            """处理前向节点"""
            if not isinstance(module_node, ModuleNode):
                return

            module = module_node.name
            module_parent = "/".join([node.name for node in module_node_deque]).strip("/")

            # 跳过没有module归属的前向节点
            if not module and not module_parent:
                return

            results.append({
                'module_parent': module_parent,
                'module': module,
                'module_start': module_node.start,
                'module_end': module_node.end,
                'fwd_name': fwd_node.name,
                'fwd_ts': fwd_node.start,
                'fwd_end': fwd_node.end,
            })

        self.tree_builder.traverse_module_tree(root, callback=process_fwd_node)
        return results

    def _generate_bwd_module_events(self, fwd_module_mappings, fwd_bwd_df):
        # 转换为DataFrame并排序
        fwd_module_df = pd.DataFrame(fwd_module_mappings)
        fwd_module_df = fwd_module_df.sort_values(by=['module_start', 'fwd_ts'], ascending=[True, True])

        # 合并前向反向数据
        merged_df = pd.merge(fwd_module_df, fwd_bwd_df, on=['fwd_name', 'fwd_ts', 'fwd_end'], how='inner')
        if merged_df.empty:
            return pd.DataFrame()

        # 创建新的模块事件
        merged_df.sort_values(by=['bwd_ts'], inplace=True)
        merged_df['group'] = (merged_df[['module_parent', 'module', 'module_start', 'module_end']]
                              != merged_df[['module_parent', 'module', 'module_start', 'module_end']]
                              .shift()).any(axis=1).cumsum()

        # 生成父模块事件
        parent_bwd_modules = merged_df.groupby('group').agg(
            name=('module_parent', 'first'),
            startNs=('bwd_ts', lambda x: x.min() - self.PARENT_MODULE_EXTEND_TIME),
            endNs=('bwd_end', lambda x: x.max() + self.PARENT_MODULE_EXTEND_TIME),
        )
        parent_bwd_modules = parent_bwd_modules[parent_bwd_modules['name'] != ""]

        # 生成具体backward模块事件
        bwd_modules = merged_df.groupby('group').agg(
            name=('module', 'first'),
            startNs=('bwd_ts', 'min'),
            endNs=('bwd_end', 'max'),
        )
        new_modules = pd.concat([parent_bwd_modules, bwd_modules])
        new_modules[ModuleNode.MODULE_TYPE_COL_NAME] = ModuleNode.BACKWARD

        return new_modules

    def _query_fwd_bwd_connections(self):
        # 查询前向反向数据
        fwd_bwd_export = FwdBwdFlowExport(self.profiler_db_path, recipe_name="")
        fwd_bwd_df = fwd_bwd_export.read_export_db()
        if fwd_bwd_df is None or fwd_bwd_df.empty:
            return pd.DataFrame()
        fwd_bwd_df = ensure_numeric_columns(fwd_bwd_df, ['fwd_ts', 'fwd_end', 'bwd_ts', 'bwd_end'])
        return fwd_bwd_df
