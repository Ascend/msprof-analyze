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
import unittest

from msprof_analyze.compare_tools.compare_backend.compare_bean.communication_bean import CommunicationBean


class TestCommunicationBean(unittest.TestCase):
    def test_rows_when_valid_data(self):
        base_data = {"comm_list": [0.5, 7], "comm_task": {"Notify Wait": [1, 2, 3]}}
        comparison_data = {"comm_list": [1, 3, 5], "comm_task": {"Notify Wait": [1, 2, 3], "Memcpy": [5]}}
        result = [[None, 'allreduce', None, 2, 7.5, 3.75, 7, 0.5, 'allreduce', None, 3, 9, 3.0, 5, 1, 1.5, 1.2],
                  [None, '|', 'Notify Wait', 3, 6, 2.0, 3, 1, '|', 'Notify Wait', 3, 6, 2.0, 3, 1, None, None],
                  [None, None, None, None, 0, None, None, None, '|', 'Memcpy', 1, 5, 5.0, 5, 5, None, None]]

        comm = CommunicationBean("allreduce", base_data, comparison_data)
        self.assertEqual(comm.rows, result)
