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
    @staticmethod
    def _safe_divide(numerator, denominator, default=0):
        if denominator == 0:
            return default
        return numerator / denominator

    @staticmethod
    def _ns_to_ms(duration_ns):
        return duration_ns / (10**6)

    @staticmethod
    def _linearity_ratio(linearity_df, step_id, parallel_type):
        if linearity_df is None or linearity_df.empty:
            return 0
        filtered = linearity_df[(linearity_df["stepId"] == step_id) & (linearity_df["parallelType"] == parallel_type)]
        if filtered.empty:
            return 0
        return filtered["ratioOfUnmaskedCommunication"].values[0]

    def compare_by_parallel_type(self, current_df: pd.DataFrame, baseline_df: pd.DataFrame) -> pd.DataFrame:
        """
        根据 parallelType 匹配， 计算 totalCommunicationOperatorTime 的差值
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
        self, count, T0, K0=64, K=128, B=200 * 1024**3 / 8 * 0.8, datatype="BFP16", op_type="allGather"
    ):
        """
        allGather / reduceScatter / allReduce 理论下界（极简版）-- 所有扩展在亲和组外
        """
        alpha = 60e-6
        if T0 == 0:
            return {"T_total_ms": 0, "T_L3_ms": 0.0, "ratio": 0}
        if K0 == 0:
            raise ValueError("K0 must not be 0.")
        if B == 0:
            raise ValueError("B must not be 0.")

        datatype_bytes = {
            "BFP16": 2,
            "FP16": 2,
            "FP32": 4,
            "INT32": 4,
            "INT64": 8,
        }

        bytes_per_elem = datatype_bytes.get(datatype, 2)
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
            raise ValueError(f"Unknown op_type: {op_type}, expected 'allGather' | 'reduceScatter' |'allReduce'")

        T_total = T0 + T_L3_ms

        return {"T_total_ms": T_total, "T_L3_ms": T_L3_ms, "ratio": T_total / T0}

    def sum_by_columns(self, df: pd.DataFrame, group_cols: list, sum_col: str, step_id: int = None) -> pd.DataFrame:
        """
        当多个指定列值相同时，对另一列的值进行求和
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
