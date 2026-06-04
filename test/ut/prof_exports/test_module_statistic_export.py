# Copyright (c) 2025, Huawei Technologies Co., Ltd. All rights reserved.
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
