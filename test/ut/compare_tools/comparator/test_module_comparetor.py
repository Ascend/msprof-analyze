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
from msprof_analyze.compare_tools.compare_backend.comparator.module_comparetor import ModuleComparator


class TestModuleComparator(unittest.TestCase):
    def setUp(self):
        self.mock_bean = MagicMock()
        self.mock_bean.rows = [["row_data"]]

        self.base_module1 = MagicMock()
        self.base_module1.start_time = 100

        self.base_module2 = MagicMock()
        self.base_module2.start_time = 200

        self.comparison_module1 = MagicMock()
        self.comparison_module1.start_time = 150

        self.comparison_module2 = MagicMock()
        self.comparison_module2.start_time = 250

        self.comparison_module3 = MagicMock()
        self.comparison_module3.start_time = 300
        self.origin_data = [
            (self.base_module1, self.comparison_module1),
            (self.base_module2, self.comparison_module2),
            (None, self.comparison_module3),
            (MagicMock(), None),
        ]

    def test_compare_with_empty_origin_data(self):
        comparator = ModuleComparator(None, self.mock_bean)
        comparator._compare()
        self.assertEqual(comparator._rows, [])

    def test_compare_with_empty_list(self):
        comparator = ModuleComparator([], self.mock_bean)
        comparator._compare()
        self.assertEqual(comparator._rows, [])

    @patch('msprof_analyze.compare_tools.compare_backend.comparator.module_comparetor.update_order_id')
    @patch('msprof_analyze.compare_tools.compare_backend.comparator.module_comparetor.logger')
    def test_compare_only_base_data(self, mock_logger, mock_update_order_id):
        origin_data = [
            (self.base_module1, None),
            (self.base_module2, None)
        ]

        comparator = ModuleComparator(origin_data, self.mock_bean)

        mock_bean_instance = MagicMock()
        mock_bean_instance.rows = [["test_row"]]
        self.mock_bean.return_value = mock_bean_instance

        comparator._compare()
        self.assertEqual(self.mock_bean.call_count, 2)
        mock_update_order_id.assert_called_once_with(comparator._rows)
        mock_logger.warning.assert_not_called()

    @patch('msprof_analyze.compare_tools.compare_backend.comparator.module_comparetor.update_order_id')
    @patch('msprof_analyze.compare_tools.compare_backend.comparator.module_comparetor.logger')
    def test_compare_only_comparison_data(self, mock_logger, mock_update_order_id):
        origin_data = [
            (None, self.comparison_module1),
            (None, self.comparison_module2)
        ]

        comparator = ModuleComparator(origin_data, self.mock_bean)

        mock_bean_instance = MagicMock()
        mock_bean_instance.rows = [["test_row"]]
        self.mock_bean.return_value = mock_bean_instance

        comparator._compare()
        self.assertEqual(self.mock_bean.call_count, 2)
        mock_update_order_id.assert_called_once_with(comparator._rows)
        mock_logger.warning.assert_not_called()

    @patch('msprof_analyze.compare_tools.compare_backend.comparator.module_comparetor.update_order_id')
    @patch('msprof_analyze.compare_tools.compare_backend.comparator.module_comparetor.logger')
    def test_compare_with_timing_ordering(self, mock_logger, mock_update_order_id):
        base_module_early = MagicMock()
        base_module_early.start_time = 100

        base_module_late = MagicMock()
        base_module_late.start_time = 300

        comparison_module_mid = MagicMock()
        comparison_module_mid.start_time = 200

        comparison_module_very_late = MagicMock()
        comparison_module_very_late.start_time = 400
        comparison_only_early = MagicMock()
        comparison_only_early.start_time = 50

        comparison_only_mid = MagicMock()
        comparison_only_mid.start_time = 250

        origin_data = [
            (base_module_early, comparison_module_mid),
            (base_module_late, comparison_module_very_late),
            (None, comparison_only_early),
            (None, comparison_only_mid)
        ]

        comparator = ModuleComparator(origin_data, self.mock_bean)

        mock_bean_instance = MagicMock()
        mock_bean_instance.rows = [["test_row"]]
        self.mock_bean.return_value = mock_bean_instance

        comparator._compare()
        self.assertEqual(self.mock_bean.call_count, 4)
        mock_update_order_id.assert_called_once_with(comparator._rows)
