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


logger = get_logger()


class ClusterCompareReportMixin:
    def _resolve_report_output_dir(self, params):
        if isinstance(params, dict):
            for key in ("output_dir", "output_path", "result_dir", "report_dir"):
                if params.get(key):
                    return params.get(key)
        for key in ("output_dir", "output_path", "result_dir", "report_dir"):
            value = getattr(params, key, None)
            if value:
                return value
        return os.getcwd()

    def _record_text(self, message):
        if not hasattr(self, "text_reports"):
            self.text_reports = []
        self.text_reports.append(str(message).rstrip("\n"))

    def _record_operator(self, **kwargs):
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
        output_dir = getattr(self, "report_output_dir", None) or os.getcwd()
        os.makedirs(output_dir, exist_ok=True)
        suffix = f"_rank_{rank_id}" if rank_id is not None else ""
        text_path = os.path.join(output_dir, f"cluster_compare_baseline{suffix}.txt")
        csv_path = os.path.join(output_dir, f"cluster_compare_baseline_operator{suffix}.csv")

        if getattr(self, "text_reports", None):
            with open(text_path, "w", encoding="utf-8") as file:
                file.write("\n".join(self.text_reports))
                file.write("\n")
            if hasattr(logger, "info"):
                logger.info("Cluster compare baseline text report saved to %s", text_path)

        if getattr(self, "operator_reports", None):
            pd.DataFrame(self.operator_reports).to_csv(csv_path, index=False, encoding="utf-8-sig")
            if hasattr(logger, "info"):
                logger.info("Cluster compare baseline operator report saved to %s", csv_path)

    def _reset_reports(self, rank_id):
        self.text_reports = []
        self.operator_reports = []
        self._current_report_rank_id = rank_id
