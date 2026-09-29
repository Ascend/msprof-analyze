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

import os
from collections import defaultdict
from msprof_analyze.advisor.advisor_backend.common_func_advisor.constant import Constant
from msprof_analyze.advisor.advisor_backend.cluster_advice.cluster_advice_base import ClusterAdviceBase
from msprof_analyze.advisor.advisor_backend.prof_bean_advisor.cluster_step_trace_time_bean import (
    ClusterStepTraceTimeBean,
)
from msprof_analyze.prof_common.file_manager import FileManager


class SlowRankAdvice(ClusterAdviceBase):
    RANK = "rank"
    RATIO_THRESHOLD = 0.05
    BOTTLENECK_LIST = ['Computing', 'Communication', "Free"]

    def __init__(self, collection_path: str, kwargs: dict = None):
        super().__init__(collection_path)

    def load_step_time(self):
        csv_path = os.path.join(self.collection_path, Constant.CLUSTER_ANALYSIS_OUTPUT, Constant.CLUSTER_STEP_TIME_CSV)
        if not os.path.exists(csv_path):
            msg = "[ERROR] cluster_step_trace_time.csv doesn't exist, terminate analysis."
            raise RuntimeError(msg)
        step_time = FileManager.read_csv_file(csv_path, ClusterStepTraceTimeBean)
        return step_time

    def run(self):
        self.path_check()
        step_data = self.load_step_time()
        step_dict = self.process(step_data)
        self.output(step_dict)
        return self.output_format_data

    def process(self, step_data: list):
        step_dict = defaultdict(lambda: [0, 0, 0, 0])
        for step_bean in step_data:
            if step_bean.type == self.RANK:
                step_dict[step_bean.index][0] += step_bean.compute
                step_dict[step_bean.index][1] += step_bean.communication
                step_dict[step_bean.index][2] += step_bean.free
        total_time_list = [sum(data_tuple) for rank_id, data_tuple in step_dict.items()]
        if total_time_list:
            mean_total_time = sum(total_time_list) / len(total_time_list)
            for i in range(len(self.BOTTLENECK_LIST)):
                self.produce_bottleneck(step_dict, i, mean_total_time)
        return step_dict

    def produce_bottleneck(self, step_dict: dict, produce_type: int, mean_total_time: float):
        data_list = [data_tuple[produce_type] for rank_id, data_tuple in step_dict.items()]
        max_ratio = self.compute_max_gap_ratio(data_list, mean_total_time)
        if max_ratio > self.RATIO_THRESHOLD:
            self.bottelneck += (
                f'{self.BOTTLENECK_LIST[produce_type]} has some issues in the cluster, '
                f'because the max difference of {self.BOTTLENECK_LIST[produce_type]} time '
                f'has reached {round(max_ratio * mean_total_time / 1000, 3)}ms. \n'
            )

    def output(self, step_dict: dict):  # pylint: disable=arguments-differ
        self.output_format_data[self.DATA] = step_dict
        self.output_format_data[self.BOTTLENECK] = self.bottelneck
