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
from decimal import Decimal

from msprof_analyze.advisor.advisor_backend.common_func_advisor.constant import Constant
from msprof_analyze.advisor.advisor_backend.timeline_advice.timeline_advice_base import TimelineAdviceBase

logger = get_logger()


class OpScheduleAdvice(TimelineAdviceBase):
    def __init__(self, collection_path: str):
        super().__init__(collection_path)
        self.cur_data = list()
        self.cur_bottleneck = str()
        self.cur_advice = str()

    def run(self):
        if not self.path_check():
            return self.output_format_data
        self.preparse()
        self.process()
        self.output()
        return self.output_format_data

    def process(self):
        cpt_data = self.preparse_data[self.PreParseType.OVERLAP_CPT]
        free_data = self.preparse_data[self.PreParseType.OVERLAP_FREE]
        if not cpt_data or not free_data:
            logger.error("Fail to find Overlap data.")
            return

        op_dur = [entry.get("dur", 0) for entry in cpt_data]
        op_free = [0.0] * len(cpt_data)
        merge_data = list()
        merge_data.extend(cpt_data)
        merge_data.extend(free_data)
        merge_data.sort(key=lambda x: Decimal(x.get("ts")))
        idx = free_idx = 0
        while idx < len(merge_data) and free_idx < len(op_free):
            entry = merge_data[idx]
            entry_name = entry.get("name")
            if entry_name == 'Free':
                op_free[free_idx] = merge_data[idx].get('dur')
            elif entry_name == 'Computing':
                free_idx += 1
            idx += 1
        self.cur_data.append(op_dur)
        self.cur_data.append(op_free)
        free_ratio, cpt_ratio, _ = self.get_ratio()
        if free_ratio < 0.2:
            return
        self.cur_bottleneck = f"NPU Utilication: {round(free_ratio * 100, 2)}%, " \
                              f"NPU Free Utilization: {round(cpt_ratio * 100, 2)}%."
        if len(self.preparse_data[self.PreParseType.SYNCHRONIZE]) > 1:
            self.cur_advice = \
                f"Device synchronize {len(self.preparse_data[self.PreParseType.SYNCHRONIZE])} times, " \
                "try to reduce synchronization statements to alleviate the bottleneck of operator delivery.\n"
        small_op_num = self.small_op_block(op_free, op_dur)
        small_op_ratio = small_op_num / len(op_dur) if op_dur else 0.0
        if small_op_ratio > Constant.SMALL_OP_NUM_RATIO:
            self.cur_advice += "There are too many small operators, you can increase the batch size appropriately."

    def small_op_block(self, op_frees, op_durs):
        small_op_num = 0
        for op_free, op_dur in zip(op_frees, op_durs):
            if op_free > op_dur * Constant.SMALL_OP_DUR_RATIO:
                small_op_num += 1
        return small_op_num

    def get_ratio(self):
        cpt_data = self.preparse_data[self.PreParseType.OVERLAP_CPT]
        free_data = self.preparse_data[self.PreParseType.OVERLAP_FREE]
        cmu_data = self.preparse_data[self.PreParseType.OVERLAP_CMU]
        cpt_time = sum([x.get("dur", 0) for x in cpt_data])
        free_time = sum([x.get("dur", 0) for x in free_data])
        cmu_time = sum([x.get("dur", 0) for x in cmu_data])
        total_time = cpt_time + free_time + cmu_time
        if total_time > 0.0:
            return (free_time / total_time, cpt_time / total_time, cmu_time / total_time)
        return (0.0, 0.0, 0.0)
