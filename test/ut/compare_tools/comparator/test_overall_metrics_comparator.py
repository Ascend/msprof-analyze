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
from msprof_analyze.compare_tools.compare_backend.comparator.overall_metrics_comparator import OverallMetricsComparator
from msprof_analyze.prof_common.constant import Constant
from msprof_analyze.compare_tools.compare_backend.utils.excel_config import ExcelConfig


class TestOverallMetricsComparator(unittest.TestCase):
    def setUp(self):
        self.mock_bean = MagicMock()
        self.mock_bean.rows = [["metric1", 100, 200, 100, "50%"]]
        self.base_info = MagicMock()
        self.base_info.e2e_time_ms = 1000.0

        self.comp_info = MagicMock()
        self.comp_info.e2e_time_ms = 2000.0

        self.origin_data = {
            Constant.BASE_DATA: self.base_info,
            Constant.COMPARISON_DATA: self.comp_info
        }

    def test_base_info_property(self):
        comparator = OverallMetricsComparator(self.origin_data, self.mock_bean)
        self.assertEqual(comparator.base_info, self.base_info)

    def test_comp_info_property(self):
        comparator = OverallMetricsComparator(self.origin_data, self.mock_bean)
        self.assertEqual(comparator.comp_info, self.comp_info)

    def test_compare_with_zero_e2e_time(self):
        zero_base_info = MagicMock()
        zero_base_info.e2e_time_ms = 0.0
        origin_data_zero_base = {
            Constant.BASE_DATA: zero_base_info,
            Constant.COMPARISON_DATA: self.comp_info
        }
        comparator = OverallMetricsComparator(origin_data_zero_base, self.mock_bean)
        comparator._compare()
        self.assertEqual(comparator._rows, [])
        self.assertEqual(comparator._row_style, [])

    def test_compare_normal_case(self):
        comparator = OverallMetricsComparator(self.origin_data, self.mock_bean)
        mock_bean_instance = MagicMock()
        mock_bean_instance.rows = [["metric1", 100, 200, 100, "50%"]]
        self.mock_bean.return_value = mock_bean_instance

        comparator._compare()
        self.mock_bean.assert_called_once_with(self.base_info, self.comp_info)
        self.assertEqual(len(comparator._rows), 1)
        self.assertEqual(comparator._rows[0], ["metric1", 100, 200, 100, "50%"])
        self.assertEqual(len(comparator._row_style), 1)
        self.assertEqual(comparator._row_style[0], ExcelConfig.ROW_STYLE_MAP.get("metric1", {}))

    def test_row_style_mapping(self):
        comparator = OverallMetricsComparator(self.origin_data, self.mock_bean)
        mock_bean_instance = MagicMock()
        mock_bean_instance.rows = [
            ["metric1", 100, 200, 100, "50%"],
            ["metric2", 50, 100, 50, "100%"],
            ["unknown_metric", 10, 20, 10, "100%"]
        ]
        self.mock_bean.return_value = mock_bean_instance
        comparator._compare()

        self.assertEqual(len(comparator._row_style), 3)
        self.assertEqual(comparator._row_style[0], ExcelConfig.ROW_STYLE_MAP.get("metric1", {}))
        self.assertEqual(comparator._row_style[1], ExcelConfig.ROW_STYLE_MAP.get("metric2", {}))
        self.assertEqual(comparator._row_style[2], ExcelConfig.ROW_STYLE_MAP.get("unknown_metric", {}))
