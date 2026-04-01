# Copyright (c) 2025, Huawei Technologies Co., Ltd.
# All rights reserved.
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

import json
import unittest
from enum import Enum

from msprof_analyze.cluster_analyse.cluster_kernels_analysis.operator_mfu.operator_flops import (
    OperatorFLOPs,
    MatmulFLOPs,
    FlashAttentionFLOPs,
    FLOPsStrategyFactory,
    OperatorType,
    DataType,
)


class _DummyOperator(OperatorFLOPs):
    INPUT_TENSOR_INDEX = [0, 1]

    def calculate_flops(self):
        return 0


class TestOperatorFLOPs(unittest.TestCase):
    def test_parse_types_when_string_contains_mixed_cases_then_return_upper_tokens(self):
        result = OperatorFLOPs.parse_types(" float ;dt_bf16 ; ")
        self.assertEqual(result, ["FLOAT", "DT_BF16"])

    def test_parse_shapes_when_mixed_shapes_and_empty_then_return_list_of_lists(self):
        result = OperatorFLOPs.parse_shapes("2,3; ;4,5,6")
        self.assertEqual(result, [[2, 3], [], [4, 5, 6]])

    def test_format_data_type_when_invalid_type_then_raise_value_error(self):
        with self.assertRaises(ValueError):
            OperatorFLOPs.format_data_type("random_type")

    def test_determine_data_type_when_types_mismatch_then_raise_value_error(self):
        op = _DummyOperator(input_types="float;int8", input_shapes="1,1;1,1")
        with self.assertRaises(ValueError):
            op.determine_data_type()

    def test_determine_data_type_when_types_valid_then_return_enum(self):
        op = _DummyOperator(input_types="float;float", input_shapes="1,1;1,1")
        result = op.determine_data_type()
        self.assertEqual(result, DataType.FLOAT16)


class TestMatmulFLOPs(unittest.TestCase):
    def test_calculate_flops_when_nd_format_then_return_expected_value(self):
        kwargs = {
            "input_shapes": "2,3;3,4",
            "input_types": "float;float",
            "output_shapes": "2,4",
        }
        matmul = MatmulFLOPs(**kwargs)
        self.assertEqual(matmul.calculate_flops(), 2 * 4 * 3 * 2)

    def test_calculate_flops_when_nz_format_then_return_expected_value(self):
        kwargs = {
            "input_shapes": "56,15,16,16;1,15,16,16",  # 转换成ND，相当于15*16,56*16;15*16,1*16
            "input_types": "float;float",
            "output_shapes": "1,56,16,16",  # 转换成ND，相当于56*16,1*16
        }
        matmul = MatmulFLOPs(**kwargs)
        expected_m = 56 * 16
        expected_n = 1 * 16
        expected_k = 15 * 16
        self.assertEqual(matmul.calculate_flops(), expected_m * expected_n * expected_k * 2)

    def test_calculate_flops_when_unknown_format_then_raise_value_error(self):
        kwargs = {
            "input_shapes": "2;2",
            "input_types": "float;float",
            "output_shapes": "2",
        }
        matmul = MatmulFLOPs(**kwargs)
        with self.assertRaises(ValueError):
            matmul.calculate_flops()


class TestFlashAttentionFLOPs(unittest.TestCase):
    def flash_attention_kwargs(self, operator_args):
        return {
            "input_shapes": "1,2,3,4;1,2,3,4;1,2,3,4",
            "input_types": "float;float;float",
            "operator_args": json.dumps(operator_args),
        }

    def test_calculate_flops_when_common_layout_dense_then_return_full_attention(self):
        kwargs = self.flash_attention_kwargs({
            "input_layout": "BNSD",
            "sparse_mode": 0,
        })
        flops = FlashAttentionFLOPs(**kwargs)
        expected = 2 * (1 * 2 * 3 * 3 * (4 + 4))
        self.assertEqual(flops.calculate_flops(), expected)

    def test_calculate_flops_when_tnd_layout_then_use_actual_seq_lengths(self):
        kwargs = {
            "input_shapes": "2,3,4;2,3,4;2,3,4",
            "input_types": "float;float;float",
            "operator_args": json.dumps({
                "input_layout": "TND",
                "actual_seq_qlen": [2, 5],
                "actual_seq_kvlen": [2, 5],
            }),
        }
        flops = FlashAttentionFLOPs(**kwargs)
        acl_seq_workload = 2 * 2 + 3 * 3
        expected = 2 * 3 * (4 + 4) * acl_seq_workload
        self.assertEqual(flops.calculate_flops(), expected)

    def test_calculate_flops_when_missing_operator_args_then_raise_value_error(self):
        kwargs = {
            "input_shapes": "1,2,3,4;1,2,3,4;1,2,3,4",
            "input_types": "float;float;float",
        }
        flops = FlashAttentionFLOPs(**kwargs)
        with self.assertRaises(ValueError):
            flops.calculate_flops()


class TestFLOPsStrategyFactory(unittest.TestCase):
    def test_get_strategy_when_operator_type_supported_then_return_class(self):
        strategy = FLOPsStrategyFactory.get_strategy(OperatorType.MATMUL)
        self.assertIs(strategy, MatmulFLOPs)

    def test_create_strategy_when_operator_type_invalid_then_raise_value_error(self):
        class FakeOperator(Enum):
            UNKNOWN = "UNKNOWN"

        with self.assertRaises(ValueError):
            FLOPsStrategyFactory.create_strategy(FakeOperator.UNKNOWN, input_shapes="", input_types="")
