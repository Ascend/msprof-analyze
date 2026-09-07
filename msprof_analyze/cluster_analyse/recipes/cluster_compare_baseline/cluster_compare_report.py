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


import os

import pandas as pd

from msprof_analyze.prof_common.logger import get_logger
from msprof_analyze.prof_common.file_manager import FileManager
from msprof_analyze.prof_common.path_manager import PathManager

logger = get_logger()


class ClusterCompareReportMixin:
    """
    Cluster Compare Report Mixin

    提供集群对比分析报告的收集、记录和刷新功能。

    设计说明：
        本 Mixin 负责报告数据的收集（_record_text, _record_operator）、
        格式化和输出（_flush_reports），以及报告重置（_reset_reports）。

    组合约束：
        使用本 Mixin 的类需要提供以下属性或方法：
        - report_output_dir: 可选，报告输出目录路径
        - _current_report_rank_id: 当前报告的 rank ID

        本 Mixin 依赖 FileManager 和 PathManager 进行安全的文件操作。

    与 BaseRecipeAnalysis 的关系：
        本 Mixin 设计为可混入到继承 BaseRecipeAnalysis 的 Recipe 类中，
        复用 BaseRecipeAnalysis 的 output_path 等属性。
        同时也可独立使用，但需要外部提供 report_output_dir。
    """

    def _resolve_report_output_dir(self, params):
        """
        解析报告输出目录路径并进行安全校验

        Args:
            params: 参数对象或字典，可能包含 output_dir/output_path/result_dir/report_dir

        Returns:
            校验后的输出目录路径

        Note:
            解析优先级：字典键值 > 对象属性 > 当前工作目录
            使用 PathManager 进行路径安全校验
        """
        # 解析输出目录
        if isinstance(params, dict):
            for key in ("output_dir", "output_path", "result_dir", "report_dir"):
                if params.get(key):
                    output_dir = params.get(key)
                    break
            else:
                output_dir = None
        else:
            for key in ("output_dir", "output_path", "result_dir", "report_dir"):
                value = getattr(params, key, None)
                if value:
                    output_dir = value
                    break
            else:
                output_dir = None

        if output_dir is None:
            output_dir = os.getcwd()

        # 使用 PathManager 进行路径安全校验
        try:
            # 获取真实路径（绝对路径）
            output_dir = PathManager.get_realpath(output_dir)
        except RuntimeError as e:
            logger.warning(f"Failed to resolve path '{output_dir}': {e}, falling back to current working directory")
            output_dir = os.getcwd()

        # 检查路径长度
        PathManager.check_path_length(output_dir)

        return output_dir

    def _record_text(self, message):
        """
        记录文本报告内容

        Args:
            message: 要记录的文本消息
        """
        if not hasattr(self, "text_reports"):
            self.text_reports = []
        self.text_reports.append(str(message).rstrip("\n"))

    def _record_operator(self, **kwargs):
        """
        记录算子级别的报告数据

        Args:
            **kwargs: 算子报告字段，包括：
                - step_id: 步骤 ID
                - phase: 阶段
                - parallel_type: 并行类型
                - op_type: 算子类型
                - data_type: 数据类型
                - count: 数量
                - group_rank: 组 rank
                - start_ns: 开始时间（纳秒）
                - end_ns: 结束时间（纳秒）
                - current_domain: 当前域
                - baseline_domain: 基线域
                - current_duration: 当前持续时间
                - baseline_duration: 基线持续时间
                - actual_ratio: 实际比率
                - theoretical_ratio: 理论比率
                - is_abnormal: 是否异常
                - conclusion: 结论
                - suggestion: 建议

        Returns:
            记录的行数据字典
        """
        if not hasattr(self, "operator_reports"):
            self.operator_reports = []
        row = {
            "rank_id": getattr(self, "_current_report_rank_id", None),
            "step_id": kwargs.get("step_id"),
            "phase": kwargs.get("phase"),
            "parallel_type": kwargs.get("parallel_type"),
            "op_type": kwargs.get("op_type"),
            "data_type": kwargs.get("data_type"),
            "count": kwargs.get("count"),
            "group_rank": kwargs.get("group_rank"),
            "start_ns": kwargs.get("start_ns"),
            "end_ns": kwargs.get("end_ns"),
            "current_domain": kwargs.get("current_domain"),
            "baseline_domain": kwargs.get("baseline_domain"),
            "current_duration": kwargs.get("current_duration"),
            "baseline_duration": kwargs.get("baseline_duration"),
            "actual_ratio": kwargs.get("actual_ratio"),
            "theoretical_ratio": kwargs.get("theoretical_ratio"),
            "is_abnormal": kwargs.get("is_abnormal"),
            "conclusion": kwargs.get("conclusion"),
            "suggestion": kwargs.get("suggestion"),
        }
        self.operator_reports.append(row)
        return row

    def _record_operator_table(self, title, rows):
        """
        记录算子表格报告

        Args:
            title: 表格标题
            rows: 表格数据行列表
        """
        if not rows:
            return

        columns = [
            "step_id",
            "phase",
            "parallel_type",
            "op_type",
            "data_type",
            "count",
            "group_rank",
            "current_domain",
            "baseline_domain",
            "current_duration",
            "baseline_duration",
            "actual_ratio",
            "theoretical_ratio",
            "is_abnormal",
            "conclusion",
        ]
        display_df = pd.DataFrame(rows)
        display_df = display_df[[column for column in columns if column in display_df.columns]]
        for column in ("current_duration", "baseline_duration", "actual_ratio", "theoretical_ratio"):
            if column in display_df.columns:
                display_df[column] = display_df[column].apply(
                    lambda value: round(value, 6) if pd.notna(value) else value
                )
        self._record_text(title)
        self._record_text(display_df.to_string(index=False))

    def _flush_reports(self, rank_id=None):
        """
        将报告刷新到文件系统，使用 FileManager 安全封装

        Args:
            rank_id: 可选的 rank ID，用于生成带后缀的文件名
        """
        # 解析输出目录
        # 优先使用 report_output_dir 属性，否则使用当前工作目录
        output_dir = getattr(self, "report_output_dir", None)
        output_dir = self._resolve_report_output_dir(output_dir)

        # 使用 FileManager 创建输出目录
        try:
            FileManager.create_output_dir(output_dir, is_overwrite=False)
            logger.info(f"Output directory ready: {output_dir}")
        except Exception as e:
            logger.error(f"Failed to create output directory '{output_dir}': {e}")
            return

        suffix = f"_rank_{rank_id}" if rank_id is not None else ""
        text_path = os.path.join(output_dir, f"cluster_compare_baseline{suffix}.txt")
        csv_path = os.path.join(output_dir, f"cluster_compare_baseline_operator{suffix}.csv")

        # 使用 FileManager.create_common_file 写入文本报告
        if getattr(self, "text_reports", None):
            content = "\n".join(self.text_reports) + "\n"
            try:
                FileManager.create_common_file(text_path, content)
                logger.info("Cluster compare baseline text report saved to %s", text_path)
            except Exception as e:
                logger.error(f"Failed to write text report '{text_path}': {e}")

        # 使用 FileManager.create_csv_from_dataframe 写入 CSV 报告
        if getattr(self, "operator_reports", None):
            df = pd.DataFrame(self.operator_reports)
            try:
                FileManager.create_csv_from_dataframe(csv_path, df, index=False)
                logger.info("Cluster compare baseline operator report saved to %s", csv_path)
            except Exception as e:
                logger.error(f"Failed to write CSV report '{csv_path}': {e}")

    def _reset_reports(self, rank_id):
        """
        重置报告数据

        Args:
            rank_id: 当前报告的 rank ID
        """
        self.text_reports = []
        self.operator_reports = []
        self._current_report_rank_id = rank_id
