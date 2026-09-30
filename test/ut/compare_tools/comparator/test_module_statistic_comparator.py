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
from msprof_analyze.compare_tools.compare_backend.comparator.module_statistic_comparator \
                import ModuleStatisticComparator


class TestModuleStatisticComparator(unittest.TestCase):
    def setUp(self):
        self.mock_bean = MagicMock()
        self.mock_bean.rows = [["row_data"]]

        self.base_module1 = MagicMock()
        self.base_module1.start_time = 100
        self.base_module1.module_name = "module1"

        self.base_module2 = MagicMock()
        self.base_module2.start_time = 200
        self.base_module2.module_name = "module2"

        self.comparison_module1 = MagicMock()
        self.comparison_module1.start_time = 150
        self.comparison_module1.module_name = "module1"

        self.comparison_module2 = MagicMock()
        self.comparison_module2.start_time = 250
        self.comparison_module2.module_name = "module2"

        self.comparison_module3 = MagicMock()
        self.comparison_module3.start_time = 300
        self.comparison_module3.module_name = "module3"

        self.origin_data = [
            (self.base_module1, self.comparison_module1),
            (self.base_module2, self.comparison_module2),
            (None, self.comparison_module3),
            (MagicMock(), None),
        ]

    def test_compare_with_empty_origin_data(self):
        comparator = ModuleStatisticComparator(None, self.mock_bean)
        comparator._compare()
        self.assertEqual(comparator._rows, [])

    def test_group_by_module_name_only_base_data(self):
        origin_data = [
            (self.base_module1, None),
            (self.base_module2, None)
        ]

        comparator = ModuleStatisticComparator(origin_data, self.mock_bean)
        base_dict, comparison_dict = comparator._group_by_module_name()

        self.assertIn("module1", base_dict)
        self.assertIn("module2", base_dict)
        self.assertEqual(len(comparison_dict), 0)

    @patch('msprof_analyze.compare_tools.compare_backend.comparator.module_statistic_comparator.update_order_id')
    def test_compare_with_multiple_module_instances(self, mock_update_order_id):
        base_module1_2 = MagicMock()
        base_module1_2.start_time = 120
        base_module1_2.module_name = "module1"

        comparison_module1_2 = MagicMock()
        comparison_module1_2.start_time = 170
        comparison_module1_2.module_name = "module1"

        origin_data = [
            (self.base_module1, self.comparison_module1),
            (base_module1_2, comparison_module1_2)
        ]

        comparator = ModuleStatisticComparator(origin_data, self.mock_bean)

        mock_bean_instance = MagicMock()
        mock_bean_instance.rows = [["test_row"]]
        self.mock_bean.return_value = mock_bean_instance

        comparator._compare()

        expected_call = unittest.mock.call("module1", [self.base_module1, base_module1_2], \
                        [self.comparison_module1, comparison_module1_2])
        self.mock_bean.assert_has_calls([expected_call], any_order=True)

    def test_group_by_module_name_only_comparison_data(self):
        origin_data = [
            (None, self.comparison_module1),
            (None, self.comparison_module2)
        ]

        comparator = ModuleStatisticComparator(origin_data, self.mock_bean)
        base_dict, comparison_dict = comparator._group_by_module_name()

        self.assertEqual(len(base_dict), 0)
        self.assertIn("module1", comparison_dict)
        self.assertIn("module2", comparison_dict)

    def test_group_by_module_name_empty_data(self):
        comparator = ModuleStatisticComparator([], self.mock_bean)
        base_dict, comparison_dict = comparator._group_by_module_name()

        self.assertEqual(len(base_dict), 0)
        self.assertEqual(len(comparison_dict), 0)
