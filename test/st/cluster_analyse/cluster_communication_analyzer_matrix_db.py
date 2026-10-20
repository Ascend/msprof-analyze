# -------------------------------------------------------------------------
# This file is part of the MindStudio project.
# Copyright (c) 2026 Huawei Technologies Co.,Ltd.
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
"""Cluster communication matrix db class """


class ClusterCommunicationAnalyzerMatrixDb:
    def __init__(self,
                 step=None,
                 hccl_op_name=None,
                 group_name=None,
                 src_rank=None,
                 dst_rank=None,
                 transport_type=None,
                 op_name=None,
                 transit_size=None,
                 transit_time=None,
                 bandwidth=None):
        self._step = step
        self._hccl_op_name = hccl_op_name
        self._group_name = group_name
        self._src_rank = src_rank
        self._dst_rank = dst_rank
        self._transit_size = transit_size
        self._transit_time = transit_time
        self._bandwidth = bandwidth
        self._transport_type = transport_type
        self._op_name = op_name

    @property
    def step(self):
        return self._step

    @step.setter
    def step(self, value):
        self._step = value

    @property
    def hccl_op_name(self):
        return self._hccl_op_name

    @hccl_op_name.setter
    def hccl_op_name(self, value):
        self._hccl_op_name = value

    # group_name property
    @property
    def group_name(self):
        return self._group_name

    @group_name.setter
    def group_name(self, value):
        self._group_name = value

    @property
    def src_rank(self):
        return self._src_rank

    @src_rank.setter
    def src_rank(self, value):
        self._src_rank = value

    @property
    def dst_rank(self):
        return self._dst_rank

    @dst_rank.setter
    def dst_rank(self, value):
        self._dst_rank = value

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
    def transport_type(self):
        return self._transport_type

    @transport_type.setter
    def transport_type(self, value):
        self._transport_type = value

    # op_name property
    @property
    def op_name(self):
        return self._op_name

    @op_name.setter
    def op_name(self, value):
        self._op_name = value
