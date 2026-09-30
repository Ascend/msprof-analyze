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

from msprof_analyze.compare_tools.compare_backend.utils.common_func import convert_to_float, convert_to_decimal


class OperatorMemoryBean:
    __slots__ = ['_data', '_name', '_size', '_allocation_time', '_release_time']
    NA = "N/A"

    def __init__(self, data: dict):
        self._data = data.copy()
        self._name = ""
        self._size = 0.0
        self._allocation_time = Decimal(0)
        self._release_time = Decimal(0)
        self.init()

    @property
    def name(self) -> str:
        return self._name

    @property
    def size(self) -> float:
        return convert_to_float(self._size)

    @property
    def allocation_time(self) -> Decimal:
        if not self._allocation_time or self._allocation_time == self.NA:
            return Decimal(0)
        return convert_to_decimal(self._allocation_time)

    @property
    def release_time(self) -> Decimal:
        if not self._release_time or self._release_time == self.NA:
            return Decimal(0)
        return convert_to_decimal(self._release_time)

    def init(self):
        self._name = self._data.get("Name", "")
        self._size = self._data.get("Size(KB)", 0)
        self._allocation_time = self._data.get("Allocation Time(us)", 0)
        self._release_time = self._data.get("Release Time(us)", 0)

    def is_cann_op(self):
        return "cann::" in self._name
