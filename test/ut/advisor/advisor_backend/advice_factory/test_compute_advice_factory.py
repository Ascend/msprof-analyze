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

import unittest
from unittest.mock import MagicMock

from msprof_analyze.advisor.advisor_backend.advice_factory.compute_advice_factory import ComputeAdviceFactory
from msprof_analyze.advisor.advisor_backend.common_func_advisor.constant import Constant


class TestComputeAdviceFactory(unittest.TestCase):
    def setUp(self):
        self.original_advice_lib = dict(ComputeAdviceFactory.ADVICE_LIB)

    def tearDown(self):
        ComputeAdviceFactory.ADVICE_LIB = self.original_advice_lib

    def test_advice_lib_has_expected_keys(self):
        self.assertIn(Constant.NPU_FUSED, ComputeAdviceFactory.ADVICE_LIB)
        self.assertIn(Constant.NPU_SLOW, ComputeAdviceFactory.ADVICE_LIB)

    def test_run_advice_returns_fused_advice_result(self):
        mock_advice_class = MagicMock()
        mock_instance = MagicMock()
        mock_instance.run.return_value = {"status": "ok"}
        mock_advice_class.return_value = mock_instance
        ComputeAdviceFactory.ADVICE_LIB = {Constant.NPU_FUSED: mock_advice_class}

        factory = ComputeAdviceFactory("/tmp/test")
        result = factory.run_advice(Constant.NPU_FUSED, {})

        self.assertEqual(result, {"status": "ok"})
        mock_advice_class.assert_called_once_with(factory.collection_path)

    def test_run_advice_returns_slow_advice_result(self):
        mock_advice_class = MagicMock()
        mock_instance = MagicMock()
        mock_instance.run.return_value = {"status": "ok"}
        mock_advice_class.return_value = mock_instance
        ComputeAdviceFactory.ADVICE_LIB = {Constant.NPU_SLOW: mock_advice_class}

        factory = ComputeAdviceFactory("/tmp/test")
        result = factory.run_advice(Constant.NPU_SLOW, {})

        self.assertEqual(result, {"status": "ok"})
        mock_advice_class.assert_called_once_with(factory.collection_path)

    def test_run_advice_raises_for_unknown_advice(self):
        factory = ComputeAdviceFactory("/tmp/test")
        with self.assertRaises(TypeError):
            factory.run_advice("unknown_advice", {})
