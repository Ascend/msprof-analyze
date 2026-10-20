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
from msprof_analyze.prof_exports.cluster_time_summary_export import (
    CommunicationTimeExport,
    CommunicationOpWithStepExport,
    MemoryAndDispatchTimeExport,
)


class TestCommunicationTimeExport(unittest.TestCase):
    def test_inherits_from_base_stats_export(self):
        self.assertTrue(issubclass(CommunicationTimeExport, BaseStatsExport))

    def test_init_sets_query(self):
        param_dict = {Constant.START_NS: 0, Constant.END_NS: 1000}
        exp = CommunicationTimeExport("/tmp/test.db", "cluster_time_summary", param_dict)
        self.assertIn("COMMUNICATION_OP", exp._query)
        self.assertIsNotNone(exp._param)

    def test_get_param_order(self):
        param_dict = {Constant.START_NS: 0, Constant.END_NS: 1000}
        exp = CommunicationTimeExport("/tmp/test.db", "cluster_time_summary", param_dict)
        self.assertEqual(exp.get_param_order(), [Constant.START_NS, Constant.END_NS])


class TestCommunicationOpWithStepExport(unittest.TestCase):
    def test_inherits_from_base_stats_export(self):
        self.assertTrue(issubclass(CommunicationOpWithStepExport, BaseStatsExport))

    def test_init_with_step_exits_true(self):
        param_dict = {Constant.START_NS: 0, Constant.END_NS: 1000}
        exp = CommunicationOpWithStepExport("/tmp/test.db", "cluster_time_summary", param_dict, step_exits=True)
        self.assertIn("STEP_TIME", exp._query)
        self.assertNotIn("-1 AS step", exp._query)

    def test_init_with_step_exits_false(self):
        param_dict = {Constant.START_NS: 0, Constant.END_NS: 1000}
        exp = CommunicationOpWithStepExport("/tmp/test.db", "cluster_time_summary", param_dict, step_exits=False)
        self.assertIn("-1 AS step", exp._query)

    def test_get_param_order(self):
        param_dict = {Constant.START_NS: 0, Constant.END_NS: 1000}
        exp = CommunicationOpWithStepExport("/tmp/test.db", "cluster_time_summary", param_dict)
        self.assertEqual(exp.get_param_order(), [Constant.START_NS, Constant.END_NS])


class TestMemoryAndDispatchTimeExport(unittest.TestCase):
    def test_inherits_from_base_stats_export(self):
        self.assertTrue(issubclass(MemoryAndDispatchTimeExport, BaseStatsExport))

    def test_init_with_step_exits_true(self):
        param_dict = {Constant.START_NS: 0, Constant.END_NS: 1000}
        exp = MemoryAndDispatchTimeExport("/tmp/test.db", "cluster_time_summary", param_dict, step_exits=True)
        self.assertIn("STEP_TIME", exp._query)

    def test_init_with_step_exits_false(self):
        param_dict = {Constant.START_NS: 0, Constant.END_NS: 1000}
        exp = MemoryAndDispatchTimeExport("/tmp/test.db", "cluster_time_summary", param_dict, step_exits=False)
        self.assertIn("-1 AS step", exp._query)
        self.assertIsNone(exp.mode)

    def test_get_param_order(self):
        param_dict = {Constant.START_NS: 0, Constant.END_NS: 1000}
        exp = MemoryAndDispatchTimeExport("/tmp/test.db", "cluster_time_summary", param_dict)
        self.assertEqual(exp.get_param_order(), [Constant.START_NS, Constant.END_NS])
