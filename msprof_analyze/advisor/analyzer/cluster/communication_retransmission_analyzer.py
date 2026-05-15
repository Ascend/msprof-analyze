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

from msprof_analyze.advisor.analyzer.base_analyzer import BaseAnalyzer
from msprof_analyze.advisor.result.result import OptimizeResult
from msprof_analyze.advisor.analyzer.cluster.communication_retransmission_checker import \
    CommunicationRetransmissionChecker
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
