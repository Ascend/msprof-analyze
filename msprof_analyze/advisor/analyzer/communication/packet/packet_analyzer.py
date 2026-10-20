# -------------------------------------------------------------------------
# This file is part of the MindStudio project.
# Copyright (c) 2024 Huawei Technologies Co.,Ltd.
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
from msprof_analyze.prof_common.logger import get_logger

from msprof_analyze.advisor.analyzer.communication.base_communication_analyzer import BaseCommunicationAnalyzer
from msprof_analyze.advisor.analyzer.communication.packet.packet_checker import PacketChecker
from msprof_analyze.advisor.display.html.priority_background_color import PriorityBackgroundColor
from msprof_analyze.advisor.display.html.render import HTMLRender
from msprof_analyze.advisor.dataset.communication.communication_dataset import CommunicationDataset
from msprof_analyze.advisor.result.result import OptimizeResult

logger = get_logger()


class PacketAnalyzer(BaseCommunicationAnalyzer):
    dataset_cls_list = [CommunicationDataset]
    requires_cluster_dataset = False

    def __init__(self, collection_path, n_processes: int = 1, **kwargs) -> None:
        super().__init__(collection_path, n_processes, **kwargs)
        key = CommunicationDataset.get_key()
        self.dataset = self.get_first_data_by_key(self.dataset_list, key)
        self.result = OptimizeResult()
        self.html_render = HTMLRender()
        self.html = None

    @BaseCommunicationAnalyzer.check_data((CommunicationDataset.get_key(),))
    def optimize(self, **kwargs):
        add_render_list = kwargs.get("add_render_list", True)
        if not hasattr(self.dataset, "hccl_dict"):
            return self.result
        packet_checker = PacketChecker(**kwargs)
        packet_checker.check_packet(self.dataset)
        if not packet_checker.packet_issues:
            return self.result
        packet_checker.make_record(self.result)
        self.html = packet_checker.make_render(self.html_render, add_render_list, priority=self.get_priority())
        return self.result

    def get_priority(self, max_mem_op_dur=None):
        # 提升1% ~ 3%
        return PriorityBackgroundColor.low
