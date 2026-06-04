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
# pylint: disable=duplicate-code,unspecified-encoding

import unittest
from unittest.mock import patch, MagicMock

import pandas as pd

from msprof_analyze.prof_exports.compute_op_sum_export import ComputeOpSumExport, ComputeOpSumExportExcludeOpName
from msprof_analyze.prof_exports.base_stats_export import BaseStatsExport
from msprof_analyze.prof_common.constant import Constant


class TestComputeOpSumExport(unittest.TestCase):
    def test_inherits_from_base_stats_export(self):
        self.assertTrue(issubclass(ComputeOpSumExport, BaseStatsExport))

    def test_init_sets_query_and_params(self):
        param_dict = {Constant.START_NS: 100, Constant.END_NS: 200}
        exp = ComputeOpSumExport("/tmp/test.db", "compute_op_sum", param_dict)
        self.assertIn("COMPUTE_TASK_INFO", exp._query)
        self.assertIsNotNone(exp._param)

    def test_get_param_order_returns_correct_order(self):
        param_dict = {Constant.START_NS: 100, Constant.END_NS: 200}
        exp = ComputeOpSumExport("/tmp/test.db", "compute_op_sum", param_dict)
        order = exp.get_param_order()
        self.assertEqual(order, [Constant.START_NS, Constant.END_NS])

    def test_build_param_list_maps_correctly(self):
        param_dict = {Constant.START_NS: 100, Constant.END_NS: 200}
        exp = ComputeOpSumExport("/tmp/test.db", "compute_op_sum", param_dict)
        params = exp._build_param_list()
        self.assertEqual(params, [100, 200])

    @patch('msprof_analyze.prof_exports.base_stats_export.DBManager.create_connect_db')
    @patch('msprof_analyze.prof_exports.base_stats_export.pd.read_sql')
    def test_read_export_db_with_params(self, mock_read_sql, mock_create_db):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_create_db.return_value = (mock_conn, mock_cursor)
        mock_df = pd.DataFrame({"OpName": ["op1", "op2"], "Duration": [100, 200]})
        mock_read_sql.return_value = mock_df

        import tempfile
        import os

        with tempfile.TemporaryDirectory() as tmp:
            db_path = os.path.join(tmp, "test.db")
            with open(db_path, 'w', encoding='utf-8') as f:
                f.write('')
            param_dict = {Constant.START_NS: 100, Constant.END_NS: 200}
            exp = ComputeOpSumExport(db_path, "compute_op_sum", param_dict)
            result = exp.read_export_db()

        self.assertIsNotNone(result)
        call_kwargs = mock_read_sql.call_args[1]
        self.assertIn('params', call_kwargs)


class TestComputeOpSumExportExcludeOpName(unittest.TestCase):
    def test_inherits_from_base_stats_export(self):
        self.assertTrue(issubclass(ComputeOpSumExportExcludeOpName, BaseStatsExport))

    def test_uses_exclude_opname_query(self):
        param_dict = {Constant.START_NS: 100, Constant.END_NS: 200}
        exp = ComputeOpSumExportExcludeOpName("/tmp/test.db", "recipe", param_dict)
        self.assertNotIn("\"OpName\"", exp._query)
        self.assertIn("COMPUTE_TASK_INFO", exp._query)

    def test_get_param_order_returns_correct_order(self):
        param_dict = {Constant.START_NS: 100, Constant.END_NS: 200}
        exp = ComputeOpSumExportExcludeOpName("/tmp/test.db", "recipe", param_dict)
        order = exp.get_param_order()
        self.assertEqual(order, [Constant.START_NS, Constant.END_NS])
