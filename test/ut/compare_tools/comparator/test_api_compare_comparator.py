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
from msprof_analyze.compare_tools.compare_backend.comparator.api_compare_comparator import ApiCompareComparator
from msprof_analyze.prof_common.constant import Constant


class TestApiCompareComparator(unittest.TestCase):
    def setUp(self):
        self.mock_bean = MagicMock()
        self.mock_bean.row = {"name": "test_op", "base_data": [], "comparison_data": []}

        self.base_op1 = MagicMock()
        self.base_op1.name = "op1"
        self.base_op1_2 = MagicMock()
        self.base_op1_2.name = "op1"

        self.base_op2 = MagicMock()
        self.base_op2.name = "op2"
        self.comparison_op1 = MagicMock()
        self.comparison_op1.name = "op1"

        self.comparison_op2 = MagicMock()
        self.comparison_op2.name = "op2"
        self.comparison_op3 = MagicMock()
        self.comparison_op3.name = "op3"

        self.base_ops = [self.base_op1, self.base_op1_2, self.base_op2]
        self.comparison_ops = [self.comparison_op1, self.comparison_op2, self.comparison_op3]

        self.origin_data = {
            Constant.BASE_DATA: self.base_ops,
            Constant.COMPARISON_DATA: self.comparison_ops
        }

    def test_aggregated_api_by_name(self):
        op1 = MagicMock()
        op1.name = "op1"

        op2 = MagicMock()
        op2.name = "op2"
        ops = [op1, op2]

        result = ApiCompareComparator._aggregated_api_by_name(ops)

        self.assertEqual(len(result), 2)
        self.assertEqual(len(result["op1"]), 1)
        self.assertEqual(len(result["op2"]), 1)

    def test_compare_with_empty_origin_data(self):
        comparator = ApiCompareComparator(None, self.mock_bean)
        comparator._compare()
        self.assertEqual(comparator._rows, [])

    def test_compare_with_empty_base_data(self):
        origin_data = {
            Constant.BASE_DATA: [],
            Constant.COMPARISON_DATA: self.comparison_ops
        }
        comparator = ApiCompareComparator(origin_data, self.mock_bean)
        comparator._compare()
        self.assertEqual(comparator._rows, [])

    @patch('msprof_analyze.compare_tools.compare_backend.comparator.api_compare_comparator.update_order_id')
    def test_compare_normal_case(self, mock_update_order_id):
        comparator = ApiCompareComparator(self.origin_data, self.mock_bean)
        mock_bean_instance = MagicMock()
        mock_bean_instance.row = {"name": "test_row"}
        self.mock_bean.return_value = mock_bean_instance

        comparator._compare()
        self.assertEqual(self.mock_bean.call_count, 3)
        mock_update_order_id.assert_called_once_with(comparator._rows)
        self.assertEqual(len(comparator._rows), 3)

    @patch('msprof_analyze.compare_tools.compare_backend.comparator.api_compare_comparator.update_order_id')
    def test_compare_with_only_base_data(self, mock_update_order_id):
        origin_data = {
            Constant.BASE_DATA: self.base_ops,
            Constant.COMPARISON_DATA: [self.comparison_op1]
        }
        comparator = ApiCompareComparator(origin_data, self.mock_bean)

        mock_bean_instance = MagicMock()
        mock_bean_instance.row = {"name": "test_row"}
        self.mock_bean.return_value = mock_bean_instance
        comparator._compare()
        self.assertEqual(self.mock_bean.call_count, 2)
        mock_update_order_id.assert_called_once_with(comparator._rows)
