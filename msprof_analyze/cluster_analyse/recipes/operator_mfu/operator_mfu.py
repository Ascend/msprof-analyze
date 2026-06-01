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
from msprof_analyze.cluster_analyse.recipes.operator_mfu.tree_build import (NodeType, TreeNode, ModuleNode,
                                                                            KernelNode, TreeBuilder)
from msprof_analyze.cluster_analyse.common_func.excel_utils import ExcelUtils
from msprof_analyze.cluster_analyse.recipes.base_recipe_analysis import BaseRecipeAnalysis
from msprof_analyze.prof_exports.module_statistic_export import FrameworkOpToKernelExport, ModuleMstxRangeExport
from msprof_analyze.cluster_analyse.common_func.utils import ensure_numeric_columns
from msprof_analyze.prof_common.db_manager import DBManager
from msprof_analyze.prof_common.constant import Constant
from msprof_analyze.prof_common.logger import get_logger

logger = get_logger()


class OperatorMfu(BaseRecipeAnalysis):
    """生成 kernel 级 MFU 明细和 module 级 MFU 统计结果。"""
    TABLE_OPERATOR_MFU = "OperatorMFU"
    TABLE_MODULE_MFU = "ModuleMFU"
    KERNEL_RELATED_TABLE_LIST = [Constant.TABLE_COMPUTE_TASK_INFO, Constant.TABLE_COMMUNICATION_OP,
                                 Constant.TABLE_COMMUNICATION_SCHEDULE_TASK_INFO]

    def __init__(self, params):
        """初始化算子 MFU 分析任务。"""
        super().__init__(params)

    @property
    def base_dir(self):
        """返回当前分析任务目录名。"""
        return os.path.basename(os.path.dirname(__file__))

    def run(self, context, save=True):
        """执行算子 MFU 分析，并按导出类型保存结果。"""
        if self._export_type != Constant.DB and self._export_type != Constant.TEXT:
            logger.error(f"Invalid export type: {self._export_type} for operator mfu analysis, "
                         f"required to be {Constant.DB} or {Constant.TEXT}")
            return
        mapper_res = self.mapper_func(context)
        if not save:
            valid_res = [(rank, kernel_df, module_df) for rank, kernel_df, module_df in mapper_res
                         if ((kernel_df is not None and not kernel_df.empty)
                             or (module_df is not None and not module_df.empty))]
            return valid_res
        if self._export_type == Constant.DB:
            kernel_mfu_df, module_mfu_df = self.reducer_func(mapper_res)
            self.save_db(kernel_mfu_df, module_mfu_df)
        elif self._export_type == Constant.TEXT:
            self.save_excel(mapper_res)

    def mapper_func(self, context):
        """并发执行各 rank 的算子 MFU 分析。"""
        db_paths = self._get_rank_db()
        if not db_paths:
            return []
        return context.wait(
            context.map(
                self._mapper_func,
                db_paths,
                analysis_class=self._recipe_name
            )
        )

    def _mapper_func(self, data_map, analysis_class):
        """生成单个 rank 的 kernel 级和 module 级 MFU 结果。"""
        profiler_db_path = data_map.get(Constant.PROFILER_DB_PATH)
        rank_id = data_map.get(Constant.RANK_ID)

        # 查询 module 和 kernel 数据。
        module_df, kernel_df = self._query_all_data(profiler_db_path, rank_id)

        # kernel 数据是计算 MFU 的必要输入，缺失时当前 rank 无法继续分析。
        if kernel_df is None or kernel_df.empty:
            logger.error(f"No kernel data found for rank {rank_id}")
            return rank_id, pd.DataFrame(), pd.DataFrame()

        # 计算 kernel 级 MFU。
        kernel_df = self._calculate_kernel_mfu(data_map, kernel_df)

        # kernel 级结果不依赖 module 数据，始终优先生成。
        kernel_mfu_df = self._generate_kernel_mfu_list(kernel_df, rank_id)

        # module 数据是可选输入，缺失时仍保留 kernel 级结果。
        module_mfu_df = pd.DataFrame()
        if module_df is not None and not module_df.empty:
            root = self._build_complete_tree(module_df, kernel_df)
            if root:
                module_mfu_df = self._generate_module_mfu_stats(root, rank_id)
            else:
                logger.warning(f"Failed to build event tree for rank {rank_id}, skipping module MFU stats")
        else:
            logger.debug(f"No module data found for rank {rank_id}, only kernel-level MFU will be generated")

        return rank_id, kernel_mfu_df, module_mfu_df

    def _query_all_data(self, profiler_db_path, rank_id):
        """查询单个 rank 的 module 数据和 kernel 数据。"""
        # module 数据用于生成聚合统计，缺失时仍可输出 kernel 级明细。
        module_export = ModuleMstxRangeExport(profiler_db_path, self._recipe_name)
        module_df = module_export.read_export_db()
        if module_df is None or module_df.empty:
            logger.debug(f"No mstx range event (module data) found from rank {rank_id}")
            module_df = pd.DataFrame()
        else:
            module_df = ensure_numeric_columns(module_df, ['startNs', 'endNs'])

        # kernel 数据用于计算 MFU，是必要输入。
        kernel_df = self._query_framework_op_to_kernel(profiler_db_path)
        if kernel_df is None or kernel_df.empty:
            logger.error(f"Can not export framework op to kernel mapper from rank {rank_id}")
            return None, None

        kernel_df = ensure_numeric_columns(kernel_df, ['kernel_ts', 'kernel_end', 'op_ts', 'op_end'])

        return module_df, kernel_df

    def _query_framework_op_to_kernel(self, profiler_db_path):
        """汇总不同任务表中的 framework op 与 kernel 关联关系。"""
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

    def _calculate_kernel_mfu(self, data_map, op_kernel_df):
        """计算 kernel MFU，并合并回 op 与 kernel 的关联数据。"""
        mfu_worker = MFUCalculator(data_map, op_kernel_df)
        mfu_df = mfu_worker.run()
        if mfu_df.empty or 'mfu' not in mfu_df.columns:
            logger.warning("No MFU calculated for kernels.")
            op_kernel_df['mfu'] = -1.0
            return op_kernel_df
        else:
            op_kernel_df = pd.merge(op_kernel_df, mfu_df, on=['kernel_name', 'kernel_ts', 'kernel_end'], how='left')
            op_kernel_df['mfu'] = op_kernel_df['mfu'].fillna(-1.0)
            return op_kernel_df

    def _build_complete_tree(self, module_df, kernel_df):
        """构建 module、op 和 kernel 的层级树。"""
        # 创建 module 节点。
        module_nodes = TreeBuilder.create_tree_nodes_from_df(
            module_df, NodeType.MODULE_EVENT_NODE, 'startNs', 'endNs', 'name')

        # 创建 op 和 kernel 节点。
        op_nodes = []
        if kernel_df is not None and not kernel_df.empty:
            # 按 op 的名称和时间范围分组，避免同名 op 被错误合并。
            op_groups = defaultdict(list)
            for _, row in kernel_df.iterrows():
                op_groups[(row['op_name'], row['op_ts'], row['op_end'])].append(row)

            # 创建 op 节点以及对应的 kernel 子节点。
            for (op_name, op_ts, op_end), kernels in op_groups.items():
                op_node = TreeNode(op_ts, op_end, NodeType.CPU_OP_EVENT, op_name)

                # 将 MFU 保存在 kernel 节点中，供 module 级聚合使用。
                for kernel in kernels:
                    kernel_mfu = kernel.get('mfu', -1.0) if 'mfu' in kernel else -1.0
                    kernel_node = KernelNode(kernel['kernel_ts'], kernel['kernel_end'],
                                             kernel['kernel_name'], kernel_mfu)
                    op_node.add_child(kernel_node)

                op_nodes.append(op_node)

        # 合并所有节点并构建树。
        all_nodes = module_nodes + op_nodes
        if not all_nodes:
            logger.error("Empty node (module_event/cpu_op/kernel), skipping tree build")
            return None

        # 根节点覆盖所有事件的时间范围。
        global_start = min(module_df['startNs'].min(), kernel_df['kernel_ts'].min(), kernel_df['op_ts'].min())
        global_end = max(module_df['endNs'].max(), kernel_df['kernel_end'].max(), kernel_df['op_end'].max())
        return TreeBuilder.build_tree_from_events(all_nodes, global_start, global_end)

    def _generate_kernel_mfu_list(self, kernel_df, rank_id):
        """生成 kernel 级 MFU 明细。"""
        if kernel_df is None or kernel_df.empty:
            return pd.DataFrame()

        # -1 表示当前 kernel 未计算出有效 MFU，不写入明细。
        valid_kernel_df = kernel_df[kernel_df.get('mfu', -1) != -1.0].copy()
        if valid_kernel_df.empty:
            logger.warning(f"No valid MFU data for rank {rank_id}")
            return pd.DataFrame()

        # 生成导出所需的 kernel 级字段。
        kernel_mfu_list = []
        for _, row in valid_kernel_df.iterrows():
            chip_peak_tflops = round(row.get('chip_peak', 0) / 1e12, 2) if row.get('chip_peak', 0) > 0 else 0
            mfu = round(row.get('mfu', 0), 4)
            # 优先使用 MFUCalculator 计算的实际 TFLOPS，缺失时按 MFU 和峰值补算。
            actual_tflops = row.get('actual_tflops', round(mfu * chip_peak_tflops, 2))
            kernel_mfu_list.append({
                'rank_id': rank_id,
                'op_name': row.get('op_name', ''),
                'kernel_name': row.get('kernel_name', ''),
                'kernel_ts': row.get('kernel_ts', 0),
                'kernel_end': row.get('kernel_end', 0),
                'kernel_duration': row.get('kernel_duration', row.get('kernel_end', 0) - row.get('kernel_ts', 0)),
                'mfu': mfu,
                'actual_tflops': actual_tflops,
                'chip_peak_tflops': chip_peak_tflops,
                'flops': row.get('flops', 0),
                'flops_op_name': row.get('flops_op_name', ''),
                'input_shapes': row.get('input_shapes', ''),
                'output_shapes': row.get('output_shapes', ''),
            })

        if not kernel_mfu_list:
            return pd.DataFrame()

        return pd.DataFrame(kernel_mfu_list)

    def _generate_module_mfu_stats(self, root_node, rank_id):
        """生成 module 级 MFU 统计。"""
        results = []

        def process_module_op_pair(module_node, op_node, module_node_deque):
            """将 module 与直属 op 转换为一条待聚合记录。"""
            if not isinstance(module_node, ModuleNode):
                return

            module = module_node.name
            module_parent = "/".join([node.name for node in module_node_deque]).strip("/")

            if not module and not module_parent:
                return

            # 当前节点或父节点链包含 backward 时，将当前 module 标记为反向传播。
            is_backward = module_node.is_backward or any(
                isinstance(parent, ModuleNode) and parent.is_backward
                for parent in module_node_deque
            )

            # 收集当前 op 下的所有 kernel 信息。
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
                'rank_id': rank_id,
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

        # 使用通用树遍历方法生成待聚合记录。
        TreeBuilder.traverse_module_tree(root_node, process_module_op_pair)

        if not results:
            return pd.DataFrame()

        # 转换为 DataFrame，并按 module 和 op 的开始时间排序。
        df = pd.DataFrame(results)
        df = df.sort_values(by=['module_start', 'op_start'], ascending=[True, True])

        # 聚合 module 级统计数据。
        return self._aggregate_module_mfu_stats(df)

    def _aggregate_module_mfu_stats(self, df):
        """聚合 module 级 MFU 统计。"""
        if df is None or df.empty:
            logger.warning("Empty dataframe received for aggregation")
            return pd.DataFrame()

        # 为每个算子添加在 module 下的顺序位置。
        distinct_module_columns = ['rank_id', 'module_parent', 'module', 'module_start', 'module_end']
        df['op_order'] = df.groupby(distinct_module_columns).cumcount()

        # 创建 seq_key 保证唯一性，并分配 ID。
        op_seq = df.groupby(distinct_module_columns)['op_name'].transform(lambda x: '/'.join(x))
        df['seq_key'] = df['rank_id'].astype(str) + "|" + df['module_parent'] + "|" + df['module'] + "|" + op_seq
        df['seq_id'] = pd.factorize(op_seq)[0]
        df.drop(columns=['seq_key'], inplace=True)

        def compute_mfu_avg(series_of_lists):
            """按 kernel 位置计算多次调用的平均 MFU。"""
            arr = np.array(series_of_lists.tolist())
            result_list = []
            for pos in range(arr.shape[1]):
                values_at_pos = arr[:, pos]
                valid_vals = values_at_pos[values_at_pos > 0]
                if len(valid_vals) > 0:
                    avg_val = round(valid_vals.mean() * 100, 2)
                    result_list.append(str(avg_val) + '%')
            return ','.join(result_list)

        # 聚合统计。
        stat_df = (
            df.groupby(['rank_id', 'module_parent', 'module', 'op_name', 'op_order', 'kernel_list', 'seq_id'])
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

        # 区分名称相同但实际算子序列不同的连续 module。
        stat_df = self._distinguish_contiguous_module(stat_df)

        # 根据算子执行顺序排序，删除后续不再使用的列。
        stat_df = (stat_df.sort_values(by=['op_start', 'op_order'])
                   .drop(columns=['module_start', 'module_end', 'seq_id', 'op_order', 'op_start'])
                   .reset_index(drop=True))

        return stat_df

    def _distinguish_contiguous_module(self, stat_df):
        """区分名称相同但算子序列不同的连续 module。"""
        stat_df = stat_df.sort_values('op_start').reset_index(drop=True)
        stat_df['index'] = stat_df.index
        result_dfs = []

        for _, group in stat_df.groupby(['rank_id', 'module_parent', 'module']):
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

    def reducer_func(self, mapper_res):
        """合并所有 rank 的 kernel 级和 module 级结果。"""
        kernel_mfu_dfs = []
        module_mfu_dfs = []

        for rank_id, kernel_df, module_df in mapper_res:
            if kernel_df is not None and not kernel_df.empty:
                kernel_mfu_dfs.append(kernel_df)
            if module_df is not None and not module_df.empty:
                module_mfu_dfs.append(module_df)

        kernel_mfu_result = pd.concat(kernel_mfu_dfs, ignore_index=True) if kernel_mfu_dfs else pd.DataFrame()
        module_mfu_result = pd.concat(module_mfu_dfs, ignore_index=True) if module_mfu_dfs else pd.DataFrame()

        return kernel_mfu_result, module_mfu_result

    def save_db(self, kernel_mfu_df, module_mfu_df):
        """将分析结果写入数据库。"""
        if kernel_mfu_df is not None and not kernel_mfu_df.empty:
            kernel_mfu_df = self._format_kernel_mfu_columns(kernel_mfu_df, Constant.DB)
            self.dump_data(kernel_mfu_df, Constant.DB_CLUSTER_COMMUNICATION_ANALYZER,
                           self.TABLE_OPERATOR_MFU, index=False)

        if module_mfu_df is not None and not module_mfu_df.empty:
            module_mfu_df = self._format_module_mfu_columns(module_mfu_df, Constant.DB)
            self.dump_data(module_mfu_df, Constant.DB_CLUSTER_COMMUNICATION_ANALYZER,
                           self.TABLE_MODULE_MFU, index=False)

    def save_excel(self, mapper_res):
        """将各 rank 的分析结果写入 Excel 文件。"""
        excel_utils = ExcelUtils()

        for rank_id, kernel_df, module_df in mapper_res:
            # 保存 kernel 级 MFU。
            if kernel_df is not None and not kernel_df.empty:
                kernel_df = self._format_kernel_mfu_columns(kernel_df, Constant.TEXT)
                file_name = f"operator_mfu_kernel_{rank_id}.xlsx"
                try:
                    excel_utils.create_excel_writer(self.output_path, file_name, kernel_df)
                    excel_utils.set_column_width({
                        "Kernel Name": 50,
                        "Op Name": 40,
                        "MFU": 10,
                        "Kernel Duration(ns)": 15
                    })
                    excel_utils.save_and_close()
                    excel_utils.clear()
                except Exception as e:
                    logger.error(f"Save kernel MFU excel failed, err: {e}")

            # 保存 module 级 MFU。
            if module_df is not None and not module_df.empty:
                module_df = self._format_module_mfu_columns(module_df, Constant.TEXT)
                file_name = f"operator_mfu_module_{rank_id}.xlsx"
                columns_to_merge = ['Parent Module', 'Module']
                column_width_config = {
                    "Parent Module": 40,
                    "Module": 40,
                    "Op Name": 40,
                    "Kernel List": 50,
                    "Total Kernel Duration(ns)": 10,
                    "Avg Kernel Duration(ns)": 10,
                    "Op Count": 10,
                    "Avg MFU": 10
                }
                try:
                    excel_utils.create_excel_writer(self.output_path, file_name, module_df)
                    excel_utils.merge_duplicate_cells(columns_to_merge)
                    excel_utils.set_column_width(column_width_config)
                    excel_utils.set_row_height(0, 27)
                    excel_utils.save_and_close()
                    excel_utils.clear()
                except Exception as e:
                    logger.error(f"Save module MFU excel failed, err: {e}")

    def _format_kernel_mfu_columns(self, df, export_type):
        """按导出类型格式化 kernel 级 MFU 列名。"""
        try:
            if export_type == Constant.DB:
                column_mapping = {
                    'rank_id': 'rankID',
                    'op_name': 'opName',
                    'kernel_name': 'kernelName',
                    'kernel_ts': 'kernelStart(ns)',
                    'kernel_end': 'kernelEnd(ns)',
                    'kernel_duration': 'kernelDuration(ns)',
                    'mfu': 'mfu'
                }
            elif export_type == Constant.TEXT:
                column_mapping = {
                    'rank_id': 'Rank ID',
                    'op_name': 'Op Name',
                    'kernel_name': 'Kernel Name',
                    'kernel_ts': 'Kernel Start(ns)',
                    'kernel_end': 'Kernel End(ns)',
                    'kernel_duration': 'Kernel Duration(ns)',
                    'mfu': 'MFU'
                }
            else:
                return df

            return df.rename(columns=column_mapping)
        except Exception as e:
            logger.error(f"Failed to format kernel MFU columns, error: {e}")
            return pd.DataFrame()

    def _format_module_mfu_columns(self, df, export_type):
        """按导出类型格式化 module 级 MFU 列名。"""
        try:
            # 没有任何 MFU 信息时，不输出 avg_mfu 列。
            if 'avg_mfu' in df.columns:
                empty_mfu = df['avg_mfu'].isna().all() or df['avg_mfu'].eq('').all()
                if empty_mfu:
                    df = df.drop(columns=['avg_mfu'])

            if export_type == Constant.DB:
                column_mapping = {
                    'rank_id': 'rankID',
                    'module_parent': 'parentModule',
                    'op_name': 'opName',
                    'kernel_list': 'kernelList',
                    'op_count': 'opCount',
                    'total_kernel_duration': 'totalKernelDuration(ns)',
                    'avg_kernel_duration': 'avgKernelDuration(ns)',
                    'avg_mfu': 'avgMFU'
                }
            elif export_type == Constant.TEXT:
                column_mapping = {
                    'rank_id': 'Rank ID',
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
                return df

            return df.rename(columns=column_mapping)
        except Exception as e:
            logger.error(f"Failed to format module MFU columns, error: {e}")
            return pd.DataFrame()
