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
from decimal import Decimal

from msprof_analyze.compare_tools.compare_backend.compare_bean.origin_data_bean.trace_event_bean import TraceEventBean
from msprof_analyze.prof_common.constant import Constant


class KernelEvent:
    __slots__ = ['_event', '_device_type']

    def __init__(self, event: TraceEventBean, device_type: str):
        self._event = event
        self._device_type = device_type

    @property
    def kernel_name(self) -> str:
        return self._event.name

    @property
    def device_dur(self) -> float:
        return self._event.dur

    @property
    def task_id(self) -> int:
        return self._event.task_id

    @property
    def task_type(self) -> str:
        return self._event.task_type

    @property
    def kernel_details(self):
        if self._device_type == Constant.GPU:
            return f"{self.kernel_name} [duration: {self.device_dur}]\n"
        input_shape = f", [input shapes: {self._event.input_shapes}]" if self._event.input_shapes else ""
        return f"{self.kernel_name}, {self.task_id}, {self.task_type}{input_shape} [duration: {self.device_dur}]\n"


class MemoryEvent:
    def __init__(self, event: dict):
        self._event = event
        self._name = ""
        self._size = 0.0
        self._ts = Decimal(0)
        self._release_time = Decimal(0)
        self._allocation_time = Decimal(0)
        self._duration = 0.0
        self.init()

    @property
    def size(self) -> float:
        return self._size

    @property
    def duration(self) -> float:
        return self._duration

    @property
    def memory_details(self) -> str:
        name = self._event.get(Constant.NAME, "") or self._name
        return (
            f"{name}, ({self._allocation_time}, {self._release_time}), "
            f"[duration: {self._duration}], [size: {self._size}]\n"
        )

    @property
    def is_torch_op(self) -> bool:
        return False

    @property
    def start_time(self) -> Decimal:
        return self._ts

    def set_name(self, name: str):
        self._name = name

    def init(self):
        self._size = self._event.get(Constant.SIZE, 0)
        self._ts = self._event.get(Constant.TS, 0)
        self._release_time = self._event.get(Constant.RELEASE_TIME)
        self._allocation_time = self._event.get(Constant.ALLOCATION_TIME)
        if not self._release_time or not self._allocation_time:
            self._duration = 0.0
        else:
            self._duration = float(self._release_time - self._allocation_time)
