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
from abc import ABC, abstractmethod


class BaseComparator(ABC):
    def __init__(self, origin_data: any, bean: any):
        self._sheet_name = bean.TABLE_NAME
        self._headers = bean.HEADERS
        self._overhead = bean.OVERHEAD
        self._origin_data = origin_data
        self._bean = bean
        self._rows = []

    def generate_data(self) -> dict:
        '''
        generate one sheet(table) data
        type: dict
        sheet name as the dict key
        '''
        self._compare()
        return {self._sheet_name: {"headers": self._headers, "rows": self._rows, "overhead": self._overhead}}

    @abstractmethod
    def _compare(self):
        raise NotImplementedError("Function _compare need to be implemented.")
