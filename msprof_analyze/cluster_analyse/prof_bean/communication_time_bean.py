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


class CommunicationTimeBean:
    def __init__(self, single_op: dict):
        self._rank_id = single_op.get(TableConstant.RANK_ID, '')
        self._step_id = single_op.get(TableConstant.STEP, '')
        self._group_name = single_op.get(TableConstant.GROUP_NAME, '')
        self._hccl_op_name = single_op.get(TableConstant.HCCL_OP_NAME, '')
        self._start_time = single_op.get(TableConstant.START_TIMESTAMP, 0)
        self._elapsed_time = single_op.get(TableConstant.ELAPSED_TIME, 0.0)
        self._transit_time = single_op.get(TableConstant.TRANSIT_TIME, 0.0)
        self._wait_time = single_op.get(TableConstant.WAIT_TIME, 0.0)
        self._synchronization_time = single_op.get(TableConstant.SYNCHRONIZATION_TIME, 0.0)
        self._idle_time = single_op.get(TableConstant.IDLE_TIME, 0.0)
        self._sync_ratio = 0
        self._wait_ratio = 0

    def __add__(self, other):
        res = {
            TableConstant.RANK_ID: self._rank_id,
            TableConstant.STEP: self._step_id,
            TableConstant.GROUP_NAME: self._group_name,
            TableConstant.HCCL_OP_NAME: self._hccl_op_name,
            TableConstant.START_TIMESTAMP: 0,
            TableConstant.ELAPSED_TIME: self._elapsed_time + other._elapsed_time,
            TableConstant.TRANSIT_TIME: self._transit_time + other._transit_time,
            TableConstant.WAIT_TIME: self._wait_time + other._wait_time,
            TableConstant.SYNCHRONIZATION_TIME: self._synchronization_time + other._synchronization_time,
            TableConstant.IDLE_TIME: self._idle_time + other._idle_time,
        }
        return CommunicationTimeBean(res)

    @property
    def rank_id(self):
        return self._rank_id

    @property
    def step_id(self):
        return self._step_id

    @property
    def group_name(self):
        return self._group_name

    def compute_ratio(self):
        total_duration = self._transit_time + self._synchronization_time
        self._sync_ratio = self._synchronization_time / total_duration if total_duration != 0 else 0
        total_duration = self._transit_time + self._wait_time
        self._wait_ratio = self._wait_time / total_duration if total_duration != 0 else 0

    def convert_output(self):
        return [
            self._step_id,
            self._rank_id,
            self._hccl_op_name,
            self._group_name,
            self._start_time,
            self._elapsed_time,
            self._transit_time,
            self._wait_time,
            self._synchronization_time,
            self._idle_time,
            round(self._sync_ratio, 4),
            round(self._wait_ratio, 4),
        ]
