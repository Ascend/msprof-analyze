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

from msprof_analyze.cluster_analyse.cluster_kernels_analysis.operator_mbu.mbu_calculator import (
    GB_TO_BYTES,
    MBUCalculator,
)
from msprof_analyze.cluster_analyse.recipes.base_recipe_analysis import BaseRecipeAnalysis
from msprof_analyze.prof_common.constant import Constant
from msprof_analyze.prof_common.file_manager import FileManager
from msprof_analyze.prof_common.logger import get_logger

logger = get_logger()


class OperatorMbu(BaseRecipeAnalysis):
    """生成 kernel 级 MBU（内存带宽利用率）明细，并输出单一 MBU.csv。"""

    MBU_CSV = "MBU.csv"
    PEAK_BW_ARG = "chip_peak_bandwidth"

    @property
    def base_dir(self):
        """返回当前分析任务目录名。"""
        return os.path.basename(os.path.dirname(__file__))

    @classmethod
    def add_parser_argument(cls, parser):
        """注册 MBU 自定义参数：芯片理论 HBM 峰值带宽（GB/s）。"""
        parser.add_argument(
            "--chip_peak_bandwidth",
            type=float,
            default=None,
            help="Chip peak HBM bandwidth in GB/s used to compute MBU. "
            "If omitted, only access bytes and achieved bandwidth are reported (MBU left empty).",
        )

    def run(self, context, save=True):
        """执行算子 MBU 分析，并将 kernel 级结果保存为单一 MBU.csv。"""
        mapper_res = self.mapper_func(context)
        if not save:
            return [(rank, df) for rank, df in mapper_res if df is not None and not df.empty]
        mbu_df = self.reducer_func(mapper_res)
        self.save(mbu_df)
        return None

    def _mapper_func(self, data_map, analysis_class):
        """生成单个 rank 的 kernel 级 MBU 结果。"""
        rank_id = data_map.get(Constant.RANK_ID)
        peak_bandwidth_gb = self._extra_args.get(self.PEAK_BW_ARG, None)

        mbu_df = MBUCalculator(data_map, peak_bandwidth_gb, analysis_class).run()
        if mbu_df is None or mbu_df.empty:
            logger.warning("No MBU data calculated for rank %s", rank_id)
            return rank_id, pd.DataFrame()

        mbu_df.insert(0, "rank_id", rank_id)
        return rank_id, mbu_df

    @staticmethod
    def reducer_func(mapper_res):
        """合并所有 rank 的 kernel 级 MBU 结果，并按 rank_id、kernel_ts 排序。"""
        kernel_mbu_dfs = [df for _, df in mapper_res if df is not None and not df.empty]
        if not kernel_mbu_dfs:
            return pd.DataFrame()
        result = pd.concat(kernel_mbu_dfs, ignore_index=True)
        sort_columns = [column for column in ("rank_id", "kernel_ts") if column in result.columns]
        if sort_columns:
            result = result.sort_values(sort_columns).reset_index(drop=True)
        return result

    def save(self, mbu_df):
        """将 kernel 级 MBU 结果写入单一 MBU.csv。"""
        if mbu_df is None or mbu_df.empty:
            logger.warning("No MBU data to save.")
            return
        mbu_df = self._format_columns(mbu_df)
        output_file = os.path.join(self.output_path, self.MBU_CSV)
        FileManager.create_csv_from_dataframe(output_file, mbu_df, index=False)
        logger.info("MBU result saved to %s", output_file)

    def _format_columns(self, df):
        """格式化输出列：带宽由 Byte/s 换算为 GB/s，并重命名为友好列名。"""
        df = df.copy()
        for col in ["achieved_bandwidth", "chip_peak_bandwidth"]:
            if col in df.columns:
                df[col] = (pd.to_numeric(df[col], errors="coerce") / GB_TO_BYTES).round(2)
        if "mbu" in df.columns:
            df["mbu"] = pd.to_numeric(df["mbu"], errors="coerce").round(4)

        column_mapping = {
            "rank_id": "Rank ID",
            "kernel_name": "Kernel Name",
            "op_type": "Op Type",
            "kernel_ts": "Kernel Start(ns)",
            "kernel_end": "Kernel End(ns)",
            "kernel_duration": "Kernel Duration(ns)",
            "access_bytes": "Access Bytes",
            "achieved_bandwidth": "Achieved Bandwidth(GB/s)",
            "chip_peak_bandwidth": "Chip Peak Bandwidth(GB/s)",
            "mbu": "MBU",
            "input_shapes": "Input Shapes",
            "output_shapes": "Output Shapes",
        }
        ordered = [c for c in column_mapping if c in df.columns]
        return df[ordered].rename(columns=column_mapping)
