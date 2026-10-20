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

from msprof_analyze.compare_tools.compare_backend.comparator.communication_comparator import CommunicationComparator
from msprof_analyze.compare_tools.compare_backend.compare_bean.communication_bean import CommunicationBean


class TestCommunicationComparator(unittest.TestCase):
    ORIGIN_DATA = {
        "base_data": {
            "allreduce": {"comm_list": [0.5, 7], "comm_task": {"Notify Wait": [1, 2, 3], "Memcpy": [5]}},
            "allgather": {"comm_list": [1, 4], "comm_task": {}}
        },
        "comparison_data": {
            "allreduce": {"comm_list": [4, 5], "comm_task": {"Notify Wait": [1, 2, 3]}},
            "gather": {"comm_list": [1], "comm_task": {"Notify Wait": [1, 2, 3]}}
        }
    }
    RESULT_DATA = [[1, 'allreduce', None, 2, 7.5, 3.75, 7, 0.5, 'allreduce', None, 2, 9, 4.5, 5, 4, 1.5, 1.2],
                   [2, '|', 'Notify Wait', 3, 6, 2.0, 3, 1, '|', 'Notify Wait', 3, 6, 2.0, 3, 1, None, None],
                   [3, '|', 'Memcpy', 1, 5, 5.0, 5, 5, None, None, None, 0, None, None, None, None, None],
                   [4, 'allgather', None, 2, 5, 2.5, 4, 1, None, None, None, 0, None, None, None, -5, 0.0],
                   [5, None, None, None, 0, None, None, None, 'gather', None, 1, 1, 1.0, 1, 1, 1, float('inf')],
                   [6, None, None, None, 0, None, None, None, '|', 'Notify Wait', 3, 6, 2.0, 3, 1, None, None]]

    def test_compare_when_valid_data(self):
        comm_comparator = CommunicationComparator(self.ORIGIN_DATA, CommunicationBean)
        comm_comparator._compare()
        self.assertEqual(comm_comparator._rows, self.RESULT_DATA)

    def test_compare_when_invalid_data(self):
        comm_comparator = CommunicationComparator({}, CommunicationBean)
        comm_comparator._compare()
        self.assertEqual(comm_comparator._rows, [])

    def test_compare_when_invalid_base_data(self):
        data = {"comparison_data": {"allreduce": {"comm_list": [4, 5], "comm_task": {}}}}
        result = [[1, None, None, None, 0, None, None, None, 'allreduce', None, 2, 9, 4.5, 5, 4, 9, float('inf')]]
        comm_comparator = CommunicationComparator(data, CommunicationBean)
        comm_comparator._compare()
        self.assertEqual(comm_comparator._rows, result)
