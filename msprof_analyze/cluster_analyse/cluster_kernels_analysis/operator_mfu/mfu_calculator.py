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

from msprof_analyze.cluster_analyse.cluster_kernels_analysis.operator_mfu.chip_peak_flops import ChipPeakFLOPSCalculator
from msprof_analyze.cluster_analyse.cluster_kernels_analysis.operator_mfu.operator_flops import DataType, OperatorFLOPs
from msprof_analyze.prof_exports.mfu_export import KernelShapeExport, MfuFlopsExport
from msprof_analyze.prof_exports.module_statistic_export import FrameworkOpToKernelExport
from msprof_analyze.cluster_analyse.common_func.utils import ensure_numeric_columns
from msprof_analyze.cluster_analyse.common_func.table_constant import TableConstant
from msprof_analyze.prof_common.db_manager import DBManager
from msprof_analyze.prof_common.constant import Constant
from msprof_analyze.prof_common.logger import get_logger


logger = get_logger()


class MFUCalculator:
    def __init__(self, data_map):
        self.profiler_db_path = data_map.get(Constant.PROFILER_DB_PATH)
        self.profiler_path = data_map.get(Constant.PROFILING_PATH)
        self.chip_peak_manager = ChipPeakFLOPSCalculator(self.profiler_path)
        self.op_kernel_df = None  # cpu-op与下发的device-kernel的关联关系
        self.shapes_df = None

    def run(self):
        logger.info("Start MFU calculation.")
        logger.debug("profiler_db_path=%s", self.profiler_db_path)
        logger.debug("profiler_path=%s", self.profiler_path)
        if not self.chip_peak_manager.is_valid():
            logger.error("Can not get chip info. Skip MFU calculation.")
            return pd.DataFrame()
        if not self._query_kernel_shapes():
            logger.error("Query Kernel Shapes Failed. Skip MFU calculation.")
            return pd.DataFrame()
        logger.debug("Kernel shapes queried: %s rows", len(self.shapes_df))

        mfu_flops_df = self._query_mfu_flops()
        if mfu_flops_df is not None and not mfu_flops_df.empty:
            logger.debug("Using MFU data from mstx ranges: %s FLOPs records", len(mfu_flops_df))
            mfu = self._calculate_mfu_from_recorded_flops(mfu_flops_df)
        else:
            logger.warning("No mfu_flops ranges found. Skip MFU calculation.")
            mfu = pd.DataFrame()

        logger.info("MFU calculation finished, result rows: %s", len(mfu))
        return mfu

    def _calculate_mfu_from_recorded_flops(self, mfu_flops_df):
        """根据 mstx range 中记录的 FLOPs 计算 kernel 级 MFU。"""
        logger.debug("Calculate MFU from %s FLOPs records", len(mfu_flops_df))
        if self.op_kernel_df is None and not self._query_op_kernel_correlation():
            logger.warning("Can not get cpu-op to device-kernel correlation. Skip MFU calculation.")
            return pd.DataFrame()

        # range 消息格式为 "<FLOPs>-<算子名>"，格式不合法或 FLOPs 非正数的数据不参与计算。
        mfu_flops_df = ensure_numeric_columns(mfu_flops_df, ['startNs', 'endNs'])
        split_result = mfu_flops_df['flops'].astype(str).str.extract(r'^(?P<flops>\d+)-(?P<name>.+)$')
        mfu_flops_df['flops'] = pd.to_numeric(split_result['flops'], errors='coerce')
        mfu_flops_df['name'] = split_result['name']

        mfu_flops_df = mfu_flops_df.dropna(subset=['flops'])
        mfu_flops_df = mfu_flops_df[mfu_flops_df['flops'] > 0]
        logger.debug("Valid FLOPs records after filtering: %s", len(mfu_flops_df))

        if mfu_flops_df.empty:
            logger.warning("No valid flops values found in mfu_flops ranges.")
            return pd.DataFrame()

        df = pd.merge(self.op_kernel_df, self.shapes_df, on=['kernel_name', 'kernel_ts', 'kernel_end'], how='inner')
        if df.empty:
            return pd.DataFrame()
        for column_name in ['input_shapes', 'output_shapes']:
            if column_name not in df.columns:
                df[column_name] = ''
        df = ensure_numeric_columns(df, ['op_ts', 'task_duration'])
        df = df.dropna(subset=['op_ts']).sort_values(['op_ts', 'kernel_ts', 'kernel_end']).reset_index(drop=True)
        if df.empty:
            return pd.DataFrame()
        op_ts_values = df['op_ts'].to_numpy()

        result_frames = []
        for range_row in mfu_flops_df.itertuples(index=False):
            range_start = range_row.startNs
            range_end = range_row.endNs
            flops = range_row.flops
            name = range_row.name

            if pd.isna(range_start) or pd.isna(range_end) or range_end <= range_start:
                continue

            # 通过已排序的 op_ts 查找边界，避免每个 FLOPs range 全量扫描 kernel 关联数据。
            start_index = op_ts_values.searchsorted(range_start, side='left')
            end_index = op_ts_values.searchsorted(range_end, side='right')
            range_kernels = df.iloc[start_index:end_index]
            if range_kernels.empty:
                continue

            # 多表关联可能返回重复 kernel，计算前按时间范围去重。
            range_kernels = range_kernels.drop_duplicates(subset=['kernel_ts', 'kernel_end'])

            total_duration = range_kernels['task_duration'].sum()
            if total_duration <= 0 or flops <= 0:
                continue

            # 同一 range 下的 kernel 属于同一算子，使用首个 kernel 的输入类型获取芯片理论峰值。
            dtype = self._determine_dtype_from_input_types(range_kernels.iloc[0].get('input_types', ''))
            chip_peak = self._get_peak_performance(dtype)
            if chip_peak == Constant.INVALID_RETURN:
                continue

            range_kernels = range_kernels[range_kernels['task_duration'] > 0].copy()
            if range_kernels.empty:
                continue

            kernel_duration = range_kernels['task_duration']
            range_kernels['mfu'] = flops / (kernel_duration * 1e-9) / chip_peak
            range_kernels['flops_op_name'] = name
            range_kernels['flops'] = flops
            range_kernels['kernel_duration'] = kernel_duration
            range_kernels['chip_peak'] = chip_peak
            # 实际 TFLOPS 与 MFU 均按 kernel 执行时长计算。
            range_kernels['actual_tflops'] = (flops / (kernel_duration * 1e-9) / 1e12).round(2)
            result_frames.append(
                range_kernels[
                    [
                        'kernel_name',
                        'kernel_ts',
                        'kernel_end',
                        'mfu',
                        'flops_op_name',
                        'flops',
                        'kernel_duration',
                        'chip_peak',
                        'actual_tflops',
                        'input_shapes',
                        'output_shapes',
                    ]
                ]
            )

        if not result_frames:
            return pd.DataFrame()

        return pd.concat(result_frames, ignore_index=True)

    def _determine_dtype_from_input_types(self, input_types_str: str):
        """从 kernel 输入类型中提取用于计算芯片峰值的数据类型。"""
        if not isinstance(input_types_str, str) or not input_types_str:
            return DataType.FLOAT16

        type_list = [t.strip().upper() for t in input_types_str.split(';') if t.strip()]
        if type_list:
            return OperatorFLOPs.format_data_type(type_list[0])
        return DataType.FLOAT16

    def _query_kernel_shapes(self):
        export = KernelShapeExport(self.profiler_db_path, "")
        shapes_df = export.read_export_db()
        if shapes_df is None or shapes_df.empty:
            return False
        shapes_df['input_shapes'] = shapes_df['input_shapes'].str.strip('"\'')
        shapes_df['output_shapes'] = shapes_df['output_shapes'].str.strip('"\'')
        self.shapes_df = shapes_df[
            (shapes_df['input_shapes'] != Constant.NA) & (shapes_df['output_shapes'] != Constant.NA)
        ]
        return True

    def _query_op_kernel_correlation(self):
        export = FrameworkOpToKernelExport(self.profiler_db_path, "", table_name=TableConstant.TABLE_COMPUTE_TASK_INFO)
        op_kernel_df = export.read_export_db()
        if op_kernel_df is None or op_kernel_df.empty:
            self.op_kernel_df = pd.DataFrame()
            return False
        op_kernel_df = ensure_numeric_columns(op_kernel_df, ['kernel_ts', 'kernel_end', 'op_ts', 'op_end'])
        self.op_kernel_df = op_kernel_df
        return True

    def _query_mfu_flops(self):
        """查询 mstx range 中记录的算子 FLOPs。"""
        logger.debug("Query MFU FLOPs data from DB")
        if not DBManager.check_tables_in_db(self.profiler_db_path, TableConstant.TABLE_MSTX_EVENTS):
            logger.debug("MSTX_EVENTS table not found in DB")
            return None
        export = MfuFlopsExport(self.profiler_db_path, "")
        flops_df = export.read_export_db()
        if flops_df is None or flops_df.empty:
            logger.debug("No MFU FLOPs data found in DB")
            return None
        logger.debug("MFU FLOPs data queried: %s rows", len(flops_df))
        return ensure_numeric_columns(flops_df, ['startNs', 'endNs'])

    def _get_peak_performance(self, dtype) -> float:
        """获取芯片理论计算峰值。"""
        return self.chip_peak_manager.get_peak_performance(dtype)
