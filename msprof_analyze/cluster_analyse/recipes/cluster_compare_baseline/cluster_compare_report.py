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

import pandas as pd
from msprof_analyze.prof_common.logger import get_logger

logger = get_logger()


class ClusterCompareReportMixin:
    """
    集群对比分析报告收集类（Mixin）

    设计说明：
        本 Mixin 负责报告数据的收集（_record_text、_record_operator、
        _record_operator_table）和重置（_reset_reports），不负责文件保存。

        文件保存由 Recipe 类通过 BaseRecipeAnalysis.dump_data 和
        FileManager.create_common_file 完成，复用基类的 output_path。

    组合约束：
        使用本 Mixin 的类需要继承 BaseRecipeAnalysis，并可通过以下属性访问报告数据：
        - text_reports: 文本报告列表（由 _record_text 初始化）
        - operator_reports: 算子报告列表（由 _record_operator 初始化）
        - _current_report_rank_id: 当前报告的 rank ID
    """

    def _record_text(self, message):
        if not hasattr(self, "text_reports"):
            self.text_reports = []
        self.text_reports.append(str(message).rstrip("\n"))

    def _record_operator(self, **kwargs):
        if not hasattr(self, "operator_reports"):
            self.operator_reports = []
        row = {k: kwargs.get(k) for k in [
            "step_id", "phase", "parallel_type", "op_type", "data_type", "count",
            "group_rank", "start_ns", "end_ns", "current_domain", "baseline_domain",
            "current_duration", "baseline_duration", "actual_ratio", "theoretical_ratio",
            "is_abnormal", "conclusion", "suggestion"
        ]}
        row["rank_id"] = getattr(self, "_current_report_rank_id", None)
        self.operator_reports.append(row)
        return row

    def _record_operator_table(self, title, rows):
        if not rows:
            return
        cols = ["step_id", "phase", "parallel_type", "op_type", "data_type", "count", "group_rank",
                "current_domain", "baseline_domain", "current_duration", "baseline_duration",
                "actual_ratio", "theoretical_ratio", "is_abnormal", "conclusion"]
        df = pd.DataFrame(rows)
        df = df[[c for c in cols if c in df.columns]]
        for col in ("current_duration", "baseline_duration", "actual_ratio", "theoretical_ratio"):
            if col in df.columns:
                df[col] = df[col].apply(lambda v: round(v, 6) if pd.notna(v) else v)
        self._record_text(title)
        self._record_text(df.to_string(index=False))

    def _reset_reports(self, rank_id):
        self.text_reports = []
        self.operator_reports = []
        self._current_report_rank_id = rank_id
