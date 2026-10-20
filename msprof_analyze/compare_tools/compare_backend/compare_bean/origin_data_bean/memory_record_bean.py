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
from msprof_analyze.compare_tools.compare_backend.utils.common_func import convert_to_float


class MemoryRecordBean:
    __slots__ = ['_data', '_total_reserved_mb']

    def __init__(self, data: dict):
        self._data = data
        self._total_reserved_mb = 0.0
        self.init()

    @property
    def total_reserved_mb(self) -> float:
        return convert_to_float(self._total_reserved_mb)

    def init(self):
        self._total_reserved_mb = self._data.get("Total Reserved(MB)", 0)
