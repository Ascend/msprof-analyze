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
from msprof_analyze.advisor.dataset.communication.communication_dataset import CommunicationDataset
from msprof_analyze.advisor.display.prompt.base_prompt import BasePrompt
from msprof_analyze.advisor.result.result import OptimizeResult
from msprof_analyze.advisor.result.item import OptimizeItem, OptimizeRecord
from msprof_analyze.prof_common.additional_args_manager import AdditionalArgsManager
from msprof_analyze.prof_common.file_manager import FileManager
from msprof_analyze.advisor.utils.utils import convert_to_float
from msprof_analyze.prof_common.additional_args_manager import AdditionalArgsManager

logger = get_logger()


class Statistic:
    def __init__(self, min_ratio, min_size, desc, type_):
        self.issue = False
        self.count = 0
        self.abnormal_count = 0
        self.abnormal_duration = 0
        self.abnormal_ratio = 0
        self.min_ratio = min_ratio
        self.min_size = min_size
        self.desc = desc
        self.type = type_

    def check_threshold(self):
        if self.count and self.abnormal_count:
            self.abnormal_ratio = self.abnormal_count / self.count
            if self.abnormal_ratio > self.min_ratio:
                self.issue = True
        return self.issue

    def process(self, hccl_info):
        info = dict()
        if self.type == "SDMA":
            info = hccl_info.sdma_info
        elif self.type == "RDMA":
            info = hccl_info.rdma_info
        if info.get('Transit Size(MB)', 0):
            packet_size = info.get('Transit Size(MB)', 0)
            if packet_size < self.min_size:
                self.abnormal_count += 1
                self.abnormal_duration += info.get('Transit Time(ms)', 0)
            self.count += 1

    def adapt(self, dst_headers: list, src_headers, datas: list):
        if not self.issue:
            return False
        dst_headers.extend(src_headers)
        datas.extend([self.count, self.abnormal_count, self.abnormal_ratio, self.abnormal_duration])
        self.desc = self.desc.format(
            abnormal_ratio=f"{round(self.abnormal_ratio, 4):.2%}",
            min_size=self.min_size,
            abnormal_time=round(self.abnormal_duration, 4))
        return True


class PacketChecker:
    def __init__(self, **kwargs):
        self.packet_issues = False
        self.desc = ""
        self.sdma_desc = ""
        self.rdma_desc = ""
        self.suggestions = []
        self.min_sdma_size = 0
        self.min_rdma_size = 0
        self.min_sdma_ratio = 0
        self.min_rdma_ratio = 0
        self.step_id = kwargs.get("step")
        self.stage = None
        self.packet_issues = False
        self._init_rule()
        self.sdma_statistic = Statistic(self.min_sdma_ratio, self.min_sdma_size, self.sdma_desc, "SDMA")
        self.rdma_statistic = Statistic(self.min_rdma_ratio, self.min_rdma_size, self.rdma_desc, "RDMA")
        self.small_packet_detail = []
        self.headers = []
        self.sdma_headers = ["SDMA total count", "Small SDMA count", "Small SDMA ratio", "Small SDMA duration(ms)"]
        self.rdma_headers = ["RDMA total count", "Small RDMA count", "Small RDMA ratio", "Small RDMA duration(ms)"]

    def check_packet(self, hccl_dataset: CommunicationDataset):
        for step_id, hccl_list in hccl_dataset.hccl_dict.items():
            if self.step_id and step_id != self.step_id:
                continue
            for hccl_info in hccl_list:
                self.sdma_statistic.process(hccl_info)
                self.rdma_statistic.process(hccl_info)
        self.sdma_statistic.check_threshold()
        self.rdma_statistic.check_threshold()
        if self.sdma_statistic.adapt(self.headers, self.sdma_headers, self.small_packet_detail):
            self.packet_issues = True
            self.desc += self.sdma_statistic.desc
        if self.rdma_statistic.adapt(self.headers, self.rdma_headers, self.small_packet_detail):
            self.packet_issues = True
            self.desc += self.rdma_statistic.desc

    def make_record(self, result: OptimizeResult):
        """
        make record for what and how to optimize
        """
        optimization_item = OptimizeItem(self.problem, self.desc, self.suggestions)
        result.add(OptimizeRecord(optimization_item))

        sub_table_name = BasePrompt.get_sub_table_name(self.problem, self.stage)

        result.add_detail(sub_table_name, headers=self.headers)
        result.add_detail(sub_table_name, detail=self.small_packet_detail)

    def make_render(self, html_render, add_render_list=True, **kwargs):
        priority = kwargs.get("priority")
        return html_render.render_template(key="communication",
                                           template_dir="templates",
                                           template_name="packet_analysis.html",
                                           desc=self.desc,
                                           solutions=self.solutions,
                                           headers=self.headers,
                                           data=self.small_packet_detail,
                                           priority_background_color=priority)

    def _init_rule(self):
        language = AdditionalArgsManager().language
        syncbn_rule_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))),
            "rules",
            language,
            "packet.yaml"
        )

        syncbn_rule = FileManager.read_yaml_file(syncbn_rule_path)
        self.problem = syncbn_rule.get("problem")
        self.desc = syncbn_rule.get("description")
        self.sdma_desc = syncbn_rule.get("sdma_problem")
        self.rdma_desc = syncbn_rule.get("rdma_problem")
        self.min_sdma_size = convert_to_float(syncbn_rule.get("min_sdma_size"))
        self.min_rdma_size = convert_to_float(syncbn_rule.get("min_rdma_size"))
        self.min_sdma_ratio = convert_to_float(syncbn_rule.get("min_sdma_ratio"))
        self.min_rdma_ratio = convert_to_float(syncbn_rule.get("min_rdma_ratio"))

        self.solutions = syncbn_rule.get("solutions")
        for solution in self.solutions:
            for key, val in solution.items():
                self.suggestions.append(f"{key}, {val.get('desc')}")
