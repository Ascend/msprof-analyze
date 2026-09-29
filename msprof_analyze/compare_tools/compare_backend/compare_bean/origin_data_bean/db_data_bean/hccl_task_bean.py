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
from decimal import Decimal

from msprof_analyze.prof_common.constant import Constant
from msprof_analyze.compare_tools.compare_backend.utils.common_func import convert_to_decimal


class HcclTaskBean:
    def __init__(self, data):
        self._data = data

    @property
    def name(self):
        return self._data.get("taskName", "")

    @property
    def dur(self):
        return self._data.get("Duration", 0) / Constant.NS_TO_US

    @property
    def start_time(self) -> Decimal:
        return convert_to_decimal(self._data.get("startNs", 0)) / Constant.NS_TO_US

    @property
    def end_time(self) -> Decimal:
        return convert_to_decimal(self._data.get("endNs", 0)) / Constant.NS_TO_US

    @property
    def task_id(self):
        return self._data.get("opId", "")

    @property
    def group_name(self):
        return self._data.get("GroupName", "")

    @property
    def plane_id(self):
        return self._data.get("planeId", "")
