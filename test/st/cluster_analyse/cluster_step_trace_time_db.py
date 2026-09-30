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
"""Cluster step trace time class """


class ClusterStepTraceTimeDb:
    def __init__(self,
                 step=None,
                 data_type=None,
                 index=None,
                 computing=None,
                 communication_not_overlapped=None,
                 overlapped=None,
                 communication=None,
                 free=None,
                 stage=None,
                 bubble=None,
                 communication_not_overlapped_and_exclude_receive=None,
                 preparing=None,
                 dp_index=None,
                 pp_index=None,
                 tp_index=None):
        self._step = step
        self._type = data_type
        self._index = index
        self._computing = computing
        self._communication_not_overlapped = communication_not_overlapped
        self._overlapped = overlapped
        self._communication = communication
        self._free = free
        self._stage = stage
        self._bubble = bubble
        self._communication_not_overlapped_and_exclude_receive = communication_not_overlapped_and_exclude_receive
        self._preparing = preparing
        self._dp_index = dp_index
        self._pp_index = pp_index
        self._tp_index = tp_index

    @property
    def step(self):
        return self._step

    @step.setter
    def step(self, value):
        self._step = value

    @property
    def type(self):
        return self._type

    @type.setter
    def type(self, value):
        self._type = value

    @property
    def index(self):
        return self._index

    @index.setter
    def index(self, value):
        self._index = value

    @property
    def computing(self):
        return self._computing

    @computing.setter
    def computing(self, value):
        self._computing = value

    @property
    def communication_not_overlapped(self):
        return self._communication_not_overlapped

    @communication_not_overlapped.setter
    def communication_not_overlapped(self, value):
        self._communication_not_overlapped = value

    @property
    def overlapped(self):
        return self._overlapped

    @overlapped.setter
    def overlapped(self, value):
        self._overlapped = value

    @property
    def communication(self):
        return self._communication

    @communication.setter
    def communication(self, value):
        self._communication = value

    @property
    def free(self):
        return self._free

    @free.setter
    def free(self, value):
        self._free = value

    @property
    def stage(self):
        return self._stage

    @stage.setter
    def stage(self, value):
        self._stage = value

    @property
    def bubble(self):
        return self._bubble

    @bubble.setter
    def bubble(self, value):
        self._bubble = value

    @property
    def communication_not_overlapped_and_exclude_receive(self):
        return self._communication_not_overlapped_and_exclude_receive

    @communication_not_overlapped_and_exclude_receive.setter
    def communication_not_overlapped_and_exclude_receive(self, value):
        self._communication_not_overlapped_and_exclude_receive = value

    @property
    def preparing(self):
        return self._preparing

    @preparing.setter
    def preparing(self, value):
        self._preparing = value

    @property
    def dp_index(self):
        return self._dp_index

    @dp_index.setter
    def dp_index(self, value):
        self._dp_index = value

    @property
    def pp_index(self):
        return self._pp_index

    @pp_index.setter
    def pp_index(self, value):
        self._pp_index = value

    @property
    def tp_index(self):
        return self._tp_index

    @tp_index.setter
    def tp_index(self, value):
        self._tp_index = value
