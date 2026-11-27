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

from math import isfinite

import numpy as np
import pandas as pd

from msprof_analyze.cluster_analyse.cluster_kernels_analysis.operator_mbu.operator_bytes import compute_access_bytes
from msprof_analyze.prof_exports.mbu_export import KernelBytesExport, TARGET_OP_TYPES
from msprof_analyze.cluster_analyse.common_func.utils import ensure_numeric_columns
from msprof_analyze.prof_common.constant import Constant
from msprof_analyze.prof_common.logger import get_logger

logger = get_logger()

GB_TO_BYTES = 1e9
NS_TO_S = 1e-9


class MBUCalculator:
    """按 opType 圈定关键算子，由 kernel 输入/输出 shape 计算访存字节并得到 MBU。

    访存字节直接来自 COMPUTE_TASK_INFO 的 shape/dtype，不依赖采集侧 with_flops/mstx Range。
    峰值带宽由调用方（CLI 参数）传入；缺省时只输出访存字节与实测带宽，MBU 留空。
    """

    TARGET_OP_TYPES = TARGET_OP_TYPES
    REQUIRED_COLUMNS = {
        "type",
        "kernel_ts",
        "kernel_end",
        "task_duration",
        "input_shapes",
        "input_types",
        "output_shapes",
        "output_types",
    }

    OUTPUT_COLUMNS = [
        "kernel_name",
        "kernel_ts",
        "kernel_end",
        "op_type",
        "access_bytes",
        "kernel_duration",
        "achieved_bandwidth",
        "chip_peak_bandwidth",
        "mbu",
        "input_shapes",
        "output_shapes",
    ]

    def __init__(self, data_map, peak_bandwidth_gb=None, analysis_class=""):
        self.profiler_db_path = data_map.get(Constant.PROFILER_DB_PATH)
        self.step_range = data_map.get(Constant.STEP_RANGE)
        self.analysis_class = analysis_class
        # 仅未提供参数时留空；非法值不能静默退化为不计算 MBU。
        self.peak_bandwidth = None
        if peak_bandwidth_gb is not None:
            try:
                peak = float(peak_bandwidth_gb) * GB_TO_BYTES
            except (TypeError, ValueError, OverflowError) as err:
                raise ValueError("chip_peak_bandwidth must be a finite positive number.") from err
            if not isfinite(peak) or peak <= 0:
                raise ValueError("chip_peak_bandwidth must be a finite positive number.")
            self.peak_bandwidth = peak

    def run(self):
        logger.info("Start MBU calculation.")
        kernel_df = self._query_kernel_bytes()
        if kernel_df is None or kernel_df.empty:
            logger.warning("No kernel shape data found. Skip MBU calculation.")
            return pd.DataFrame()

        missing_columns = self.REQUIRED_COLUMNS.difference(kernel_df.columns)
        if missing_columns:
            logger.error("Kernel data missing required columns: %s. Skip MBU calculation.", sorted(missing_columns))
            return pd.DataFrame()

        # 按 opType 圈定关键算子（Matmul / FlashAttention / GroupedMatmul）。
        df = kernel_df[kernel_df["type"].isin(self.TARGET_OP_TYPES)].copy()
        if df.empty:
            logger.warning("No target operator (Matmul/FlashAttention/GroupedMatmul) kernels found.")
            return pd.DataFrame()

        df = ensure_numeric_columns(df, ["kernel_ts", "kernel_end", "task_duration"])
        df = df[df["task_duration"] > 0]
        if df.empty:
            return pd.DataFrame()

        df["access_bytes"] = [
            compute_access_bytes(*values)
            for values in zip(df["input_shapes"], df["input_types"], df["output_shapes"], df["output_types"])
        ]
        df = df[df["access_bytes"] > 0]
        if df.empty:
            return pd.DataFrame()

        df["op_type"] = df["type"]
        df["kernel_duration"] = df["task_duration"]
        df["achieved_bandwidth"] = df["access_bytes"] / (df["task_duration"] * NS_TO_S)

        if self.peak_bandwidth:
            df["chip_peak_bandwidth"] = self.peak_bandwidth
            df["mbu"] = df["achieved_bandwidth"] / self.peak_bandwidth
        else:
            # 未提供峰值带宽时，MBU 无法计算，留空（仅输出访存字节与实测带宽）。
            logger.warning("chip_peak_bandwidth not provided; MBU left empty, only bandwidth reported.")
            df["chip_peak_bandwidth"] = np.nan
            df["mbu"] = np.nan

        # 仅去除完全重复的查询记录，保留 globalTaskId 不同的并发任务。
        df = df.drop_duplicates().reset_index(drop=True)
        logger.info("MBU calculation finished, result rows: %s", len(df))
        # reindex 按固定列输出，查询结果缺失的列补空值，避免 KeyError。
        return df.reindex(columns=self.OUTPUT_COLUMNS)

    def _query_kernel_bytes(self):
        """查询 kernel 的 opType、输入/输出 shape 与 dtype、以及 kernel 时长。"""
        export = KernelBytesExport(self.profiler_db_path, self.analysis_class, self.step_range)
        df = export.read_export_db()
        if df is None or df.empty:
            return None
        # shape 与 dtype 列的取值可能带引号，统一剥离后再参与访存字节计算。
        for column_name in ["input_shapes", "output_shapes", "input_types", "output_types"]:
            if column_name in df.columns:
                df[column_name] = df[column_name].fillna("").astype(str).str.strip('"\'')
        return df
