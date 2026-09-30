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


from msprof_analyze.cluster_analyse.common_func.table_constant import TableConstant


class CommunicationBandwidthBean:
    def __init__(self, single_op: dict):
        self._rank_id = single_op.get(TableConstant.RANK_ID, '')
        self._step_id = single_op.get(TableConstant.STEP, '')
        self._group_name = single_op.get(TableConstant.GROUP_NAME, '')
        self._hccl_op_name = single_op.get(TableConstant.HCCL_OP_NAME, '')
        self._transport_type = single_op.get(TableConstant.TRANSPORT_TYPE)
        self._transit_size = single_op.get(TableConstant.TRANSIT_SIZE, 0.0)
        self._transit_time = single_op.get(TableConstant.TRANSIT_TIME, 0.0)
        self._bandwidth = single_op.get(TableConstant.BANDWIDTH, 0.0)
        self._large_packet_ratio = single_op.get(TableConstant.LARGE_PACKET_RATIO, 0)
        self._package_size = single_op.get(TableConstant.PACKAGE_SIZE, 0.0)
        self._count = single_op.get(TableConstant.COUNT, 0.0)
        self._total_duration = single_op.get(TableConstant.TOTAL_DURATION, 0.0)

    def __add__(self, other):
        res = {
            TableConstant.RANK_ID: self._rank_id,
            TableConstant.STEP: self._step_id,
            TableConstant.GROUP_NAME: self._group_name,
            TableConstant.HCCL_OP_NAME: self._hccl_op_name,
            TableConstant.TRANSPORT_TYPE: self._transport_type,
            TableConstant.TRANSIT_SIZE: self._transit_size,
            TableConstant.TRANSIT_TIME: self._transit_time,
            TableConstant.BANDWIDTH: self._bandwidth,
            TableConstant.LARGE_PACKET_RATIO: 0,
            TableConstant.PACKAGE_SIZE: self._package_size,
            TableConstant.COUNT: self._count + other._count,
            TableConstant.TOTAL_DURATION: self._total_duration + other._total_duration,
        }
        return CommunicationBandwidthBean(res)

    @property
    def rank_id(self):
        return self._rank_id

    @property
    def step_id(self):
        return self._step_id

    @property
    def transport_type(self):
        return self._transport_type

    @property
    def package_size(self):
        return self._package_size

    @property
    def transit_time(self):
        return self._transit_time

    @property
    def transit_size(self):
        return self._transit_size

    @property
    def group_name(self):
        return self._group_name

    @property
    def hccl_op_name(self):
        return self._hccl_op_name

    def set_transit_size(self, value: float):
        self._transit_size = value

    def set_transit_time(self, value: float):
        self._transit_time = value

    def set_bandwidth(self, value: float):
        self._bandwidth = value

    def set_group_name(self, value: str):
        self._group_name = value

    def convert_output(self):
        return [
            self._step_id,
            self._rank_id,
            self._hccl_op_name,
            self._group_name,
            self._transport_type,
            self._transit_size,
            self._transit_time,
            round(self._bandwidth, 4),
            self._large_packet_ratio,
            self._package_size,
            self._count,
            self._total_duration,
        ]
