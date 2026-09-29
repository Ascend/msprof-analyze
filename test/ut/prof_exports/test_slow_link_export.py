# -------------------------------------------------------------------------
# This file is part of the MindStudio project.
# Copyright (c) 2026 Huawei Technologies Co.,Ltd.
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
