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
    Cluster Compare Metrics Mixin

    提供集群对比分析中使用的指标计算工具方法。

    设计说明：
        本 Mixin 为纯计算工具类，不继承 BaseRecipeAnalysis。
        它提供独立的静态方法和实例方法，用于：
        1. 安全的数值除法 (_safe_divide)
        2. 时间单位转换 (_ns_to_ms)
        3. 线性度比率计算 (_linearity_ratio)
        4. 按 parallelType 的对比分析 (compare_by_parallel_type)
        5. 通信下界理论值计算 (comm_lower_bound)
        6. 按列分组求和 (sum_by_columns)

    组合约束：
        本 Mixin 设计为可混入到任何需要这些计算能力的类中，包括：
        - 继承 BaseRecipeAnalysis 的 Recipe 类
        - 其他 Mixin 类
        - 独立的工具类

        使用本 Mixin 的类无需额外依赖，所有方法均为自包含。

    与 BaseRecipeAnalysis 的关系：
        本 Mixin 不依赖 BaseRecipeAnalysis 的 DB 访问、参数解析、输出目录管理等能力。
        如需文件输出和目录管理，应配合 BaseRecipeAnalysis 或 FileManager/PathManager 使用。
    """

    # 数据类型字节映射（类级常量）
    DATATYPE_BYTES = {
        "BFP16": 2,
        "FP16": 2,
        "FP32": 4,
        "INT32": 4,
        "INT64": 8,
    }

    # 默认网络延迟参数（可被方法参数覆盖）
    DEFAULT_ALPHA = 60e-6  # 60μs

    @staticmethod
    def _safe_divide(numerator, denominator, default=0):
        """
        安全的除法运算，避免除零错误

        Args:
            numerator: 分子
            denominator: 分母
            default: 分母为0时的默认返回值

        Returns:
            除法结果或默认值
        """
        if denominator == 0:
            return default
        return numerator / denominator

    @staticmethod
    def _ns_to_ms(duration_ns):
        """
        纳秒转毫秒

        Args:
            duration_ns: 纳秒时间

        Returns:
            毫秒时间
        """
        return duration_ns / (10 ** 6)

    @staticmethod
    def _linearity_ratio(linearity_df, step_id, parallel_type):
        """
        获取线性度比率

        Args:
            linearity_df: 线性度数据 DataFrame
            step_id: 步骤 ID
            parallel_type: 并行类型

        Returns:
            线性度比率值，不存在时返回 0
        """
        if linearity_df is None or linearity_df.empty:
            return 0
        filtered = linearity_df[(linearity_df["stepId"] == step_id) & (linearity_df["parallelType"] == parallel_type)]
        if filtered.empty:
            return 0
        return filtered["ratioOfUnmaskedCommunication"].values[0]

    def compare_by_parallel_type(self, current_df: pd.DataFrame, baseline_df: pd.DataFrame) -> pd.DataFrame:
        """
        根据 parallelType 匹配，计算 totalCommunicationOperatorTime 的差值

        Args:
            current_df: 当前数据的DataFrame (已按parallelType 聚合)
            baseline_df: 基线数据的DataFrame (已按parallelType 聚合)

        Returns:
            包含 parallelType 和差值结果的DataFrame
        """
        if current_df is None or current_df.empty:
            logger.warning("current_df is empty!")
            return pd.DataFrame()

        if baseline_df is None or baseline_df.empty:
            logger.warning("baseline_df is empty!")
            return pd.DataFrame()

        merged = pd.merge(current_df, baseline_df, on="parallelType", how="outer", suffixes=("_current", "_baseline"))
        merged = merged.fillna(0)

        merged["diff"] = (
                merged["totalTimeWithoutCommunicationBlackout_sum_current"]
                - merged["totalTimeWithoutCommunicationBlackout_sum_baseline"]
        )
        diff_sum = merged["diff"].sum()
        merged["diff_percent"] = 0 if diff_sum == 0 else (merged["diff"] / diff_sum) * 100
        merged["diff_percent"] = merged["diff_percent"].replace([float('inf'), -float('inf')], 0).fillna(0)

        return merged[
            [
                "parallelType",
                "totalTimeWithoutCommunicationBlackout_sum_current",
                "totalTimeWithoutCommunicationBlackout_sum_baseline",
                "diff",
                "diff_percent",
            ]
        ]

    def comm_lower_bound(
            self,
            count,
            T0,
            K0=64,
            K=128,
            B=200 * 1024 ** 3 / 8 * 0.8,
            datatype="BFP16",
            op_type="allGather",
            alpha=None
    ):
        """
        allGather / reduceScatter / allReduce 理论下界（极简版）-- 所有扩展在亲和组外

        Args:
            count: 数据元素数量
            T0: 基线时间（毫秒）
            K0: 基线规模，默认为 64
            K: 目标规模，默认为 128
            B: 带宽（字节/秒），默认 20GB/s * 0.8
            datatype: 数据类型，支持 BFP16/FP16/FP32/INT32/INT64，默认 BFP16
            op_type: 通信操作类型，支持 allGather/reduceScatter/allReduce
            alpha: 网络延迟（秒），默认使用类常量 DEFAULT_ALPHA (60μs)
                   不同硬件参考值：
                   - NVLink: ~100ns (1e-7)
                   - HCCS: ~200ns (2e-7)
                   - RoCE: ~10-50μs (1e-5 ~ 5e-5)

        Returns:
            包含 T_total_ms（总时间毫秒）、T_L3_ms（L3延迟毫秒）、ratio（比率）的字典

        Raises:
            ValueError: 当 K0 或 B 为 0，或 op_type 不支持时抛出
        """
        # 使用传入的 alpha 或默认值
        if alpha is None:
            alpha = self.DEFAULT_ALPHA

        if T0 == 0:
            return {"T_total_ms": 0, "T_L3_ms": 0.0, "ratio": 0}
        if K0 == 0:
            raise ValueError("K0 must not be 0.")
        if B == 0:
            raise ValueError("B must not be 0.")

        # 使用类级常量，避免每次重建字典
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
            raise ValueError(f"Unknown op_type: {op_type}, expected 'allGather' | 'reduceScatter' | 'allReduce'")

        T_total = T0 + T_L3_ms

        return {"T_total_ms": T_total, "T_L3_ms": T_L3_ms, "ratio": T_total / T0}

    def sum_by_columns(self, df: pd.DataFrame, group_cols: list, sum_col: str, step_id: int = None) -> pd.DataFrame:
        """
        当多个指定列值相同时，对另一列的值进行求和

        Args:
            df: 输入 DataFrame
            group_cols: 分组列名列表
            sum_col: 要求和的列名
            step_id: 可选的步骤 ID 过滤

        Returns:
            分组求和后的 DataFrame
        """
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
