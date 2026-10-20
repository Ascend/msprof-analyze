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

from msprof_analyze.advisor.analyzer.base_analyzer import BaseAnalyzer
from msprof_analyze.advisor.result.result import OptimizeResult
from msprof_analyze.advisor.analyzer.cluster.communication_retransmission_checker import (
    CommunicationRetransmissionChecker,
)
from msprof_analyze.advisor.display.html.render import HTMLRender
from msprof_analyze.advisor.dataset.cluster.cluster_dataset import ClusterCommunicationDataset

logger = get_logger()


class RDMARetransmissionAnalyzer(BaseAnalyzer):
    dataset_cls_list = [ClusterCommunicationDataset]

    def __init__(self, collection_path, n_processes: int = 1, **kwargs) -> None:
        super().__init__(collection_path, n_processes, **kwargs)
        key = ClusterCommunicationDataset.get_key()
        self.dataset = self.get_first_data_by_key(self.dataset_list, key)
        self.result = OptimizeResult()
        self.html_render = HTMLRender()
        self.html = None

    @BaseAnalyzer.check_data((ClusterCommunicationDataset.get_key(),))
    def optimize(self, **kwargs):
        add_render_list = kwargs.get("add_render_list", True)
        rdma_checker = CommunicationRetransmissionChecker(**kwargs)
        rdma_checker.check_retransmission(self.dataset)
        if not rdma_checker.rdma_issues:
            return self.result
        rdma_checker.make_record(self.result)
        self.html = rdma_checker.make_render(self.html_render, add_render_list)
        return self.result

    def get_priority(self, max_mem_op_dur):
        raise NotImplementedError
