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
from unittest.mock import MagicMock, patch
from msprof_analyze.compare_tools.compare_backend.comparator.kernel_type_comparator import KernelTypeComparator
from msprof_analyze.compare_tools.compare_backend.compare_bean.origin_data_bean.op_stastic_bean import OpStatisticBean
from msprof_analyze.prof_common.constant import Constant


class TestKernelTypeComparator(unittest.TestCase):
    def setUp(self):
        self.mock_bean = MagicMock()
        self.mock_bean.row = {"key": "test", "base": 0, "comparison": 0, "diff": 0}

        self.base_kernels = {
            "kernel_type1": MagicMock(),
            "kernel_type2": MagicMock(),
            "kernel_type3": MagicMock()
        }

        self.comparison_kernels = {
            "kernel_type1": MagicMock(),
            "kernel_type2": MagicMock(),
            "kernel_type4": MagicMock()
        }

        self.origin_data = {
            Constant.BASE_DATA: self.base_kernels,
            Constant.COMPARISON_DATA: self.comparison_kernels
        }

    def test_compare_with_empty_origin_data(self):
        comparator = KernelTypeComparator({}, self.mock_bean)
        comparator._compare()
        self.assertEqual(comparator._rows, [])

    @patch('msprof_analyze.compare_tools.compare_backend.comparator.kernel_type_comparator.update_order_id')
    def test_compare_mixed_data_types(self, mock_update_order_id):
        op_statistic_bean = OpStatisticBean({"total_time": 100})
        magic_mock = MagicMock()

        origin_data = {
            Constant.BASE_DATA: {"type1": op_statistic_bean, "type2": magic_mock},
            Constant.COMPARISON_DATA: {"type1": op_statistic_bean, "type2": magic_mock}
        }

        comparator = KernelTypeComparator(origin_data, self.mock_bean)

        mock_bean_instance = MagicMock()
        mock_bean_instance.row = ["test", 0, 0, 0]
        self.mock_bean.return_value = mock_bean_instance
        comparator._compare()
        self.assertEqual(self.mock_bean.call_count, 2)
        mock_update_order_id.assert_called_once_with(comparator._rows)
