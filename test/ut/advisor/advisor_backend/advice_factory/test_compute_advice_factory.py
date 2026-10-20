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
