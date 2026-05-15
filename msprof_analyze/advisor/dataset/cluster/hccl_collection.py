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
"""
hccl info
"""
from msprof_analyze.prof_common.logger import get_logger

import pandas as pd

logger = get_logger()


class HcclInfo:
    def __init__(self, group: str, step: str, rank: str, op_name: str,
                 start_time: float, elapse_time: float, sdma_info: dict, rdma_info: dict):
        self._group = group
        self._step = step
        self._rank = rank
        self._name = op_name
        self._ts = start_time
        self._elapse_time = elapse_time
        self._sdma_info = sdma_info
        self._rdma_info = rdma_info

    @property
    def group(self):
        return self._group

    @property
    def step(self):
        return self._step

    @property
    def rank(self):
        return self._rank

    @property
    def name(self):
        return self._name

    @property
    def rdma_info(self):
        return self._rdma_info

    @property
    def sdma_info(self):
        return self._sdma_info

    @property
    def elapse_time(self):
        return self._elapse_time

    @property
    def ts(self):
        return self._ts

    @staticmethod
    def get_communication_info(rank_dict: dict, name: str):
        communication_bandwidth_info = rank_dict.get('Communication Bandwidth Info', dict())
        return communication_bandwidth_info.get(name, dict())

    @staticmethod
    def get_communication_time_info(rank_dict: dict, name: str):
        communication_time_info = rank_dict.get('Communication Time Info', dict())
        return communication_time_info.get(name, 0)

    @classmethod
    def construct_instance_from_dict(cls, group: str, step: str, rank: str, op: str, rank_dict: dict):
        return cls(group, step, rank, op.split("@")[0],
                   HcclInfo.get_communication_time_info(rank_dict, "Start Timestamp(us)"),
                   HcclInfo.get_communication_time_info(rank_dict, "Elapse Time(ms)"),
                   HcclInfo.get_communication_info(rank_dict, "SDMA"),
                   HcclInfo.get_communication_info(rank_dict, "RDMA")
                   )

    def get_rdma_transmit_time(self):
        return self.rdma_info.get('Transit Time(ms)', 0)

    def get_rdma_transit_size(self):
        return self.rdma_info.get('Transit Size(MB)', 0)

    def get_rdma_bandwidth(self):
        return self.rdma_info.get('Bandwidth(GB/s)', 0)

