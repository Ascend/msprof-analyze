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
from typing import Dict, List
from collections import defaultdict
from msprof_analyze.advisor.dataset.cluster.cluster_dataset import ClusterCommunicationDataset
from msprof_analyze.advisor.display.prompt.base_prompt import BasePrompt
from msprof_analyze.advisor.result.result import OptimizeResult
from msprof_analyze.advisor.result.item import OptimizeItem, OptimizeRecord
from msprof_analyze.prof_common.additional_args_manager import AdditionalArgsManager
from msprof_analyze.prof_common.file_manager import FileManager
from msprof_analyze.advisor.dataset.cluster.hccl_collection import HcclInfo

logger = get_logger()


class GroupStatistic:
    def __init__(self, min_transmission_time):
        self.retransmission_issue = False
        self.abnormal_op_dict: Dict[str, List] = dict()

    def add_op(self, op_name: str, hccl_info: HcclInfo):
        if self.abnormal_op_dict.get(op_name) is None:
            self.abnormal_op_dict.setdefault(op_name, [])
        self.abnormal_op_dict.get(op_name).append([hccl_info.group, op_name, hccl_info.step, hccl_info.rank,
                                                   hccl_info.get_rdma_transit_size(),
                                                   hccl_info.get_rdma_transmit_time(), hccl_info.get_rdma_bandwidth()])


class CommunicationRetransmissionChecker:
    def __init__(self, **kwargs):
        self.rdma_issues = False
        self.desc = ""
        self.sdma_desc = ""
        self.rdma_desc = ""
        self.suggestions = []
        self.abnormal_group_count = 0
        self.abnormal_rdma_list = []
        self.step_id = kwargs.get("step")
        self.stage = None
        self.group_statistics = defaultdict(GroupStatistic)
        self.headers = [
            "Communication group",
            "Op name",
            "Step id",
            "Rank id",
            "RDMA transmit size(MB)",
            "RDMA transmit time(ms)",
            "RDMA bandwidth",
        ]
        self._init_rule()

    def check_possible_retransmission_occurrence(self, hccl_list: List[HcclInfo]):
        min_elapse_time = min(hccl.elapse_time for hccl in hccl_list)
        max_transit_time = max(hccl.rdma_info.get('Transit Time(ms)', 0) for hccl in hccl_list)
        if min_elapse_time < self.min_retransmission_time:  # 检测是否是卡间不同步问题，而不是重传
            return False
        return max_transit_time > self.min_retransmission_time

    def check_retransmission(self, hccl_dataset: ClusterCommunicationDataset):
        """
        :Param event_dataset: dataset of timeline event
        """
        for group_name, hccl_group_dict in hccl_dataset.hccl_dict.items():
            for op_name, hccl_op_dict in hccl_group_dict.items():
                for step_id, hccl_list in hccl_op_dict.items():
                    if self.step_id and step_id != self.step_id:  # 传输指定step（self.step_id）情况下，非目标step跳过
                        continue
                    if not self.check_possible_retransmission_occurrence(hccl_list):
                        continue
                    self.rdma_issues = True
                    if self.group_statistics.get(group_name) is None:
                        self.group_statistics.setdefault(group_name, GroupStatistic(self.min_retransmission_time))
                        self.abnormal_group_count += 1
                    for hccl_info in hccl_list:
                        if hccl_info.rdma_info.get('Transit Size(MB)', 0):
                            transit_time = hccl_info.rdma_info.get('Transit Time(ms)', 0)
                            if transit_time > self.min_retransmission_time:
                                self.group_statistics.get(group_name).add_op(op_name, hccl_info)
        if self.rdma_issues:
            self.desc = self.desc.format(group_count=self.abnormal_group_count)
            for _, group_statistic in self.group_statistics.items():
                for _, op_list in group_statistic.abnormal_op_dict.items():
                    for op in op_list:
                        self.abnormal_rdma_list.append(op)

    def make_record(self, result: OptimizeResult):
        """
        make record for what and how to optimize
        """
        optimization_item = OptimizeItem(self.problem, self.desc, self.suggestions)
        result.add(OptimizeRecord(optimization_item))

        sub_table_name = BasePrompt.get_sub_table_name(self.problem, self.stage)
        result.add_detail(sub_table_name, headers=self.headers)

        for row in self.abnormal_rdma_list:
            result.add_detail(sub_table_name, detail=row)

    def make_render(self, html_render, add_render_list=True):
        return html_render.render_template(key="cluster",
                                           template_dir="templates",
                                           template_name="communication_retransmission_analysis.html",
                                           desc=self.desc,
                                           solutions=self.solutions,
                                           headers=self.headers,
                                           data=self.abnormal_rdma_list
                                           )

    def _init_rule(self):
        language = AdditionalArgsManager().language
        syncbn_rule_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(__file__)))),
            "rules",
            language,
            "rdma_analysis.yaml"
        )

        syncbn_rule = FileManager.read_yaml_file(syncbn_rule_path)
        self.problem = syncbn_rule.get("problem")
        self.desc = syncbn_rule.get("description")
        self.min_retransmission_time = syncbn_rule.get("min_retransmission_time")

        self.solutions = syncbn_rule.get("solutions")
        for solution in self.solutions:
            for key, val in solution.items():
                self.suggestions.append(f"{key}, {val.get('desc')}")
