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
from msprof_analyze.compare_tools.compare_backend.comparator.kernel_compare_comparator import KernelCompareComparator
from msprof_analyze.prof_common.constant import Constant


class TestKernelCompareComparator(unittest.TestCase):
    def setUp(self):
        self.mock_bean = MagicMock()
        self.mock_bean.row = {"type_shape": "test", "shape": "test", "data": []}

        self.base_kernels = {
            "type1": {
                "shape1": [("op1", 10.0), ("op2", 20.0)],
                "shape2": [("op3", 30.0)]
            },
            "type2": {
                "shape3": [("op4", 40.0)]
            }
        }

        self.comparison_kernels = {
            "type1": {
                "shape1": [("op1", 15.0), ("op2", 25.0)],
                "shape2": [("op3", 35.0)],
                "shape4": [("op5", 50.0)]
            },
            "type3": {
                "shape5": [("op6", 60.0)]
            }
        }

        self.origin_data = {
            Constant.BASE_DATA: self.base_kernels,
            Constant.COMPARISON_DATA: self.comparison_kernels
        }

    def test_aggregated_kernel_by_type_and_shape(self):
        test_kernels = {
            "type1": {
                "shape1": [("op1", 10.0), ("op2", 20.0)],
                "shape2": [("op3", 30.0)]
            }
        }

        result = KernelCompareComparator._aggregated_kernel_by_type_and_shape(test_kernels)

        self.assertEqual(len(result), 2)
        self.assertIn("type1shape1", result)
        type_shape1_data = result["type1shape1"]
        self.assertEqual(type_shape1_data[0], "type1")
        type_shape2_data = result["type1shape2"]
        self.assertEqual(type_shape2_data[0], "type1")
        self.assertEqual(type_shape2_data[1], "shape2")

    def test_aggregated_kernel_empty_data(self):
        test_kernels = {}
        result = KernelCompareComparator._aggregated_kernel_by_type_and_shape(test_kernels)
        self.assertEqual(result, {})

    @patch('msprof_analyze.compare_tools.compare_backend.comparator.kernel_compare_comparator.update_order_id')
    def test_compare_normal_case(self, mock_update_order_id):
        comparator = KernelCompareComparator(self.origin_data, self.mock_bean)

        mock_bean_instance = MagicMock()
        mock_bean_instance.row = {"test": "row_data"}
        self.mock_bean.return_value = mock_bean_instance
        comparator._compare()
        self.assertEqual(self.mock_bean.call_count, 5)
        mock_update_order_id.assert_called_once_with(comparator._rows)
        self.assertEqual(len(comparator._rows), 5)

    @patch('msprof_analyze.compare_tools.compare_backend.comparator.kernel_compare_comparator.update_order_id')
    def test_compare_bean_creation_parameters(self, mock_update_order_id):
        comparator = KernelCompareComparator(self.origin_data, self.mock_bean)
        call_args_list = []

        def mock_bean_side_effect(*args, **kwargs):
            call_args_list.append(args)
            mock_instance = MagicMock()
            mock_instance.row = {"test": "row_data"}
            return mock_instance

        self.mock_bean.side_effect = mock_bean_side_effect
        comparator._compare()
        self.assertEqual(len(call_args_list), 5)
        base_data, comparison_data = call_args_list[0]
        self.assertEqual(len(base_data), 6)
        self.assertEqual(base_data[0], "type1")
