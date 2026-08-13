# Copyright (c) 2026, Huawei Technologies Co., Ltd.
# All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
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
from tqdm import tqdm

from msprof_analyze.prof_common.constant import Constant
from msprof_analyze.prof_common.database_service import DatabaseService
from msprof_analyze.prof_common.logger import get_logger
from msprof_analyze.cluster_analyse.common_func.time_range_calculator import RangeCaculator
from msprof_analyze.prof_exports.computational_op_masking_export import CommunicationOpWithExport
from msprof_analyze.prof_exports.computational_op_masking_export import ComputeTaskInfoWithExport

logger = get_logger()


class LinearityUtils:
    """线性度计算工具类"""

    # 保持原有常量名以兼容外部引用
    COMPUTATIONAL_OPERATOR_LINEARITY_COLUMNS = [
        "stepId",
        "parallelType",
        "stepStartTime",
        "stepEndTime",
        "totalCommunicationOperatorTime",
        "timeRatioOfStepCommunicationOperator",
        "totalTimeWithoutCommunicationBlackout",
        "ratioOfUnmaskedCommunication",
    ]
    EPSILON = 1e-15  # 除零保护阈值

    @staticmethod
    def safe_divide(a, b):
        """安全除法，使用 EPSILON 防止除零"""
        return a / b if abs(b) > LinearityUtils.EPSILON else 0.0

    @staticmethod
    def _filter_by_time(df, start_col, end_col, start, end):
        """按时间范围过滤DataFrame"""
        return df[(df[end_col] > start) & (df[start_col] < end)]

    @staticmethod
    def _to_ranges(df, start_col, end_col):
        """转换为TimeRange对象列表"""
        return [RangeCaculator.generate_time_range(row[start_col], row[end_col]) for _, row in df.iterrows()]

    @staticmethod
    def _calc_comm_time(ranges, use_merge):
        """计算通信时间"""
        if use_merge:
            merged = RangeCaculator.merge_continuous_intervals(ranges)
            return sum(r.end_ts - r.start_ts for r in merged)
        return sum(r.end_ts - r.start_ts for r in ranges)

    @staticmethod
    def calculate_linearity_for_parallel_type(
        step_df, comm_df, comp_df, parallel_type, parallel_col_name="parallelType", use_merge=False
    ):
        """计算单个并行类型的线性度"""
        result = []

        # 过滤当前并行类型的通信数据
        filtered_comm = comm_df[comm_df[parallel_col_name].isin(parallel_type)]
        if filtered_comm.empty:
            return result

        # 过滤当前并行类型的计算数据
        filtered_comp = comp_df[comp_df[parallel_col_name].isin(parallel_type)]

        for _, step in step_df.iterrows():
            start, end = step["startNs"], step["endNs"]
            if end <= start:
                continue

            # 获取时间范围内的数据
            comm_in_step = LinearityUtils._filter_by_time(filtered_comm, "startNs", "endNs", start, end)
            comp_in_step = LinearityUtils._filter_by_time(filtered_comp, "task_start_time", "task_end_time", start, end)

            # 转换为时间范围对象
            comm_ranges = LinearityUtils._to_ranges(comm_in_step, "startNs", "endNs")
            comp_ranges = LinearityUtils._to_ranges(comp_in_step, "task_start_time", "task_end_time")

            # 计算各项指标
            total_comm = LinearityUtils._calc_comm_time(comm_ranges, use_merge)
            step_duration = end - start
            ratio_comm = LinearityUtils.safe_divide(total_comm, step_duration)

            uncovered = RangeCaculator.compute_uncovered_durations(comm_ranges, comp_ranges)
            total_uncovered = sum(uncovered)
            ratio_uncovered = round(LinearityUtils.safe_divide(total_uncovered, step_duration), 5)

            result.append(
                [
                    step.get("id", 0),
                    "+".join(parallel_type),
                    start,
                    end,
                    total_comm,
                    ratio_comm,
                    total_uncovered,
                    ratio_uncovered,
                ]
            )

        return result

    @staticmethod
    def _get_dataframe(data_map, analysis_class, step_columns):
        """获取并验证所有必要的数据"""
        db_path = data_map.get(Constant.PROFILER_DB_PATH)
        step_range = data_map.get(Constant.STEP_RANGE)

        # 获取step数据
        data_service = DatabaseService(db_path, step_range)
        data_service.add_table_for_query(Constant.TABLE_STEP_TIME, step_columns)
        step_df = data_service.query_data().get(Constant.TABLE_STEP_TIME)

        if step_df is None or step_df.empty:
            logger.warning("No step data in %s", db_path)
            return None, None, None

        # 验证必要列
        if not all(col in step_df.columns for col in ['startNs', 'endNs']):
            logger.warning("Step data missing required columns")
            return None, None, None

        # 确保id列存在
        if 'id' not in step_df.columns:
            step_df = step_df.copy()
            step_df['id'] = range(len(step_df))

        # 获取通信和计算数据
        comm_df = CommunicationOpWithExport(db_path, analysis_class, step_range).read_export_db()
        if comm_df is None or comm_df.empty:
            logger.warning("No communication data in %s", db_path)
            return None, None, None

        comp_df = ComputeTaskInfoWithExport(db_path, analysis_class, step_range).read_export_db()
        if comp_df is None or comp_df.empty:
            logger.warning("No computation data in %s", db_path)
            return None, None, None

        return step_df, comm_df, comp_df

    @staticmethod
    def compute_linearity_df(
        data_map,
        analysis_class,
        parallel_types,
        step_columns,
        parallel_col_name="parallelType",
        target_step_id=None,
        use_merge=False,
    ):
        """计算线性度（主入口）"""
        # 获取数据
        step_df, comm_df, comp_df = LinearityUtils._get_dataframe(data_map, analysis_class, step_columns)
        if step_df is None:
            return pd.DataFrame()

        # 过滤目标step
        if target_step_id is not None:
            step_df = step_df[step_df['id'] == target_step_id]
            if step_df.empty:
                logger.warning("No step found with id: %s", target_step_id)
                return pd.DataFrame()

        # 计算所有并行类型
        results = []
        for parallel_type in tqdm(parallel_types, desc="Computing operator parallelization masking"):
            results.extend(
                LinearityUtils.calculate_linearity_for_parallel_type(
                    step_df, comm_df, comp_df, parallel_type, parallel_col_name, use_merge
                )
            )

        if not results:
            return pd.DataFrame()

        return pd.DataFrame(results, columns=LinearityUtils.COMPUTATIONAL_OPERATOR_LINEARITY_COLUMNS)
