# Copyright (c) 2023, Huawei Technologies Co., Ltd.
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

from msprof_analyze.prof_common.logger import get_logger
from abc import ABC

import pandas as pd

from msprof_analyze.advisor.advisor_backend.compute_advice.compute_advice_base import ComputeAdviceBase
from msprof_analyze.advisor.advisor_backend.compute_advice.npu_fused.csv_analyzer import CSVAnalyzer
from msprof_analyze.advisor.advisor_backend.compute_advice.npu_fused.json_analyzer import JSONAnalyzer

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
