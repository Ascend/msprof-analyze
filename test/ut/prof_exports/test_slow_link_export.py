# Copyright (c) 2026, Huawei Technologies Co., Ltd. All rights reserved.
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
# pylint: disable=duplicate-code

import unittest

from msprof_analyze.prof_exports.slow_link_export import QUERY
from msprof_analyze.prof_exports.base_stats_export import BaseStatsExport


class _ConcreteSlowLinkExport(BaseStatsExport):
    """Concrete subclass that mirrors SlowLinkExport behavior for testing."""

    def __init__(self, db_path, recipe_name):
        super().__init__(db_path, recipe_name, {})
        self._query = QUERY

    def get_param_order(self):
        return []


class TestSlowLinkExport(unittest.TestCase):
    def test_inherits_from_base_stats_export(self):
        self.assertTrue(issubclass(_ConcreteSlowLinkExport, BaseStatsExport))

    def test_init_sets_query(self):
        exp = _ConcreteSlowLinkExport("/tmp/test.db", "slow_link")
        self.assertEqual(exp._query, QUERY)
        self.assertIn("COMMUNICATION_OP", exp._query)

    def test_init_sets_recipe_name(self):
        exp = _ConcreteSlowLinkExport("/tmp/test.db", "slow_link")
        self.assertEqual(exp._analysis_class, "slow_link")

    def test_get_query_returns_query(self):
        exp = _ConcreteSlowLinkExport("/tmp/test.db", "slow_link")
        self.assertIsNotNone(exp.get_query())
        self.assertIn("COMMUNICATION_OP", exp.get_query())

    def test_build_param_list_returns_none(self):
        exp = _ConcreteSlowLinkExport("/tmp/test.db", "slow_link")
        result = exp._build_param_list()
        self.assertIsNone(result)
