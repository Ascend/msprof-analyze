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
from unittest.mock import patch, MagicMock

from msprof_analyze.advisor.interface.interface import Interface


class TestInterface(unittest.TestCase):
    def setUp(self):
        self.original_supported_analyzer = dict(Interface.supported_analyzer)

    def tearDown(self):
        Interface.supported_analyzer = self.original_supported_analyzer

    def test_get_scope_returns_scopes_for_schedule(self):
        scopes = Interface.get_scope(Interface.SCHEDULE)
        self.assertIsInstance(scopes, list)
        self.assertTrue(len(scopes) > 0)

    def test_get_scope_returns_scopes_for_computation(self):
        scopes = Interface.get_scope(Interface.COMPUTATION)
        self.assertIsInstance(scopes, list)
        self.assertTrue(len(scopes) > 0)

    def test_get_scope_raises_for_invalid_dimension(self):
        with self.assertRaises(AttributeError):
            Interface.get_scope("invalid_dimension")

    def test_get_analyzer_returns_class_for_valid_args(self):
        analyzer = Interface.get_analyzer(Interface.SCHEDULE, "syncbn")
        self.assertIsNotNone(analyzer)

    def test_get_analyzer_returns_none_for_invalid_scope(self):
        analyzer = Interface.get_analyzer(Interface.SCHEDULE, "invalid_scope")
        self.assertIsNone(analyzer)

    def test_add_analyzer_new_dimension(self):
        Interface.add_analyzer("test_dim", "test_scope", "TestAnalyzer")
        scopes = Interface.get_scope("test_dim")
        self.assertIn("test_scope", scopes)

    def test_add_analyzer_existing_dimension(self):
        Interface.add_analyzer(Interface.SCHEDULE, "test_new_scope", "NewAnalyzer")
        scopes = Interface.get_scope(Interface.SCHEDULE)
        self.assertIn("test_new_scope", scopes)

    def test_all_dimension_contains_all_keys(self):
        for dim in [
            Interface.SCHEDULE,
            Interface.COMPUTATION,
            Interface.COMMUNICATION,
            Interface.OVERALL,
            Interface.CLUSTER,
            Interface.MEMORY,
            Interface.COMPARISON,
        ]:
            self.assertIn(dim, Interface.all_dimension)

    def test_init_sets_collection_path_to_absolute(self):
        import os

        iface = Interface(profiling_path="/tmp/test_path")
        self.assertTrue(os.path.isabs(iface.collection_path))

    def test_get_result_raises_for_invalid_dimension(self):
        iface = Interface(profiling_path="/tmp/test")
        with self.assertRaises(ValueError):
            iface.get_result("invalid_dim", "some_scope")

    def test_get_result_raises_for_invalid_scope(self):
        iface = Interface(profiling_path="/tmp/test")
        with self.assertRaises(ValueError):
            iface.get_result(Interface.SCHEDULE, "invalid_scope")

    @patch.object(Interface, 'get_analyzer')
    @patch.object(Interface, 'get_scope')
    def test_get_result_returns_result_on_success(self, mock_get_scope, mock_get_analyzer):
        mock_get_scope.return_value = ["syncbn"]
        mock_instance = MagicMock()
        mock_result = MagicMock()
        mock_result.data = {}
        mock_instance.optimize.return_value = mock_result
        mock_analyzer_class = MagicMock(return_value=mock_instance)
        mock_get_analyzer.return_value = mock_analyzer_class

        iface = Interface(profiling_path="/tmp/test")
        result = iface.get_result(Interface.SCHEDULE, "syncbn")

        self.assertIsInstance(result, dict)
        mock_instance.optimize.assert_called_once()

    @patch.object(Interface, 'get_analyzer')
    @patch.object(Interface, 'get_scope')
    def test_get_result_returns_empty_on_exception(self, mock_get_scope, mock_get_analyzer):
        mock_get_scope.return_value = ["syncbn"]
        mock_analyzer_class = MagicMock(side_effect=RuntimeError("test error"))
        mock_get_analyzer.return_value = mock_analyzer_class

        iface = Interface(profiling_path="/tmp/test")
        result = iface.get_result(Interface.SCHEDULE, "syncbn")

        self.assertIsInstance(result, dict)
