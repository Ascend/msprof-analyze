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
