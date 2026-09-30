# -------------------------------------------------------------------------
# This file is part of the MindStudio project.
# Copyright (c) 2023 Huawei Technologies Co.,Ltd.
#
# MindStudio is licensed under Mulan PSL v2.
# You can use this software according to the terms and conditions of the Mulan PSL v2.
# You may obtain a copy of Mulan PSL v2 at:
#
#          http://license.coscl.org.cn/MulanPSL2
#
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND,
# EITHER EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT,
# MERCHANTABILITY OR FIT FOR A PARTICULAR PURPOSE.
# See the Mulan PSL v2 for more details.
# -------------------------------------------------------------------------

from abc import ABC

import pandas as pd

from msprof_analyze.advisor.advisor_backend.compute_advice.compute_advice_base import ComputeAdviceBase
from msprof_analyze.advisor.advisor_backend.compute_advice.npu_fused.csv_analyzer import CSVAnalyzer
from msprof_analyze.advisor.advisor_backend.compute_advice.npu_fused.json_analyzer import JSONAnalyzer
from msprof_analyze.prof_common.logger import get_logger

logger = get_logger()


class NpuFusedAdvice(ComputeAdviceBase, ABC):
    def __init__(self, collection_path: str):
        super().__init__(collection_path)
        self.cur_data = dict()
        self.cur_bottleneck = str()
        self.cur_advice = str()
        self.kernel_details_path = ""
        self.call_stack = None

    def run(self):
        if not self.path_check():
            return self.output_format_data
        self.process()
        self.output()
        return self.output_format_data

    def process(self):
        csv_analyzer = CSVAnalyzer(self.kernel_details_path)
        all_pattern_data = csv_analyzer.process()
        all_pattern_data = all_pattern_data.sort_values(by='duration sum(us)', ascending=False)
        filter_data = all_pattern_data.get(all_pattern_data.get("duration sum(us)", 0) > 0)
        if not self.has_callstack():
            logger.warning("No call stack info found, advice will be incomplete")
            self.cur_data = filter_data
        else:
            json_analyzer = JSONAnalyzer(self.trace_view_path)
            custom_code = json_analyzer.get_custom_code(filter_data, "first_timestamp", "custom code")
            self.cur_data = pd.concat([filter_data, custom_code], axis=1)
        op_num = len(self.cur_data.index)
        op_dur = filter_data["duration sum(us)"].sum()
        if op_num > 0:
            index = 0
            self.cur_bottleneck = f"The computing time of fusable op is {round(op_dur, 2)} ms."
            self.cur_advice = ""
            for _, row in self.cur_data.iterrows():
                advice = f"Advice {index}:\n"
                cur_op = "[" + ", ".join(row.loc["pattern"]) + "]"
                npu_fused_op = row.loc["pattern_name"]
                advice += f"Replace {cur_op} with {npu_fused_op}. "
                if self.call_stack:
                    advice += f"This pattern first happened in: \n{row['custom code']}"
                if index != op_num - 1:
                    advice += "\n"
                index += 1
                self.cur_advice += advice
