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

from msprof_analyze.cluster_analyse.cluster_utils.parallel_strategy_calculator import ParallelStrategyCalculator


class TestParallelStrategyCalculator(unittest.TestCase):
    def test_parallel_strategy_calculator_should_raise_runtime_error_when_dp4_ep3(self):
        with self.assertRaises(RuntimeError):
            calculator = ParallelStrategyCalculator(
                world_size=16,
                tensor_model_parallel_size=1,
                pipeline_model_parallel_size=4,
                data_parallel_size=4,
                context_parallel_size=1,
                expert_model_parallel_size=3)

            calculator.run()

    def test_parallel_strategy_calculator_should_raise_runtime_error_when_dp1_pp4_tp2_world_size16(self):
        with self.assertRaises(RuntimeError):
            calculator = ParallelStrategyCalculator(
                world_size=16,
                tensor_model_parallel_size=2,
                pipeline_model_parallel_size=4,
                data_parallel_size=1,
                context_parallel_size=1,
                expert_model_parallel_size=1)

            calculator.run()

    def test_parallel_strategy_calculator_dp2_pp4_tp2(self):
        calculator = ParallelStrategyCalculator(
            world_size=16,
            tensor_model_parallel_size=2,
            pipeline_model_parallel_size=4,
            data_parallel_size=2,
            context_parallel_size=1,
            expert_model_parallel_size=1)

        # dp index, pp index, tp index
        expected_res = [
            (0, 0, 0), (0, 0, 1), (1, 0, 0), (1, 0, 1), (0, 1, 0), (0, 1, 1), (1, 1, 0), (1, 1, 1),
            (0, 2, 0), (0, 2, 1), (1, 2, 0), (1, 2, 1), (0, 3, 0), (0, 3, 1), (1, 3, 0), (1, 3, 1)
        ]
        res = calculator.run()
        self.assertEqual(res, expected_res)
