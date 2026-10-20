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
from unittest.mock import patch

from msprof_analyze.compare_tools.compare_backend.compare_bean.operator_statistic_bean import OperatorStatisticBean


class MockKernel:
    def __init__(self, device_dur):
        self.device_dur = device_dur


class TestOperatorStatisticBean(unittest.TestCase):
    name = "matmul"

    def test_row_when_valid_data(self):
        result = [None, self.name, 8.0, 2, 4.0, 1, -4.0, 0.5]
        with patch("msprof_analyze.compare_tools.compare_backend.utils.tree_builder.TreeBuilder.get_total_kernels",
                   return_value=[MockKernel(2000), MockKernel(2000)]):
            bean = OperatorStatisticBean(self.name, [1, 1], [1])
            self.assertEqual(bean.row, result)

    def test_row_when_invalid_base_data(self):
        result = [None, self.name, 0, 0, 4.0, 1, 4.0, float("inf")]
        with patch("msprof_analyze.compare_tools.compare_backend.utils.tree_builder.TreeBuilder.get_total_kernels",
                   return_value=[MockKernel(2000), MockKernel(2000)]):
            bean = OperatorStatisticBean(self.name, [], [1])
            self.assertEqual(bean.row, result)

    def test_row_when_invalid_comparison_data(self):
        result = [None, self.name, 8.0, 2, 0, 0, -8.0, 0]
        with patch("msprof_analyze.compare_tools.compare_backend.utils.tree_builder.TreeBuilder.get_total_kernels",
                   return_value=[MockKernel(2000), MockKernel(2000)]):
            bean = OperatorStatisticBean(self.name, [1, 1], [])
            self.assertEqual(bean.row, result)
