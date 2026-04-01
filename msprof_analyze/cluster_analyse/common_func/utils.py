# Copyright (c) 2024, Huawei Technologies Co., Ltd.
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

from multiprocessing import Value, Lock

import numpy as np
import pandas as pd

from msprof_analyze.prof_common.logger import get_logger

logger = get_logger()


def format_columns(df: pd.DataFrame):
    formatted_df = df.rename(
        {
            "25%": "Q1Ns",
            "50%": "MedianNs",
            "75%": "Q3Ns",
            0.25: "Q1Ns",
            0.5: "MedianNs",
            0.75: "Q3Ns",
            "Q1": "Q1Ns",
            "Q3": "Q3Ns",
            "min": "MinNs",
            "max": "MaxNs",
            "median": "MedianNs",
            "sum": "SumNs",
            "std": "StdNs",
            "mean": "MeanNs",
            "count": "Count"
        },
        axis="columns"
    )

    stats_cols = ["Count", "MeanNs", "StdNs", "MinNs", "Q1Ns", "MedianNs", "Q3Ns", "MaxNs", "SumNs"]
    other_cols = [col for col in formatted_df.columns if col not in stats_cols]
    return formatted_df[stats_cols + other_cols]


def describe_duration(series_groupby):
    agg_df = series_groupby.agg(["min", "max", "count", "std", "mean", "sum"])
    quantile_df = series_groupby.quantile([0.25, 0.5, 0.75])

    quantile_df = quantile_df.unstack()
    quantile_df.columns = ["25%", "50%", "75%"]

    stats_df = pd.merge(agg_df, quantile_df, left_index=True, right_index=True)
    formated_df = format_columns(stats_df)
    formated_df.index.name = stats_df.index.name
    return formated_df


def stdev(df, aggregated):
    if len(df) <= 1:
        return df["stdev"].iloc[0]
    instance = aggregated["totalCount"].loc[df.name]
    var_sum = np.dot(df["totalCount"] - 1, df["stdev"] ** 2)
    deviation = df["averageNs"] - aggregated["averageNs"].loc[df.name]
    dev_sum = np.dot(df["totalCount"], deviation ** 2)
    return np.sqrt((var_sum + dev_sum) / (instance - 1)) if (instance - 1) else 0


def convert_unit(df: pd.DataFrame, src_unit, dst_unit, factor):
    df.loc[:, df.columns.str.endswith(src_unit)] = df.loc[:, df.columns.str.endswith(src_unit)].apply(
        lambda x: x / factor)
    df = df.rename(columns=lambda x: x.replace(src_unit, "".join(["(", dst_unit, ")"])))
    return df


def increase_shared_value(shared_value: Value, lock: Lock):
    with lock:
        shared_value.value += 1


def double_hash(data):
    uint32_bits = 32
    uint32_max = 0xFFFFFFFF  # 32 位无符号整数的最大值
    prime = [29, 131]
    hash_values = [0, 0]

    for d in data:
        hash_values[0] = (hash_values[0] * prime[0] + ord(d)) & uint32_max
        hash_values[1] = (hash_values[1] * prime[1] + ord(d)) & uint32_max

    return ((hash_values[0] << uint32_bits) | hash_values[1])

def calculate_zscore(x, mean, std):
    if std != 0:
        zscore = (x - mean) / std
    elif x > mean:
        zscore = 100
    else:
        zscore = -100
    return zscore

def detect_outliers_z_score(data, threshold=3):
    """
    使用 Z-Score 方法判断是否存在异常值。
    Z-Score 是一种统计方法，用于衡量数据点与均值的标准差距离。
    如果某个数据点的 Z-Score 超过阈值（默认为3），则认为它是异常值。

    返回值：
    - True：存在异常值
    - False：不存在异常值
    """
    # 计算数据的均值
    mean = np.mean(data)  # 均值表示数据的中心位置

    # 计算数据的标准差
    std = np.std(data)  # 标准差表示数据的离散程度

    # 如果标准差为0，直接返回 False（不存在异常值）
    if std == 0:
        return False

    # 计算 Z-Score 的上阈值和下阈值
    z_scores_upper_threshold = threshold * std + mean
    z_scores_lower_threshold = -threshold * std + mean

    # 判断是否存在 Z-Score 超过阈值的数据点
    has_outliers = any(x > z_scores_upper_threshold or x < z_scores_lower_threshold for x in data)

    # 返回是否存在异常值的布尔值
    return has_outliers



def ensure_numeric_columns(df, columns, target_type='int64'):
    if df is None or df.empty:
        return df
    for col in columns:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0).astype(target_type)
    return df


class UnionFind(object):
    """Disjoint Set Union"""

    @classmethod
    def union(cls, *args):
        result = set()
        for s in args:
            if not isinstance(s, set):
                logger.warning(f"All arguments must be sets, got {type(s).__name__}")
                return set()
            result |= s
        return result

    @classmethod
    def is_connected(cls, first_set: set, second_set: set):
        """
        check whether set p and set q are connected
        """
        if not isinstance(first_set, set) or not isinstance(second_set, set):
            return False
        return len(first_set & second_set) > 0
