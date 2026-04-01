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

import os
from collections import defaultdict
import pandas as pd
import numpy as np

from msprof_analyze.cluster_analyse.cluster_kernels_analysis.operator_mfu.mfu_calculator import MFUCalculator
from msprof_analyze.cluster_analyse.recipes.module_statistic.backward_module_create import BackwardModuleCreator
from msprof_analyze.cluster_analyse.recipes.module_statistic.tree_build import (NodeType, TreeNode, ModuleNode,
                                                                                KernelNode, TreeBuilder)
from msprof_analyze.cluster_analyse.common_func.excel_utils import ExcelUtils
from msprof_analyze.cluster_analyse.recipes.base_recipe_analysis import BaseRecipeAnalysis
from msprof_analyze.prof_exports.module_statistic_export import FrameworkOpToKernelExport, ModuleMstxRangeExport
from msprof_analyze.cluster_analyse.common_func.utils import ensure_numeric_columns
from msprof_analyze.prof_common.db_manager import DBManager
from msprof_analyze.prof_common.constant import Constant
from msprof_analyze.prof_common.logger import get_logger

logger = get_logger()


class ModuleStatistic(BaseRecipeAnalysis):
    TABLE_MODULE_STATISTIC = "ModuleStatistic"
    KERNEL_RELATED_TABLE_LIST = [Constant.TABLE_COMPUTE_TASK_INFO, Constant.TABLE_COMMUNICATION_OP,
                                 Constant.TABLE_COMMUNICATION_SCHEDULE_TASK_INFO]

    def __init__(self, params):
        super().__init__(params)

    @property
    def base_dir(self):
        return os.path.basename(os.path.dirname(__file__))

    def run(self, context, save=True):
        if self._export_type != Constant.DB and self._export_type != Constant.TEXT:
            logger.error(f"Invalid export type: {self._export_type} for module analysis, "
                         f"required to be {Constant.DB} or {Constant.TEXT}")
            return
        mapper_res = self.mapper_func(context)
        if not save:
            valid_res = [(rank, df) for rank, df in mapper_res if df is not None and not df.empty]
            return valid_res
        if self._export_type == Constant.DB:
            total_df = self.reducer_func(mapper_res)
            self.save_db(total_df)
        elif self._export_type == Constant.TEXT:
            self.save_excel(mapper_res)

    def reducer_func(self, mapper_res):
        valid_dfs = [stat_df.assign(rankID=rank_id)
                     for rank_id, stat_df in mapper_res
                     if not stat_df.empty]
        return pd.concat(valid_dfs, ignore_index=True) if valid_dfs else None

    def save_db(self, df):
        if df is None or df.empty:
            logger.warning(f"No module analysis result, skipping dump data")
            return
        self.dump_data(df, Constant.DB_CLUSTER_COMMUNICATION_ANALYZER,
                       self.TABLE_MODULE_STATISTIC, index=False)

    def save_excel(self, mapper_res):
        columns_to_merge = ['Parent Module', 'Module']
        column_width_config = {"Parent Module": 40,
                               "Module": 40,
                               "Op Name": 40,
                               "Kernel List": 50,
                               "Total Kernel Duration(ns)": 10,
                               "Avg Kernel Duration(ns)": 10,
                               "Op Count": 10}
        excel_utils = ExcelUtils()
        for rank_id, stat_df in mapper_res:
            if stat_df.empty:
                logger.warning(f"No module analysis result for rank {rank_id}, skipping dump data")
                continue
            file_name = f"module_statistic_{rank_id}.xlsx"
            try:
                excel_utils.create_excel_writer(self.output_path, file_name, stat_df)
                excel_utils.merge_duplicate_cells(columns_to_merge)
                excel_utils.set_column_width(column_width_config)
                excel_utils.set_row_height(0, 27)  # 标题行行高27
                excel_utils.save_and_close()
                excel_utils.clear()
            except Exception as e:
                logger.error(f"Save excel failed, err: {e}")

    def _mapper_func(self, data_map, analysis_class):
        profiler_db_path = data_map.get(Constant.PROFILER_DB_PATH)
        rank_id = data_map.get(Constant.RANK_ID)

        # 查询数据
        module_df, kernel_df = self._query_all_data(profiler_db_path, rank_id)
        if module_df is None or module_df.empty:
            return rank_id, pd.DataFrame()

        # 计算MFU
        kernel_df = self._calculate_kernel_mfu(data_map, kernel_df)

        # 处理反向传播数据
        backward_creator = BackwardModuleCreator(profiler_db_path)
        bwd_module_df = backward_creator.run(module_df)
        if not bwd_module_df.empty:
            module_df = pd.concat([module_df, bwd_module_df])

        # 构建树并处理
        root = self._build_complete_tree(module_df, kernel_df)
        if not root:
            logger.error(f"Empty event tree for rank {rank_id}")
            return rank_id, pd.DataFrame()

        verbose_df = self._flatten_tree_to_dataframe(root)
        if verbose_df.empty:
            logger.error(f"Failed to extract event tree data for rank {rank_id}")
            return rank_id, pd.DataFrame()

        stat_df = self._aggregate_module_operator_stats(verbose_df)
        return rank_id, stat_df

    def _query_all_data(self, profiler_db_path, rank_id):
        # 查询模块数据
        module_export = ModuleMstxRangeExport(profiler_db_path, self._recipe_name)
        module_df = module_export.read_export_db()
        if module_df is None or module_df.empty:
            logger.error(f"Can not export mstx range event from rank {rank_id}")
            return None, None

        module_df = ensure_numeric_columns(module_df, ['startNs', 'endNs'])

        # 查询kernel数据
        kernel_df = self._query_framework_op_to_kernel(profiler_db_path)
        if kernel_df is None or kernel_df.empty:
            logger.error(f"Can not export framework op to kernel mapper from rank {rank_id}")
            return None, None

        kernel_df = ensure_numeric_columns(kernel_df, ['kernel_ts', 'kernel_end', 'op_ts', 'op_end'])

        return module_df, kernel_df

    def _query_framework_op_to_kernel(self, profiler_db_path):
        valid_dfs = []
        for table_name in self.KERNEL_RELATED_TABLE_LIST:
            if not DBManager.check_tables_in_db(profiler_db_path, table_name):
                continue
            export = FrameworkOpToKernelExport(profiler_db_path, self._recipe_name, table_name)
            df = export.read_export_db()
            if df is not None and not df.empty:
                valid_dfs.append(df)

        if not valid_dfs:
            return None

        try:
            return pd.concat(valid_dfs, ignore_index=True)
        except Exception as e:
            logger.error(f"Failed to concatenate framework op to kernel dataframes: {str(e)}")
            return None

    def _build_complete_tree(self, module_df, kernel_df):
        # 创建模块节点
        module_nodes = TreeBuilder.create_tree_nodes_from_df(
            module_df, NodeType.MODULE_EVENT_NODE, 'startNs', 'endNs', 'name')

        # 创建OP和kernel节点
        op_nodes = []
        if kernel_df is not None and not kernel_df.empty:
            # 按op_name分组处理kernel数据
            op_groups = defaultdict(list)
            for _, row in kernel_df.iterrows():
                op_groups[(row['op_name'], row['op_ts'], row['op_end'])].append(row)

            # 创建op节点和对应的kernel节点
            for (op_name, op_ts, op_end), kernels in op_groups.items():
                op_node = TreeNode(op_ts, op_end, NodeType.CPU_OP_EVENT, op_name)

                # 为每个op添加对应的kernel节点
                for kernel in kernels:
                    kernel_node = KernelNode(kernel['kernel_ts'], kernel['kernel_end'],
                                             kernel['kernel_name'], kernel['mfu'])
                    op_node.add_child(kernel_node)

                op_nodes.append(op_node)

        # 合并所有节点并构建树
        all_nodes = module_nodes + op_nodes
        if not all_nodes:
            logger.error("Empty node (module_event/cpu_op/kernel), skipping tree build")
            return None

        # 计算全局时间范围
        global_start = min(module_df['startNs'].min(), kernel_df['kernel_ts'].min(), kernel_df['op_ts'].min())
        global_end = max(module_df['endNs'].max(), kernel_df['kernel_end'].max(), kernel_df['op_end'].max())
        return TreeBuilder.build_tree_from_events(all_nodes, global_start, global_end)

    def _flatten_tree_to_dataframe(self, root_node):
        results = []

        def process_module_op_pair(module_node, op_node, module_node_deque):
            """处理模块-算子对"""
            # 类型检查确保是ModuleNode
            if not isinstance(module_node, ModuleNode):
                return

            module = module_node.name
            module_parent = "/".join([node.name for node in module_node_deque]).strip("/")

            if not module and not module_parent:
                return

            # 判断是否为backward：检查当前节点或父节点链中是否有backward
            is_backward = module_node.is_backward or any(
                isinstance(parent, ModuleNode) and parent.is_backward
                for parent in module_node_deque
            )

            # 收集该op下的所有kernel信息
            kernel_names = []
            total_device_time = 0.0
            mfu_list = []
            for kernel_child in op_node.children:
                if kernel_child.node_type == NodeType.KERNEL_EVENT:
                    kernel_names.append(kernel_child.name)
                    duration = kernel_child.end - kernel_child.start
                    total_device_time += duration
                    mfu_list.append(kernel_child.mfu)

            results.append({
                'module_parent': module_parent,
                'module': module if not is_backward else f"[{ModuleNode.BACKWARD}]{module}",
                'module_start': module_node.start,
                'module_end': module_node.end,
                'op_name': op_node.name,
                'op_start': op_node.start,
                'op_end': op_node.end,
                'kernel_list': ', '.join(kernel_names),
                'device_time': total_device_time,
                'mfu_list': mfu_list
            })

        # 使用通用的树遍历方法
        TreeBuilder.traverse_module_tree(root_node, process_module_op_pair)

        if not results:
            return pd.DataFrame()

        # 转换为DataFrame并排序
        df = pd.DataFrame(results)
        df = df.sort_values(by=['module_start', 'op_start'], ascending=[True, True])
        return df

    def _aggregate_module_operator_stats(self, df):
        stat_df = self._aggregate_module_stats(df)
        return self._format_stat_df_columns(stat_df)

    def _aggregate_module_stats(self, df):
        if df is None or df.empty:
            logger.warning("Empty dataframe received for aggregation")
            return pd.DataFrame()

        # 为每个算子添加在module下的顺序位置
        distinct_module_columns = ['module_parent', 'module', 'module_start', 'module_end']
        df['op_order'] = df.groupby(distinct_module_columns).cumcount()

        # 创建seq_key保证唯一性，并分配ID
        op_seq = df.groupby(distinct_module_columns)['op_name'].transform(lambda x: '/'.join(x))
        df['seq_key'] = df['module_parent'] + "|" + df['module'] + "|" + op_seq
        df['seq_id'] = pd.factorize(op_seq)[0]
        df.drop(columns=['seq_key'], inplace=True)

        def compute_mfu_avg(series_of_lists):
            arr = np.array(series_of_lists.tolist())
            result_list = []
            for pos in range(arr.shape[1]):
                values_at_pos = arr[:, pos]
                valid_vals = values_at_pos[values_at_pos > 0]
                if len(valid_vals) > 0:
                    avg_val = round(valid_vals.mean() * 100, 2)
                    result_list.append(str(avg_val) + '%')
            return ','.join(result_list)

        # 聚合统计
        stat_df = (
            df.groupby(['module_parent', 'module', 'op_name', 'op_order', 'kernel_list', 'seq_id'])
            .agg(
                module_start=('module_start', 'first'),
                module_end=('module_end', 'first'),
                total_kernel_duration=('device_time', 'sum'),
                avg_kernel_duration=('device_time', 'mean'),
                op_count=('device_time', 'count'),
                op_start=('op_start', 'min'),
                avg_mfu=('mfu_list', compute_mfu_avg)
            ).reset_index()
        )

        # 区分同一module_parent下，module名称相同，但实际算子执行不同的层级
        stat_df = self._distinguish_contiguous_module(stat_df)

        # 根据算子执行顺序排序，删除后续不再使用的列
        stat_df = (stat_df.sort_values(by=['op_start', 'op_order'])
                   .drop(columns=['module_start', 'module_end', 'seq_id', 'op_order', 'op_start'])
                   .reset_index(drop=True))

        return stat_df

    def _distinguish_contiguous_module(self, stat_df):
        stat_df = stat_df.sort_values('op_start').reset_index(drop=True)
        stat_df['index'] = stat_df.index
        result_dfs = []

        for _, group in stat_df.groupby(['module_parent', 'module']):
            group = group.copy().sort_values('index')
            group['continuous_group'] = (group['index'].diff() != 1).cumsum()

            for _, subgroup in group.groupby('continuous_group'):
                unique_seq_ids = subgroup['seq_id'].unique()
                if len(unique_seq_ids) > 1:
                    seq_id_to_suffix = {seq_id: i for i, seq_id in enumerate(sorted(unique_seq_ids))}
                    for idx in subgroup.index:
                        suffix = seq_id_to_suffix[group.loc[idx, 'seq_id']]
                        group.loc[idx, 'module'] = f"{group.loc[idx, 'module']}_{suffix}"

            result_dfs.append(group)

        return pd.concat(result_dfs, ignore_index=True).drop(columns=['index', 'continuous_group'])

    def _format_stat_df_columns(self, stat_df):
        try:
            # 如果没有任何MFU信息，不输出这一列
            empty_mfu = stat_df['avg_mfu'].isna().all() or stat_df['avg_mfu'].eq('').all()
            if empty_mfu:
                stat_df = stat_df.drop(columns=['avg_mfu'])

            if self._export_type == Constant.DB:
                column_mapping = {
                    'module_parent': 'parentModule',
                    'op_name': 'opName',
                    'kernel_list': 'kernelList',
                    'op_count': 'opCount',
                    'total_kernel_duration': 'totalKernelDuration(ns)',
                    'avg_kernel_duration': 'avgKernelDuration(ns)',
                    'avg_mfu': 'avgMFU'
                }
            elif self._export_type == Constant.TEXT:
                column_mapping = {
                    'module_parent': 'Parent Module',
                    'module': 'Module',
                    'op_name': 'Op Name',
                    'kernel_list': 'Kernel List',
                    'op_count': 'Op Count',
                    'total_kernel_duration': 'Total Kernel Duration(ns)',
                    'avg_kernel_duration': 'Avg Kernel Duration(ns)',
                    'avg_mfu': 'Avg MFU'
                }
            else:
                return stat_df

            return stat_df.rename(columns=column_mapping)
        except Exception as e:
            logger.error(f"Failed to format statistic data's title, error message: {e}")
            return pd.DataFrame()

    def _calculate_kernel_mfu(self, data_map, op_kernel_df):
        mfu_worker = MFUCalculator(data_map, op_kernel_df)
        mfu_df = mfu_worker.run()
        if mfu_df.empty or 'mfu' not in mfu_df.columns:
            logger.warning(f"No MFU calculated for kernels.")
            op_kernel_df['mfu'] = -1.0
            return op_kernel_df
        else:
            op_kernel_df = pd.merge(op_kernel_df, mfu_df, on=['kernel_name', 'kernel_ts', 'kernel_end'], how='left')
            return op_kernel_df

