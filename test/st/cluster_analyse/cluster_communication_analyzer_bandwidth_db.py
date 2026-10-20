# -------------------------------------------------------------------------
# This file is part of the MindStudio project.
# Copyright (c) 2025 Huawei Technologies Co.,Ltd.
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
class ClusterCommunicationAnalyzerBandwidthDb:
    def __init__(self, step=None, rank_id=None, hccl_op_name=None, group_name=None,
                 band_type=None, transit_size=None, transit_time=None, bandwidth=None, large_packet_ratio=None,
                 package_size=None, count=None, total_duration=None):
        self._step = step
        self._rank_id = rank_id
        self._hccl_op_name = hccl_op_name
        self._group_name = group_name
        self._band_type = band_type
        self._transit_size = transit_size
        self._transit_time = transit_time
        self._bandwidth = bandwidth
        self._large_packet_ratio = large_packet_ratio
        self._package_size = package_size
        self._count = count
        self._total_duration = total_duration

    @property
    def step(self):
        return self._step

    @step.setter
    def step(self, value):
        self._step = value

    @property
    def rank_id(self):
        return self._rank_id

    @rank_id.setter
    def rank_id(self, value):
        self._rank_id = value

    @property
    def hccl_op_name(self):
        return self._hccl_op_name

    @hccl_op_name.setter
    def hccl_op_name(self, value):
        self._hccl_op_name = value

    @property
    def group_name(self):
        return self._group_name

    @group_name.setter
    def group_name(self, value):
        self._group_name = value

    @property
    def band_type(self):
        return self._band_type

    @band_type.setter
    def band_type(self, value):
        self._band_type = value

    @property
    def transit_size(self):
        return self._transit_size

    @transit_size.setter
    def transit_size(self, value):
        self._transit_size = value

    @property
    def transit_time(self):
        return self._transit_time

    @transit_time.setter
    def transit_time(self, value):
        self._transit_time = value

    @property
    def bandwidth(self):
        return self._bandwidth

    @bandwidth.setter
    def bandwidth(self, value):
        self._bandwidth = value

    @property
    def large_packet_ratio(self):
        return self._large_packet_ratio

    @large_packet_ratio.setter
    def large_packet_ratio(self, value):
        self._large_packet_ratio = value

    @property
    def package_size(self):
        return self._package_size

    @package_size.setter
    def package_size(self, value):
        self._package_size = value

    @property
    def count(self):
        return self._count

    @count.setter
    def count(self, value):
        self._count = value

    @property
    def total_duration(self):
        return self._total_duration

    @total_duration.setter
    def total_duration(self, value):
        self._total_duration = value
