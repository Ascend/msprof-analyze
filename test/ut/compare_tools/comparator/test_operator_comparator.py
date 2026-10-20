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

from msprof_analyze.compare_tools.compare_backend.comparator.operator_comparator import OperatorComparator


class MockBean:
    TABLE_NAME = "TEST"
    HEADERS = ["INDEX", "VALUE1", "VALUE2"]
    OVERHEAD = []

    def __init__(self, index, base_op, comparison_op):
        self._index = index
        self._base_op = base_op
        self._comparison_op = comparison_op

    @property
    def row(self):
        return [self._index + 1, 1, 1]


class TestOperatorComparator(unittest.TestCase):
    def test_compare_when_valid_data(self):
        data = [[1, 1]] * 3
        result = [[1, 1, 1], [2, 1, 1], [3, 1, 1]]
        comparator = OperatorComparator(data, MockBean)
        comparator._compare()
        self.assertEqual(comparator._rows, result)

    def test_compare_when_invalid_data(self):
        comparator = OperatorComparator({}, MockBean)
        comparator._compare()
        self.assertEqual(comparator._rows, [])
