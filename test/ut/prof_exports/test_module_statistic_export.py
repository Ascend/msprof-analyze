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

from msprof_analyze.prof_common.constant import Constant
from msprof_analyze.prof_exports.base_stats_export import BaseStatsExport
from msprof_analyze.prof_exports.module_statistic_export import (
    FrameworkOpToKernelExport,
    ModuleMstxRangeExport,
    FwdBwdFlowExport,
)


class TestFrameworkOpToKernelExport(unittest.TestCase):
    def test_inherits_from_base_stats_export(self):
        self.assertTrue(issubclass(FrameworkOpToKernelExport, BaseStatsExport))

    def test_init_with_compute_task_info_table(self):
        exp = FrameworkOpToKernelExport("/tmp/test.db", "module_statistic", Constant.TABLE_COMPUTE_TASK_INFO)
        self.assertIsNotNone(exp._query)
        self.assertIn("task_connections", exp._query)

    def test_init_with_communication_schedule_table(self):
        exp = FrameworkOpToKernelExport(
            "/tmp/test.db", "module_statistic", Constant.TABLE_COMMUNICATION_SCHEDULE_TASK_INFO
        )
        self.assertIsNotNone(exp._query)

    def test_init_with_communication_op_table(self):
        exp = FrameworkOpToKernelExport("/tmp/test.db", "module_statistic", Constant.TABLE_COMMUNICATION_OP)
        self.assertIsNotNone(exp._query)
        self.assertIn("COMMUNICATION_OP", exp._query)

    def test_init_with_unsupported_table(self):
        exp = FrameworkOpToKernelExport("/tmp/test.db", "module_statistic", "INVALID_TABLE")
        self.assertIsNone(exp._query)

    def test_get_param_order_returns_empty_list(self):
        exp = FrameworkOpToKernelExport("/tmp/test.db", "module_statistic", Constant.TABLE_COMPUTE_TASK_INFO)
        self.assertEqual(exp.get_param_order(), [])


class TestModuleMstxRangeExport(unittest.TestCase):
    def test_inherits_from_base_stats_export(self):
        self.assertTrue(issubclass(ModuleMstxRangeExport, BaseStatsExport))

    def test_init_sets_query(self):
        exp = ModuleMstxRangeExport("/tmp/test.db", "module_statistic")
        self.assertIsNotNone(exp._query)
        self.assertIn("MSTX_EVENTS", exp._query)

    def test_get_param_order_returns_empty_list(self):
        exp = ModuleMstxRangeExport("/tmp/test.db", "module_statistic")
        self.assertEqual(exp.get_param_order(), [])


class TestFwdBwdFlowExport(unittest.TestCase):
    def test_inherits_from_base_stats_export(self):
        self.assertTrue(issubclass(FwdBwdFlowExport, BaseStatsExport))

    def test_init_sets_query(self):
        exp = FwdBwdFlowExport("/tmp/test.db", "module_statistic")
        self.assertIsNotNone(exp._query)
        self.assertIn("fwd_name", exp._query.lower())

    def test_get_param_order_returns_empty_list(self):
        exp = FwdBwdFlowExport("/tmp/test.db", "module_statistic")
        self.assertEqual(exp.get_param_order(), [])
