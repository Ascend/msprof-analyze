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
from msprof_analyze.compare_tools.compare_backend.comparator.base_comparator import BaseComparator
from msprof_analyze.compare_tools.compare_backend.compare_bean.communication_bean import CommunicationBean
from msprof_analyze.compare_tools.compare_backend.utils.common_func import update_order_id

from msprof_analyze.prof_common.constant import Constant


class CommunicationComparator(BaseComparator):
    def __init__(self, origin_data: dict, bean: any):
        super().__init__(origin_data, bean)

    def _compare(self):
        base_data = self._origin_data.get(Constant.BASE_DATA, {})
        comparison_data = self._origin_data.get(Constant.COMPARISON_DATA, {})
        for comm_name, comm_data in base_data.items():
            comparison_comm_data = comparison_data.pop(comm_name, {})
            self._rows.extend(CommunicationBean(comm_name, comm_data, comparison_comm_data).rows)
        for comm_name, comm_data in comparison_data.items():
            self._rows.extend(CommunicationBean(comm_name, {}, comm_data).rows)
        update_order_id(self._rows)
