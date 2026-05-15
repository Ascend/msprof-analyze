# Copyright (c) 2024, Huawei Technologies Co., Ltd.
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
import os
from typing import List
from msprof_analyze.advisor.dataset.communication.communication_dataset import CommunicationDataset
from msprof_analyze.advisor.dataset.profiling.profiling_dataset import ProfilingDataset
from msprof_analyze.advisor.display.prompt.base_prompt import BasePrompt
from msprof_analyze.advisor.result.result import OptimizeResult
from msprof_analyze.advisor.result.item import OptimizeItem, OptimizeRecord
from msprof_analyze.prof_common.additional_args_manager import AdditionalArgsManager
from msprof_analyze.prof_common.file_manager import FileManager
from msprof_analyze.advisor.utils.utils import convert_to_float
from msprof_analyze.advisor.dataset.cluster.hccl_collection import HcclInfo
from msprof_analyze.advisor.dataset.profiling.info_collection import OpInfo
from msprof_analyze.prof_common.additional_args_manager import AdditionalArgsManager

logger = get_logger()


class SDMAOperator:
    def __init__(self, hccl_info: HcclInfo):
        self._ts = hccl_info.ts
        self._dur = hccl_info.elapse_time
        self._name = hccl_info.name
        self._bandwidth = hccl_info.sdma_info.get('Bandwidth(GB/s)', 0)

    @property
    def ts(self):
        return self._ts

    @property
    def dur(self):
        return self._dur

    @property
    def end(self):
        return self._ts + self._dur * 1000

    @property
    def name(self):
        return self._name

    @property
    def bandwidth(self):
        return self._bandwidth


class BandwidthContentionChecker:
    _CHECKER = "BandwidthContentionChecker"

    def __init__(self, **kwargs):
        self.contention_issues = False
        self.desc = ""
        self.step_id = kwargs.get("step")
        self.stage = None
        self.threshold = 0
        self.contention_topk = 0
        self.sdma_list: List[SDMAOperator] = []
        self.matmul_list: List[OpInfo] = []
        self.abnormal_sdma_list: List[SDMAOperator] = []
        self.suggestions = []
        self._init_rule()
        self.headers = ["op name", "duration(ms)", "bandwidth(GB/s)"]

    @staticmethod
    def check_sdma_operator(hccl_op: HcclInfo):
        if hccl_op.sdma_info:
            if hccl_op.sdma_info.get('Transit Size(MB)', 0):
                return True
        return False

    def export_sdma_list(self):
        res = []
        for hccl_op in self.abnormal_sdma_list:
            res.append([hccl_op.name, round(hccl_op.dur, 4), round(hccl_op.bandwidth, 2)])
        res.sort(key=lambda x: x[2])
        return res[:min(len(res), self.contention_topk)]

    def check_task_dict(self, profiling_dataset: ProfilingDataset) -> bool:
        if not hasattr(profiling_dataset, "op_summary"):
            logger.warning("Skip %s checker because of not containing %s", self._CHECKER, "op summary")
            return False
        if not hasattr(profiling_dataset.op_summary, "task_dict"):
            logger.warning("Skip %s checker because of not containing %s", self._CHECKER, "op summary")
            return False
        return True

    def extract_matmul_operator(self, profiling_dataset: ProfilingDataset):
        for key, value in profiling_dataset.op_summary.task_dict.items():
            if "matmul" in key.lower():
                self.matmul_list.extend(value)
        self.matmul_list.sort(key=lambda x: convert_to_float(x.task_start_time))

    def extract_sdma_operator(self, hccl_dataset: CommunicationDataset):
        for step_id, step_data in hccl_dataset.hccl_dict.items():
            if self.step_id is not None and step_id != self.step_id:
                continue
            for hccl_op in step_data:
                if self.check_sdma_operator(hccl_op):
                    self.sdma_list.append(SDMAOperator(hccl_op))
        self.sdma_list.sort(key=lambda x: x.ts)

    def check_contention(self, hccl_dataset: CommunicationDataset, profiling_dataset: ProfilingDataset) -> None:
        if not self.check_task_dict(profiling_dataset):
            return
        self.extract_matmul_operator(profiling_dataset)
        self.extract_sdma_operator(hccl_dataset)
        hccl_index = 0
        matmul_index = 0
        while hccl_index < len(self.sdma_list) and matmul_index < len(self.matmul_list):
            if self.sdma_list[hccl_index].end < self.matmul_list[matmul_index].get_float_attr("task_start_time"):
                hccl_index += 1
            elif self.matmul_list[matmul_index].get_float_attr("task_start_time") + \
                    self.matmul_list[matmul_index].get_float_attr("task_duration") < self.sdma_list[hccl_index].ts:
                matmul_index += 1
            else:
                if self.sdma_list[hccl_index].bandwidth < self.threshold:
                    self.abnormal_sdma_list.append(self.sdma_list[hccl_index])
                hccl_index += 1
        if self.abnormal_sdma_list:
            self.contention_issues = True
            self.desc = self.desc.format(threshold=self.threshold)

    def make_record(self, result: OptimizeResult):
        """
        make record for what and how to optimize
        """
        optimization_item = OptimizeItem(self.problem, self.desc, self.suggestions)
        result.add(OptimizeRecord(optimization_item))

        sub_table_name = BasePrompt.get_sub_table_name(self.problem, self.stage)
        result.add_detail(sub_table_name, headers=self.headers)

        for hccl_op in self.abnormal_sdma_list:
            result.add_detail(sub_table_name, detail=[hccl_op.name, round(hccl_op.dur, 4), round(hccl_op.bandwidth, 2)])

    def make_render(self, html_render, add_render_list=True, **kwargs):
        priority = kwargs.get("priority")
        return html_render.render_template(key="communication",
                                           template_dir="templates",
                                           template_name="contention.html",
                                           desc=self.desc,
                                           solutions=self.solutions,
                                           headers=self.headers,
                                           data=self.export_sdma_list(),
                                           topk=self.contention_topk,
                                           priority_background_color=priority)

    def _init_rule(self):
        language = AdditionalArgsManager().language
        contention_rule_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))),
            "rules",
            language,
            "bandwidth_contention.yaml"
        )

        contention_rule = FileManager.read_yaml_file(contention_rule_path)
        self.problem = contention_rule.get("problem")
        self.desc = contention_rule.get("description")
        self.threshold = contention_rule.get("threshold", 0) * contention_rule.get("sdma_baseline", 0)
        self.contention_topk = contention_rule.get("top_num", 3)
        self.solutions = contention_rule.get("solutions")
        if not self.desc or not self.solutions or not isinstance(self.solutions, list):
            raise RuntimeError("The configuration file of the bandwidth contention analyzer is abnormal. Please check.")
        for solution in self.solutions:
            for _, val in solution.items():
                self.suggestions.append(f"{val.get('desc')}")
