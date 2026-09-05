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

import numpy as np
import pandas as pd

from msprof_analyze.cluster_analyse.cluster_kernels_analysis.operator_mbu.operator_bytes import compute_access_bytes
from msprof_analyze.prof_exports.mbu_export import KernelBytesExport
from msprof_analyze.cluster_analyse.common_func.utils import ensure_numeric_columns
from msprof_analyze.prof_common.constant import Constant
from msprof_analyze.prof_common.logger import get_logger
from msprof_analyze.prof_common.utils import convert_to_float

logger = get_logger()

GB_TO_BYTES = 1e9
NS_TO_S = 1e-9


class MBUCalculator:
    """按 opType 圈定关键算子，由 kernel 输入/输出 shape 计算访存字节并得到 MBU。

    访存字节直接来自 COMPUTE_TASK_INFO 的 shape/dtype，不依赖采集侧 with_flops/mstx Range。
    峰值带宽由调用方（CLI 参数）传入；缺省时只输出访存字节与实测带宽，MBU 留空。
    """

    # Device 侧 opType 与关键算子族的对应关系（与 issue 要求的 3 类算子一致）。
    TARGET_OP_TYPES = {
        "MatMulV2",
        "MatMulV3",
        "FlashAttentionScore",
        "GroupedMatmul",
        "GroupedMatMul",
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
        self.analysis_class = analysis_class
        # peak_bandwidth_gb 单位为 GB/s，内部统一换算为 Byte/s；
        # 入参可能来自 CLI 等外部输入（如字符串 "1600"），先做数值转换，无法转换或非正数视为未提供。
        peak = convert_to_float(peak_bandwidth_gb) if peak_bandwidth_gb is not None else 0
        self.peak_bandwidth = peak * GB_TO_BYTES if peak > 0 else None

    def run(self):
        logger.info("Start MBU calculation.")
        kernel_df = self._query_kernel_bytes()
        if kernel_df is None or kernel_df.empty:
            logger.warning("No kernel shape data found. Skip MBU calculation.")
            return pd.DataFrame()

        if "type" not in kernel_df.columns:
            logger.error("Kernel data missing opType column. Skip MBU calculation.")
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

        df["access_bytes"] = df.apply(
            lambda row: compute_access_bytes(
                row.get("input_shapes", ""),
                row.get("input_types", ""),
                row.get("output_shapes", ""),
                row.get("output_types", ""),
            ),
            axis=1,
        )
        df = df[df["access_bytes"] > 0]
        if df.empty:
            return pd.DataFrame()

        df["op_type"] = df["type"]
        df["kernel_duration"] = df["task_duration"]
        df["achieved_bandwidth"] = df["access_bytes"] / (df["task_duration"] * NS_TO_S)

        if self.peak_bandwidth:
            df["chip_peak_bandwidth"] = self.peak_bandwidth
            df["mbu"] = (df["achieved_bandwidth"] / self.peak_bandwidth).round(4)
        else:
            # 未提供峰值带宽时，MBU 无法计算，留空（仅输出访存字节与实测带宽）。
            logger.warning("chip_peak_bandwidth not provided; MBU left empty, only bandwidth reported.")
            df["chip_peak_bandwidth"] = np.nan
            df["mbu"] = np.nan

        # 同一 kernel 时间段唯一，按 (kernel_ts, kernel_end) 去重避免重复计数。
        df = df.drop_duplicates(subset=["kernel_ts", "kernel_end"]).reset_index(drop=True)
        logger.info("MBU calculation finished, result rows: %s", len(df))
        # reindex 按固定列输出，查询结果缺失的列补空值，避免 KeyError。
        return df.reindex(columns=self.OUTPUT_COLUMNS)

    def _query_kernel_bytes(self):
        """查询 kernel 的 opType、输入/输出 shape 与 dtype、以及 kernel 时长。"""
        export = KernelBytesExport(self.profiler_db_path, self.analysis_class)
        df = export.read_export_db()
        if df is None or df.empty:
            return None
        # shape 与 dtype 列的取值可能带引号，统一剥离后再参与访存字节计算。
        for column_name in ["input_shapes", "output_shapes", "input_types", "output_types"]:
            if column_name in df.columns:
                df[column_name] = df[column_name].astype(str).str.strip('"\'')
        return df
