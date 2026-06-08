# pylint: disable=duplicate-code
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
import pandas as pd
import numpy as np

from msprof_analyze.cluster_analyse.cluster_kernels_analysis.operator_mfu.mfu_calculator import MFUCalculator
from msprof_analyze.cluster_analyse.recipes.module_statistic.module_statistic import ModuleStatistic
from msprof_analyze.cluster_analyse.common_func.excel_utils import ExcelUtils
from msprof_analyze.prof_exports.module_statistic_export import ModuleMstxRangeExport
from msprof_analyze.cluster_analyse.common_func.utils import ensure_numeric_columns
from msprof_analyze.prof_common.constant import Constant
from msprof_analyze.prof_common.logger import get_logger

logger = get_logger()


class OperatorMfu(ModuleStatistic):
    """生成 kernel 级 MFU 明细和 module 级 MFU 统计结果。"""

    TABLE_OPERATOR_MFU = "OperatorMFU"
    TABLE_MODULE_MFU = "ModuleMFU"

    @property
    def base_dir(self):
        """返回当前分析任务目录名。"""
        return os.path.basename(os.path.dirname(__file__))

    def run(self, context, save=True):
        """执行算子 MFU 分析，并按导出类型保存结果。"""
        if self._export_type not in (Constant.DB, Constant.TEXT):
            logger.error(
                "Invalid export type: %s for operator mfu analysis, required to be %s or %s",
                self._export_type,
                Constant.DB,
                Constant.TEXT,
            )
            return None
        mapper_res = self.mapper_func(context)
        if not save:
            valid_res = [
                (rank, kernel_df, module_df)
                for rank, kernel_df, module_df in mapper_res
                if ((kernel_df is not None and not kernel_df.empty) or (module_df is not None and not module_df.empty))
            ]
            return valid_res
        if self._export_type == Constant.DB:
            kernel_mfu_df, module_mfu_df = self.reducer_func(mapper_res)
            self.save_db(kernel_mfu_df, module_mfu_df)
        elif self._export_type == Constant.TEXT:
            self.save_excel(mapper_res)
        return None

    def _mapper_func(self, data_map, analysis_class):
        """生成单个 rank 的 kernel 级和 module 级 MFU 结果。"""
        profiler_db_path = data_map.get(Constant.PROFILER_DB_PATH)
        rank_id = data_map.get(Constant.RANK_ID)

        # 查询 module 和 kernel 数据。
        module_df, kernel_df = self._query_all_data(profiler_db_path, rank_id)

        # kernel 数据是计算 MFU 的必要输入，缺失时当前 rank 无法继续分析。
        if kernel_df is None or kernel_df.empty:
            logger.error("No kernel data found for rank %s", rank_id)
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
                module_mfu_df = self._generate_module_mfu_stats(root, rank_id, kernel_df)
            else:
                logger.warning("Failed to build event tree for rank %s, skipping module MFU stats", rank_id)
        else:
            logger.debug("No module data found for rank %s, only kernel-level MFU will be generated", rank_id)

        return rank_id, kernel_mfu_df, module_mfu_df

    def _query_all_data(self, profiler_db_path, rank_id):
        """查询单个 rank 的 module 数据和 kernel 数据。"""
        # module 数据用于生成聚合统计，缺失时仍可输出 kernel 级明细。
        module_export = ModuleMstxRangeExport(profiler_db_path, self._recipe_name)
        module_df = module_export.read_export_db()
        if module_df is None or module_df.empty:
            logger.debug("No mstx range event (module data) found from rank %s", rank_id)
            module_df = pd.DataFrame()
        else:
            module_df = ensure_numeric_columns(module_df, ['startNs', 'endNs'])

        # kernel 数据用于计算 MFU，是必要输入。
        kernel_df = self._query_framework_op_to_kernel(profiler_db_path)
        if kernel_df is None or kernel_df.empty:
            logger.error("Can not export framework op to kernel mapper from rank %s", rank_id)
            return None, None

        kernel_df = ensure_numeric_columns(kernel_df, ['kernel_ts', 'kernel_end', 'op_ts', 'op_end'])

        return module_df, kernel_df

    def _calculate_kernel_mfu(self, data_map, op_kernel_df):
        """计算 kernel MFU，并合并回 op 与 kernel 的关联数据。"""
        mfu_worker = MFUCalculator(data_map)
        mfu_df = mfu_worker.run()
        if mfu_df.empty or 'mfu' not in mfu_df.columns:
            logger.warning("No MFU calculated for kernels.")
            op_kernel_df['mfu'] = -1.0
            return op_kernel_df
        else:
            op_kernel_df = pd.merge(op_kernel_df, mfu_df, on=['kernel_name', 'kernel_ts', 'kernel_end'], how='left')
            op_kernel_df['mfu'] = op_kernel_df['mfu'].fillna(-1.0)
            return op_kernel_df

    def _generate_kernel_mfu_list(self, kernel_df, rank_id):
        """生成 kernel 级 MFU 明细。"""
        if kernel_df is None or kernel_df.empty:
            return pd.DataFrame()

        # -1 表示当前 kernel 未计算出有效 MFU，不写入明细。
        valid_kernel_df = kernel_df[kernel_df.get('mfu', -1) != -1.0].copy()
        if valid_kernel_df.empty:
            logger.warning("No valid MFU data for rank %s", rank_id)
            return pd.DataFrame()

        valid_kernel_df = valid_kernel_df.reset_index(drop=True)
        row_count = len(valid_kernel_df)

        def get_column(column_name, default_value):
            if column_name in valid_kernel_df.columns:
                return valid_kernel_df[column_name]
            return pd.Series([default_value] * row_count)

        kernel_ts = pd.to_numeric(get_column('kernel_ts', 0), errors='coerce').fillna(0)
        kernel_end = pd.to_numeric(get_column('kernel_end', 0), errors='coerce').fillna(0)
        fallback_duration = kernel_end - kernel_ts
        kernel_duration = pd.to_numeric(get_column('kernel_duration', pd.NA), errors='coerce').fillna(fallback_duration)

        chip_peak = pd.to_numeric(get_column('chip_peak', 0), errors='coerce').fillna(0)
        chip_peak_tflops = (chip_peak.where(chip_peak > 0, 0) / 1e12).round(2)
        mfu = pd.to_numeric(get_column('mfu', 0), errors='coerce').fillna(0).round(4)

        actual_tflops = pd.to_numeric(get_column('actual_tflops', pd.NA), errors='coerce')
        actual_tflops = actual_tflops.fillna((mfu * chip_peak_tflops).round(2))

        return pd.DataFrame(
            {
                'rank_id': rank_id,
                'op_name': get_column('op_name', ''),
                'kernel_name': get_column('kernel_name', ''),
                'kernel_ts': kernel_ts,
                'kernel_end': kernel_end,
                'kernel_duration': kernel_duration,
                'mfu': mfu,
                'actual_tflops': actual_tflops,
                'chip_peak_tflops': chip_peak_tflops,
                'flops': get_column('flops', 0),
                'flops_op_name': get_column('flops_op_name', ''),
                'input_shapes': get_column('input_shapes', ''),
                'output_shapes': get_column('output_shapes', ''),
            }
        )

    def _generate_module_mfu_stats(self, root_node, rank_id, kernel_df):
        """生成 module 级 MFU 统计。"""
        verbose_df = self._flatten_tree_to_dataframe(root_node)
        if verbose_df.empty:
            return pd.DataFrame()

        op_mfu_map = {}
        for (op_name, op_ts, op_end), group in kernel_df.groupby(['op_name', 'op_ts', 'op_end'], sort=False):
            op_mfu_map[(op_name, op_ts, op_end)] = group['mfu'].tolist() if 'mfu' in group else [-1.0] * len(group)
        verbose_df['mfu_list'] = verbose_df.apply(
            lambda row: op_mfu_map.get((row['op_name'], row['op_start'], row['op_end']), []),
            axis=1,
        )
        verbose_df.insert(0, 'rank_id', rank_id)
        return self._aggregate_module_mfu_stats(verbose_df)

    def _aggregate_module_mfu_stats(self, df):
        """聚合 module 级 MFU 统计。"""
        if df is None or df.empty:
            logger.warning("Empty dataframe received for aggregation")
            return pd.DataFrame()

        # 为每个算子添加在 module 下的顺序位置。
        distinct_module_columns = ['rank_id', 'module_parent', 'module', 'module_start', 'module_end']
        df['op_order'] = df.groupby(distinct_module_columns).cumcount()

        # 创建 seq_key 保证唯一性，并分配 ID。
        op_seq = df.groupby(distinct_module_columns)['op_name'].transform('/'.join)
        df['seq_id'] = pd.factorize(op_seq)[0]

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
                avg_mfu=('mfu_list', compute_mfu_avg),
            )
            .reset_index()
        )

        # 区分名称相同但实际算子序列不同的连续 module。
        stat_df = self._distinguish_contiguous_module(stat_df)

        # 根据算子执行顺序排序，删除后续不再使用的列。
        stat_df = (
            stat_df.sort_values(by=['op_start', 'op_order'])
            .drop(columns=['module_start', 'module_end', 'seq_id', 'op_order', 'op_start'])
            .reset_index(drop=True)
        )

        return stat_df

    def _distinguish_contiguous_module(self, stat_df):
        """区分名称相同但算子序列不同的连续 module。"""
        distinguish_contiguous_module = super()._distinguish_contiguous_module
        rank_dfs = [distinguish_contiguous_module(rank_df) for _, rank_df in stat_df.groupby('rank_id')]
        return pd.concat(rank_dfs, ignore_index=True)

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

    def save_db(self, kernel_mfu_df, module_mfu_df):  # pylint: disable=arguments-differ
        """将分析结果写入数据库。"""
        if kernel_mfu_df is not None and not kernel_mfu_df.empty:
            kernel_mfu_df = self._format_kernel_mfu_columns(kernel_mfu_df, Constant.DB)
            self.dump_data(
                kernel_mfu_df, Constant.DB_CLUSTER_COMMUNICATION_ANALYZER, self.TABLE_OPERATOR_MFU, index=False
            )

        if module_mfu_df is not None and not module_mfu_df.empty:
            module_mfu_df = self._format_module_mfu_columns(module_mfu_df, Constant.DB)
            self.dump_data(
                module_mfu_df, Constant.DB_CLUSTER_COMMUNICATION_ANALYZER, self.TABLE_MODULE_MFU, index=False
            )

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
                    excel_utils.set_column_width(
                        {"Kernel Name": 50, "Op Name": 40, "MFU": 10, "Kernel Duration(ns)": 15}
                    )
                    excel_utils.save_and_close()
                    excel_utils.clear()
                except Exception as e:
                    logger.error("Save kernel MFU excel failed, err: %s", e)

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
                    "Avg MFU": 10,
                }
                try:
                    excel_utils.create_excel_writer(self.output_path, file_name, module_df)
                    excel_utils.merge_duplicate_cells(columns_to_merge)
                    excel_utils.set_column_width(column_width_config)
                    excel_utils.set_row_height(0, 27)
                    excel_utils.save_and_close()
                    excel_utils.clear()
                except Exception as e:
                    logger.error("Save module MFU excel failed, err: %s", e)

    def _format_kernel_mfu_columns(self, df, export_type):
        """按导出类型格式化 kernel 级 MFU 列名。"""
        try:
            if export_type == Constant.DB:
                column_mapping = {
                    'rank_id': 'rank_id',
                    'op_name': 'op_name',
                    'kernel_name': 'kernel_name',
                    'kernel_ts': 'kernel_start(ns)',
                    'kernel_end': 'kernel_end(ns)',
                    'kernel_duration': 'kernel_duration(ns)',
                    'mfu': 'mfu',
                }
            elif export_type == Constant.TEXT:
                column_mapping = {
                    'rank_id': 'Rank ID',
                    'op_name': 'Op Name',
                    'kernel_name': 'Kernel Name',
                    'kernel_ts': 'Kernel Start(ns)',
                    'kernel_end': 'Kernel End(ns)',
                    'kernel_duration': 'Kernel Duration(ns)',
                    'mfu': 'MFU',
                }
            else:
                return df

            return df.rename(columns=column_mapping)
        except Exception as e:
            logger.error("Failed to format kernel MFU columns, error: %s", e)
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
                    'rank_id': 'rank_id',
                    'module_parent': 'parent_module',
                    'module': 'module',
                    'op_name': 'op_name',
                    'kernel_list': 'kernel_list',
                    'op_count': 'op_count',
                    'total_kernel_duration': 'total_kernel_duration(ns)',
                    'avg_kernel_duration': 'avg_kernel_duration(ns)',
                    'avg_mfu': 'avg_mfu',
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
                    'avg_mfu': 'Avg MFU',
                }
            else:
                return df

            return df.rename(columns=column_mapping)
        except Exception as e:
            logger.error("Failed to format module MFU columns, error: %s", e)
            return pd.DataFrame()
