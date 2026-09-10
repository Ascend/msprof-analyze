# Copyright (c) 2026, Huawei Technologies Co., Ltd.
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

import math
import pandas as pd
from msprof_analyze.prof_common.logger import get_logger

logger = get_logger()


class ClusterCompareMetricsMixin:
    """
    集群对比分析指标计算工具类（Mixin）

    设计说明：
        本 Mixin 为纯计算工具类，不继承 BaseRecipeAnalysis。
        它提供独立的计算能力，可混入到任何需要这些计算功能的类中。

    组合约束：
        使用本 Mixin 的类需要满足以下条件：
        - 无需额外依赖，所有方法均为自包含
        - 调用方法时需自行保证传入的参数有效
        - 本 Mixin 不依赖 DB 访问、参数解析、输出目录管理等能力

    与 BaseRecipeAnalysis 的关系：
        本 Mixin 不依赖 BaseRecipeAnalysis，可独立使用。
        如需要文件输出和目录管理功能，应配合 BaseRecipeAnalysis 或 FileManager/PathManager 使用。
    """

    DATATYPE_BYTES = {"BFP16": 2, "FP16": 2, "FP32": 4, "INT32": 4, "INT64": 8}
    DEFAULT_ALPHA = 60e-6  # 60μs

    @staticmethod
    def _safe_divide(numerator, denominator, default=0):
        return default if denominator == 0 else numerator / denominator

    @staticmethod
    def _ns_to_ms(duration_ns):
        return duration_ns / (10 ** 6)

    @staticmethod
    def _linearity_ratio(linearity_df, step_id, parallel_type):
        if linearity_df is None or linearity_df.empty:
            return 0
        filtered = linearity_df[(linearity_df["stepId"] == step_id) &
                                (linearity_df["parallelType"] == parallel_type)]
        return filtered["ratioOfUnmaskedCommunication"].values[0] if not filtered.empty else 0

    def compare_by_parallel_type(self, current_df: pd.DataFrame, baseline_df: pd.DataFrame) -> pd.DataFrame:
        """按parallelType匹配，计算通信时间的差值"""
        if current_df is None or current_df.empty:
            logger.warning("current_df is empty!")
            return pd.DataFrame()
        if baseline_df is None or baseline_df.empty:
            logger.warning("baseline_df is empty!")
            return pd.DataFrame()

        merged = pd.merge(current_df, baseline_df, on="parallelType", how="outer", suffixes=("_current", "_baseline")).fillna(0)
        merged["diff"] = merged["totalTimeWithoutCommunicationBlackout_sum_current"] - merged["totalTimeWithoutCommunicationBlackout_sum_baseline"]
        diff_sum = merged["diff"].sum()
        merged["diff_percent"] = 0 if diff_sum == 0 else (merged["diff"] / diff_sum) * 100
        merged["diff_percent"] = merged["diff_percent"].replace([float('inf'), -float('inf')], 0).fillna(0)

        return merged[["parallelType", "totalTimeWithoutCommunicationBlackout_sum_current",
                      "totalTimeWithoutCommunicationBlackout_sum_baseline", "diff", "diff_percent"]]

    def comm_lower_bound(self, count, T0, K0=64, K=128, B=200 * 1024 ** 3 / 8 * 0.8,
                         datatype="BFP16", op_type="allGather", alpha=None):
        """
        计算 allGather / reduceScatter / allReduce 理论下界

        Args:
            count: 数据元素数量
            T0: 基线时间（毫秒）
            K0: 基线规模，默认为 64
            K: 目标规模，默认为 128
            B: 带宽（字节/秒），默认 20GB/s * 0.8
            datatype: 数据类型，支持 BFP16/FP16/FP32/INT32/INT64
            op_type: 通信操作类型，支持 allGather / reduceScatter / allReduce
            alpha: 网络延迟（秒），默认使用类常量 DEFAULT_ALPHA (60μs)
                   不同硬件参考值：
                   - NVLink: ~100ns (1e-7)
                   - HCCS: ~200ns (2e-7)
                   - RoCE: ~10-50μs (1e-5 ~ 5e-5)
        """
        if alpha is None:
            alpha = self.DEFAULT_ALPHA
        if T0 == 0:
            return {"T_total_ms": 0, "T_L3_ms": 0.0, "ratio": 0}
        if K0 == 0 or B == 0:
            raise ValueError("K0 and B must not be 0.")

        bytes_per_elem = self.DATATYPE_BYTES.get(datatype, 2)
        r = K / K0
        if r <= 1:
            return {"T_total_ms": T0, "T_L3_ms": 0.0, "ratio": 1.0}

        m = count * bytes_per_elem
        M3 = math.ceil(math.log2(r))

        if op_type in ("allGather", "reduceScatter"):
            T_L3_ms = (alpha * M3 + (m / B) * (r - 1)) * 1000
        elif op_type == "allReduce":
            T_L3_ms = (2 * alpha * M3 + 2 * (m / B) * (r - 1)) * 1000
        else:
            # 修复风格问题：错误消息添加空格，并包含所有支持的 op_type
            raise ValueError(f"Unknown op_type: {op_type}, expected 'allGather' | 'reduceScatter' | 'allReduce'")

        return {"T_total_ms": T0 + T_L3_ms, "T_L3_ms": T_L3_ms, "ratio": (T0 + T_L3_ms) / T0}

    def sum_by_columns(self, df: pd.DataFrame, group_cols: list, sum_col: str, step_id: int = None) -> pd.DataFrame:
        """按指定列分组求和"""
        if df is None or df.empty:
            return pd.DataFrame()
        filtered_df = df.copy()
        if step_id is not None:
            filtered_df = filtered_df[filtered_df['stepId'] == step_id]
        if filtered_df.empty:
            return pd.DataFrame()
        result = filtered_df.groupby(group_cols)[sum_col].sum().reset_index()
        result = result.rename(columns={sum_col: f'{sum_col}_sum'})
        return result
