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
from unittest.mock import MagicMock
from msprof_analyze.compare_tools.compare_backend.compare_bean.api_compare_bean import ApiInfo, ApiCompareBean


class TestApiInfo(unittest.TestCase):
    def setUp(self):
        self.mock_data1 = MagicMock()
        self.mock_data1.api_dur = 5000.0
        self.mock_data1.api_self_time = 3000.0

        self.mock_data2 = MagicMock()
        self.mock_data2.api_dur = 7000.0
        self.mock_data2.api_self_time = 4000.0

        self.data_list = [self.mock_data1, self.mock_data2]

    def test_slots_behavior(self):
        api_info = ApiInfo("test_op", self.data_list)
        with self.assertRaises(AttributeError):
            api_info.new_attribute = "test"
        self.assertEqual(api_info.name, "test_op")


class TestApiCompareBean(unittest.TestCase):
    def setUp(self):
        self.base_data1 = MagicMock()
        self.base_data1.api_dur = 5000.0
        self.base_data1.api_self_time = 3000.0

        self.base_data2 = MagicMock()
        self.base_data2.api_dur = 7000.0
        self.base_data2.api_self_time = 4000.0

        self.comparison_data1 = MagicMock()
        self.comparison_data1.api_dur = 6000.0
        self.comparison_data1.api_self_time = 3500.0

        self.comparison_data2 = MagicMock()
        self.comparison_data2.api_dur = 8000.0
        self.comparison_data2.api_self_time = 4500.0

        self.base_api_list = [self.base_data1, self.base_data2]
        self.comparison_api_list = [self.comparison_data1, self.comparison_data2]

    def test_row_with_both_empty_data(self):
        bean = ApiCompareBean("test_op", [], [])
        row = bean.row
        self.assertEqual(row[2], 0.0)
        self.assertEqual(row[3], 0.0)
        self.assertEqual(row[4], 0.0)
        self.assertEqual(row[5], 0)
        self.assertEqual(row[6], 0.0)

    def test_row_with_different_data_lengths(self):
        single_comparison_data = [self.comparison_data1]
        bean = ApiCompareBean("test_op", self.base_api_list, single_comparison_data)
        row = bean.row

        self.assertEqual(row[5], 2)
        self.assertEqual(row[9], 1)
        self.assertEqual(row[4], 6.0)
        self.assertEqual(row[8], 6.0)
