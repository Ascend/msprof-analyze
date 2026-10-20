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
from msprof_analyze.compare_tools.compare_backend.compare_bean.kernel_compare_bean \
                    import KernelCompareInfo, KernelCompareBean


class TestKernelCompareInfo(unittest.TestCase):
    def test_init_with_valid_data(self):
        data_list = ["MatMul", "256x512", "12.345", 5, "3.456", "1.234"]
        kernel_info = KernelCompareInfo(data_list)

        self.assertEqual(kernel_info.kernel_type, "MatMul")
        self.assertEqual(kernel_info.input_shapes, "256x512")
        self.assertEqual(kernel_info.total_dur, 12.35)
        self.assertEqual(kernel_info.number, 5)
        self.assertEqual(kernel_info.max_dur, 3.46)
        self.assertEqual(kernel_info.min_dur, 1.23)
        self.assertEqual(kernel_info.avg_dur, 2.47)

    def test_init_with_insufficient_data(self):
        data_list = ["MatMul", "256x512"]
        kernel_info = KernelCompareInfo(data_list)

        self.assertIsNone(kernel_info.kernel_type)
        self.assertIsNone(kernel_info.input_shapes)
        self.assertEqual(kernel_info.total_dur, 0.0)
        self.assertIsNone(kernel_info.number)
        self.assertIsNone(kernel_info.max_dur)
        self.assertIsNone(kernel_info.min_dur)
        self.assertEqual(kernel_info.avg_dur, 0.0)


class TestKernelCompareBean(unittest.TestCase):
    def setUp(self):
        self.base_data = ["MatMul", "256x512", "12.345", 5, "3.456", "1.234"]
        self.comparison_data = ["MatMul", "256x512", "10.123", 4, "2.789", "1.012"]

    def test_init_with_base_data_only(self):
        bean = KernelCompareBean(self.base_data, [])

        self.assertEqual(bean._kernel_type, "MatMul")
        self.assertEqual(bean._input_shapes, "256x512")
        self.assertEqual(bean._base_kernel.total_dur, 12.35)
        self.assertEqual(bean._comparison_kernel.total_dur, 0.0)

    def test_init_with_different_kernel_types(self):
        base_data = ["MatMul", "256x512", "12.345", 5, "3.456", "1.234"]
        comparison_data = ["Conv", "256x512", "10.123", 4, "2.789", "1.012"]

        bean = KernelCompareBean(base_data, comparison_data)

        self.assertEqual(bean._kernel_type, "MatMul")
        self.assertEqual(bean._input_shapes, "256x512")

    def test_row_with_empty_comparison_data(self):
        bean = KernelCompareBean(self.base_data, [])
        row = bean.row

        self.assertEqual(row[8], 0.0)
        self.assertEqual(row[9], 0.0)
        self.assertIsNone(row[10])
        self.assertIsNone(row[11])
        self.assertIsNone(row[12])

    def test_slots_behavior(self):
        bean = KernelCompareBean(self.base_data, self.comparison_data)
        with self.assertRaises(AttributeError):
            bean.new_attribute = "test"

        self.assertEqual(bean._kernel_type, "MatMul")
