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

import os
import tempfile
import unittest
from unittest.mock import patch, MagicMock

import pandas as pd

from msprof_analyze.prof_exports.base_stats_export import BaseStatsExport


class _ConcreteExport(BaseStatsExport):
    """Minimal concrete subclass for testing BaseStatsExport."""

    def __init__(self, db_path, analysis_class, param_dict=None, query=None, param_order=None):
        self._param_order = param_order or []
        super().__init__(db_path, analysis_class, param_dict)
        self._query = query

    def get_param_order(self):
        return self._param_order


class TestBaseStatsExport(unittest.TestCase):
    def test_init_sets_attributes(self):
        exp = _ConcreteExport("/tmp/test.db", "test_recipe", {"key": "val"})
        self.assertEqual(exp._db_path, "/tmp/test.db")
        self.assertEqual(exp._analysis_class, "test_recipe")
        self.assertEqual(exp._param_dict, {"key": "val"})

    def test_get_query_returns_query(self):
        exp = _ConcreteExport("/tmp/test.db", "test", query="SELECT 1")
        self.assertEqual(exp.get_query(), "SELECT 1")

    def test_build_param_list_returns_none_when_no_param_order(self):
        exp = _ConcreteExport("/tmp/test.db", "test", param_dict={"a": 1}, param_order=[])
        result = exp._build_param_list()
        self.assertIsNone(result)

    def test_build_param_list_returns_none_when_no_param_dict(self):
        exp = _ConcreteExport("/tmp/test.db", "test", param_dict=None, param_order=["a"])
        result = exp._build_param_list()
        self.assertIsNone(result)

    def test_build_param_list_returns_params_in_order(self):
        exp = _ConcreteExport(
            "/tmp/test.db", "test", param_dict={"start": 100, "end": 200}, param_order=["start", "end"]
        )
        result = exp._build_param_list()
        self.assertEqual(result, [100, 200])

    def test_build_param_list_skips_missing_params(self):
        exp = _ConcreteExport("/tmp/test.db", "test", param_dict={"start": 100}, param_order=["start", "end"])
        result = exp._build_param_list()
        self.assertEqual(result, [100])

    def test_build_param_list_all_missing_returns_none(self):
        exp = _ConcreteExport("/tmp/test.db", "test", param_dict={"other": 1}, param_order=["start", "end"])
        result = exp._build_param_list()
        self.assertIsNone(result)

    def test_read_export_db_returns_none_when_db_path_empty(self):
        exp = _ConcreteExport("", "test", query="SELECT 1")
        result = exp.read_export_db()
        self.assertIsNone(result)

    def test_read_export_db_returns_none_when_file_not_exists(self):
        exp = _ConcreteExport("/nonexistent/path.db", "test", query="SELECT 1")
        result = exp.read_export_db()
        self.assertIsNone(result)

    def test_read_export_db_returns_none_when_query_is_none(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = os.path.join(tmp, "test.db")
            with open(db_path, 'w', encoding='utf-8') as f:
                f.write('')
            exp = _ConcreteExport(db_path, "test", query=None)
            result = exp.read_export_db()
            self.assertIsNone(result)

    @patch('msprof_analyze.prof_exports.base_stats_export.DBManager.create_connect_db')
    @patch('msprof_analyze.prof_exports.base_stats_export.pd.read_sql')
    def test_read_export_db_returns_data_without_params(self, mock_read_sql, mock_create_db):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_create_db.return_value = (mock_conn, mock_cursor)
        mock_df = pd.DataFrame({"col": [1, 2]})
        mock_read_sql.return_value = mock_df

        with tempfile.TemporaryDirectory() as tmp:
            db_path = os.path.join(tmp, "test.db")
            with open(db_path, 'w', encoding='utf-8') as f:
                f.write('')
            exp = _ConcreteExport(db_path, "test", query="SELECT * FROM t", param_order=[])
            result = exp.read_export_db()

        self.assertIsNotNone(result)
        mock_read_sql.assert_called_once()

    @patch('msprof_analyze.prof_exports.base_stats_export.DBManager.create_connect_db')
    @patch('msprof_analyze.prof_exports.base_stats_export.pd.read_sql')
    def test_read_export_db_returns_data_with_params(self, mock_read_sql, mock_create_db):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_create_db.return_value = (mock_conn, mock_cursor)
        mock_df = pd.DataFrame({"col": [1, 2]})
        mock_read_sql.return_value = mock_df

        with tempfile.TemporaryDirectory() as tmp:
            db_path = os.path.join(tmp, "test.db")
            with open(db_path, 'w', encoding='utf-8') as f:
                f.write('')
            exp = _ConcreteExport(
                db_path, "test", query="SELECT * FROM t WHERE x >= ?", param_dict={"x": 100}, param_order=["x"]
            )
            result = exp.read_export_db()

        self.assertIsNotNone(result)
        call_kw = mock_read_sql.call_args[1]
        self.assertIn('params', call_kw)

    @patch('msprof_analyze.prof_exports.base_stats_export.DBManager.create_connect_db')
    def test_read_export_db_returns_none_on_exception(self, mock_create_db):
        mock_create_db.side_effect = RuntimeError("db error")

        with tempfile.TemporaryDirectory() as tmp:
            db_path = os.path.join(tmp, "test.db")
            with open(db_path, 'w', encoding='utf-8') as f:
                f.write('')
            exp = _ConcreteExport(db_path, "test", query="SELECT * FROM t")
            result = exp.read_export_db()

        self.assertIsNone(result)
