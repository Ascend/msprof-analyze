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

import os
import unittest
from unittest.mock import patch

from msprof_analyze.advisor.advisor_backend.advice_factory.advice_factory import AdviceFactory


class _ConcreteAdviceFactory(AdviceFactory):
    """Concrete subclass for testing AdviceFactory base class."""

    ADVICE_LIB = {"valid_advice": "SomeAdviceClass"}

    def run_advice(self, advice: str, kwargs: dict):
        return f"result_for_{advice}"


class TestAdviceFactory(unittest.TestCase):
    def test_init_resolves_absolute_path(self):
        factory = _ConcreteAdviceFactory("/tmp/test_path")
        self.assertTrue(os.path.isabs(factory.collection_path))

    def test_init_resolves_relative_path(self):
        factory = _ConcreteAdviceFactory("relative/path")
        self.assertTrue(os.path.isabs(factory.collection_path))

    @patch('msprof_analyze.advisor.advisor_backend.advice_factory.advice_factory.PathManager.input_path_common_check')
    def test_path_check_calls_path_manager(self, mock_check):
        factory = _ConcreteAdviceFactory("/tmp/test")
        factory.path_check()
        mock_check.assert_called_once_with(factory.collection_path)

    def test_advice_check_raises_for_invalid_advice(self):
        factory = _ConcreteAdviceFactory("/tmp/test")
        with self.assertRaises(RuntimeError):
            factory.advice_check("invalid_advice")

    def test_advice_check_passes_for_valid_advice(self):
        factory = _ConcreteAdviceFactory("/tmp/test")
        factory.advice_check("valid_advice")

    @patch('msprof_analyze.advisor.advisor_backend.advice_factory.advice_factory.PathManager.input_path_common_check')
    def test_produce_advice_calls_all_checks_and_run(self, mock_path_check):
        factory = _ConcreteAdviceFactory("/tmp/test")
        result = factory.produce_advice("valid_advice", {"key": "val"})
        mock_path_check.assert_called_once()
        self.assertEqual(result, "result_for_valid_advice")

    @patch('msprof_analyze.advisor.advisor_backend.advice_factory.advice_factory.PathManager.input_path_common_check')
    def test_produce_advice_raises_when_advice_invalid(self, mock_path_check):
        factory = _ConcreteAdviceFactory("/tmp/test")
        with self.assertRaises(RuntimeError):
            factory.produce_advice("invalid_advice", {})
