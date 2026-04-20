# Copyright (c) 2025, Huawei Technologies Co., Ltd.
# All rights reserved.
#
# Licensed under the Apache License, Version 2.0  (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
import unittest
from decimal import Decimal, ROUND_HALF_UP

from mock import patch

from msprof_analyze.compare_tools.compare_backend.utils.common_func import (
    calculate_diff_ratio,
    update_order_id,
    convert_to_float,
    convert_to_decimal,
    longest_common_subsequence_matching,
    BitMap
)


class TestCommonFunc(unittest.TestCase):

    def test_calculate_diff_ratio_normal_cases(self):
        """测试正常情况下的差异比率计算"""
        # 测试正数情况
        result = calculate_diff_ratio(10.0, 15.0)
        self.assertEqual(result, [5.0, 1.5])

        # 测试小数情况
        result = calculate_diff_ratio(2.5, 3.75)
        self.assertEqual(result, [1.25, 1.5])

        # 测试比较值小于基准值的情况
        result = calculate_diff_ratio(20.0, 10.0)
        self.assertEqual(result, [-10.0, 0.5])

    def test_calculate_diff_ratio_edge_cases(self):
        """测试边界情况下的差异比率计算"""
        # 测试两个值都为0的情况
        result = calculate_diff_ratio(0.0, 0.0)
        self.assertEqual(result, [0.0, 1.0])

        # 测试基准值为0，比较值不为0的情况
        result = calculate_diff_ratio(0.0, 5.0)
        self.assertEqual(result, [5.0, float('inf')])

        # 测试负数情况
        result = calculate_diff_ratio(-10.0, -5.0)
        self.assertEqual(result, [5.0, 0.5])

    def test_update_order_id(self):
        """测试更新顺序ID功能"""
        # 测试普通列表
        data_list = [[10, "data1"], [20, "data2"], [30, "data3"]]
        update_order_id(data_list)
        self.assertEqual(data_list, [[1, "data1"], [2, "data2"], [3, "data3"]])

        # 测试包含None的列表
        data_list = [[10, "data1"], None, [30, "data3"]]
        update_order_id(data_list)
        self.assertEqual(data_list, [[1, "data1"], None, [3, "data3"]])

        # 测试空列表
        data_list = []
        update_order_id(data_list)
        self.assertEqual(data_list, [])

    def test_convert_to_float(self):
        """测试转换为浮点数功能"""
        # 测试字符串数字转换
        self.assertEqual(convert_to_float("123.45"), 123.45)

        # 测试整数转换
        self.assertEqual(convert_to_float(42), 42.0)

        # 测试浮点数转换
        self.assertEqual(convert_to_float(3.14), 3.14)

        # 测试科学计数法转换
        self.assertEqual(convert_to_float("1.23e-4"), 0.000123)

    @patch('msprof_analyze.compare_tools.compare_backend.utils.common_func.logger.warning')
    def test_convert_to_float_invalid_data(self, mock_warning):
        """测试转换无效数据到浮点数的情况"""
        # 测试无法转换的字符串
        self.assertEqual(convert_to_float("not a number"), 0.0)
        mock_warning.assert_called_once_with('Invalid profiling data which failed to convert data to float.')

        # 测试None值
        mock_warning.reset_mock()
        self.assertEqual(convert_to_float(None), 0.0)
        mock_warning.assert_called_once_with('Invalid profiling data which failed to convert data to float.')

    def test_convert_to_decimal(self):
        """测试转换为Decimal类型功能"""
        # 测试字符串数字转换
        self.assertEqual(convert_to_decimal("123.45"), Decimal("123.45"))

        # 测试整数转换
        self.assertEqual(convert_to_decimal(42), Decimal("42"))

        # 测试浮点数转换
        self.assertEqual(convert_to_decimal(3.14).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP), Decimal("3.14"))

        # 测试科学计数法转换
        self.assertEqual(convert_to_decimal("1.23e-4"), Decimal("0.000123"))

    @patch('msprof_analyze.compare_tools.compare_backend.utils.common_func.logger.warning')
    def test_convert_to_decimal_invalid_data(self, mock_warning):
        """测试转换无效数据到Decimal类型的情况"""
        # 测试无法转换的字符串
        self.assertEqual(convert_to_decimal("not a number"), Decimal("0"))
        mock_warning.assert_called_once_with('Invalid profiling data which failed to convert data to decimal.')

        # 测试None值
        mock_warning.reset_mock()
        self.assertEqual(convert_to_decimal(None), Decimal("0"))
        mock_warning.assert_called_once_with('Invalid profiling data which failed to convert data to decimal.')

    def test_longest_common_subsequence_matching(self):
        """测试最长公共子序列匹配算法"""
        # 测试简单匹配情况
        base_ops = ["a", "b", "c", "d"]
        comparison_ops = ["b", "c", "e"]

        result = longest_common_subsequence_matching(base_ops, comparison_ops, lambda x: x)
        expected = [['a', None], ['b', 'b'], ['c', 'c'], ['d', None], [None, 'e']]
        self.assertEqual(result, expected)

        # 测试空列表情况
        result = longest_common_subsequence_matching([], comparison_ops, lambda x: x)
        expected = [[None, "b"], [None, "c"], [None, "e"]]
        self.assertEqual(result, expected)

        result = longest_common_subsequence_matching(base_ops, [], lambda x: x)
        expected = [["a", None], ["b", None], ["c", None], ["d", None]]
        self.assertEqual(result, expected)

        # 测试完全匹配情况
        base_ops = ["x", "y", "z"]
        comparison_ops = ["x", "y", "z"]
        result = longest_common_subsequence_matching(base_ops, comparison_ops, lambda x: x)
        expected = [["x", "x"], ["y", "y"], ["z", "z"]]
        self.assertEqual(result, expected)

    def test_bitmap(self):
        """测试BitMap类的功能"""
        # 测试基本功能
        bitmap = BitMap(100)

        # 测试添加和检查位
        bitmap.add(5)
        bitmap.add(42)
        bitmap.add(99)

        self.assertIn(5, bitmap)
        self.assertIn(42, bitmap)
        self.assertIn(99, bitmap)
        self.assertNotIn(0, bitmap)
        self.assertNotIn(100, bitmap)  # 超出范围

        # 测试多个位操作
        bitmap = BitMap(20)
        for i in range(0, 20, 2):
            bitmap.add(i)

        for i in range(20):
            if i % 2 == 0:
                self.assertIn(i, bitmap)
            else:
                self.assertNotIn(i, bitmap)

        # 测试边界情况
        bitmap = BitMap(1)
        bitmap.add(0)
        self.assertIn(0, bitmap)
        self.assertNotIn(1, bitmap)  # 超出范围


if __name__ == '__main__':
    unittest.main()
