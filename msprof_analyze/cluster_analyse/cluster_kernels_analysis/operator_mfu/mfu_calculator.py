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
from msprof_analyze.cluster_analyse.cluster_kernels_analysis.operator_mfu.operator_flops import (OperatorType,
                                                                                                 FLOPsStrategyFactory,
                                                                                                 OP_TYPE_MAP)
from msprof_analyze.prof_exports.mfu_export import OperatorArgsExport, KernelShapeExport
from msprof_analyze.prof_exports.module_statistic_export import FrameworkOpToKernelExport
from msprof_analyze.cluster_analyse.common_func.utils import ensure_numeric_columns
from msprof_analyze.cluster_analyse.common_func.table_constant import TableConstant
from msprof_analyze.prof_common.db_manager import DBManager
from msprof_analyze.prof_common.constant import Constant
from msprof_analyze.prof_common.logger import get_logger


logger = get_logger()


class MFUCalculator:
    UNIT_MS_TO_NS = 1000000

    def __init__(self, data_map, op_kernel_df=None):
        self.profiler_db_path = data_map.get(Constant.PROFILER_DB_PATH)
        self.profiler_path = data_map.get(Constant.PROFILING_PATH)
        self.chip_peak_manager = ChipPeakFLOPSCalculator(self.profiler_path)
        self.op_kernel_df = op_kernel_df  # cpu-op与下发的device-kernel的关联关系
        self.shapes_df = None

    def run(self):
        logger.info("Start MFU calculation.")
        if not self.chip_peak_manager.is_valid():
            logger.error("Can not get chip info. Skip MFU calculation.")
            return pd.DataFrame()
        if not self._query_kernel_shapes():
            logger.error("Query Kernel Shapes Failed. Skip MFU calculation.")
            return pd.DataFrame()

        matmul_mfu = self.process_common_operator(OperatorType.MATMUL)
        fa_mfu = self.process_operator_with_additional_args_mark(OperatorType.FLASH_ATTENTION, 'flash_attn_args')
        mfu = pd.concat([matmul_mfu, fa_mfu], ignore_index=True)
        logger.info(f"MFU calculation finished")
        return mfu

    def process_common_operator(self, op_type: OperatorType):
        kernel_types = OP_TYPE_MAP.get(op_type)
        filter_df = self.shapes_df[self.shapes_df['type'].isin(kernel_types)]
        mfu_df = self._calculate_mfu(filter_df, op_type)
        return mfu_df.filter(['kernel_name', 'kernel_ts', 'kernel_end', 'mfu'])

    def process_operator_with_additional_args_mark(self, op_type: OperatorType, args_domain: str):
        if self.op_kernel_df is None and not self._query_op_kernel_correlation():
            logger.warning(f"Can not get cpu-op to device-kernel correlation. Skip {op_type.name} mfu calculation.")
            return pd.DataFrame()

        kernel_types = OP_TYPE_MAP.get(op_type)
        filter_df = self.shapes_df[self.shapes_df['type'].isin(kernel_types)]
        if filter_df.empty:
            return pd.DataFrame()
        df = pd.merge(self.op_kernel_df, filter_df, on=['kernel_name', 'kernel_ts', 'kernel_end'], how='inner')

        op_args_df = self._query_operator_args(args_domain=args_domain)
        if op_args_df.empty:
            logger.warning(f"Can not get {args_domain} mstx mark. Skip {op_type.name} mfu calculation.")
            return pd.DataFrame()

        # 将op_args标记与其时间上最近的cpu-op关联
        # 规则：每个op_args匹配第一个时间在其后的cpu-op，每个cpu-op只匹配时间最接近的op_args
        matched_df = pd.merge_asof(
            left=op_args_df,
            right=df,
            left_on='startNs',
            right_on='op_ts',
            direction='forward',
            tolerance=3 * self.UNIT_MS_TO_NS
        )
        matched_df = matched_df.sort_values('startNs')
        matched_df = matched_df[matched_df['kernel_name'].notna()].copy()  # 移除无匹配项
        matched_df = matched_df.drop_duplicates(subset=['kernel_ts', 'kernel_end'], keep='last')  # 只保留时间最近的
        mfu_df = self._calculate_mfu(matched_df, op_type)
        return mfu_df.filter(['kernel_name', 'kernel_ts', 'kernel_end', 'mfu'])

    def _query_kernel_shapes(self):
        export = KernelShapeExport(self.profiler_db_path, "")
        shapes_df = export.read_export_db()
        if shapes_df is None or shapes_df.empty:
            return False
        shapes_df['input_shapes'] = shapes_df['input_shapes'].str.strip('\"\'')
        shapes_df['output_shapes'] = shapes_df['output_shapes'].str.strip('\"\'')
        self.shapes_df = shapes_df[(shapes_df['input_shapes'] != Constant.NA) &
                                   (shapes_df['output_shapes'] != Constant.NA)]
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

    def _query_operator_args(self, args_domain):
        if not DBManager.check_tables_in_db(self.profiler_db_path, TableConstant.TABLE_MSTX_EVENTS):
            return pd.DataFrame()
        args_export = OperatorArgsExport(self.profiler_db_path, "", {"op_args_domain": args_domain})
        op_args_df = args_export.read_export_db()
        if op_args_df is None or op_args_df.empty:
            return pd.DataFrame()
        op_args_df = ensure_numeric_columns(op_args_df, ['startNs'])
        return op_args_df

    def _get_peak_performance(self, dtype) -> float:
        """获取芯片理论计算峰值"""
        return self.chip_peak_manager.get_peak_performance(dtype)

    def _calculate_mfu(self, kernel_df, operator_type):
        mfu_df = kernel_df.copy()
        mfu_df['mfu'] = -1.0
        strategy_class = FLOPsStrategyFactory.get_strategy(operator_type)
        related_columns = strategy_class.RELATED_COLUMNS
        for group_key, group in mfu_df.groupby(related_columns):
            input_kwargs = {key: val for key, val in zip(related_columns, group_key)}
            try:
                strategy = FLOPsStrategyFactory.create_strategy(operator_type, **input_kwargs)
                workload = strategy.calculate_flops()
                dtype = strategy.determine_data_type()

                chip_peak = self._get_peak_performance(dtype)
                if chip_peak == Constant.INVALID_RETURN or workload == Constant.INVALID_RETURN:
                    continue

                mask = mfu_df.loc[group.index, 'task_duration'] > 0
                valid_indices = group.index[mask]
                if len(valid_indices) > 0:
                    task_durations = mfu_df.loc[valid_indices, 'task_duration'].values
                    mfu_values = workload / (task_durations * 1e-9) / chip_peak  # 1e-9: ns to s
                    mfu_df.loc[valid_indices, 'mfu'] = mfu_values
            except Exception as err:
                logger.error(f"Calculate MFU for {operator_type} failed, err: {err}")
                continue

        return mfu_df

