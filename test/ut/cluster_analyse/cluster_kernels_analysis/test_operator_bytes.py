# Copyright (c) 2026, Huawei Technologies Co., Ltd.
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

import unittest
from unittest.mock import patch

from msprof_analyze.cluster_analyse.cluster_kernels_analysis.operator_mbu.operator_bytes import (
    dtype_size,
    parse_shapes,
    parse_types,
    compute_access_bytes,
)


class TestOperatorBytes(unittest.TestCase):
    def test_dtype_size_known_and_unknown(self):
        self.assertEqual(dtype_size("FLOAT16"), 2)
        self.assertEqual(dtype_size("DT_BF16"), 2)
        self.assertEqual(dtype_size("FLOAT"), 4)
        self.assertEqual(dtype_size("INT8"), 1)
        self.assertEqual(dtype_size("INT64"), 8)
        # 未知类型默认 2 字节
        self.assertEqual(dtype_size("WEIRD_TYPE"), 2)

    def test_dtype_size_dt_prefix_variants_and_quotes(self):
        # DT_ 前缀变体统一按去前缀后的类型解析
        self.assertEqual(dtype_size("DT_FLOAT16"), 2)
        self.assertEqual(dtype_size("DT_FLOAT"), 4)
        self.assertEqual(dtype_size("DT_INT64"), 8)
        self.assertEqual(dtype_size("DT_UINT8"), 1)
        # 带引号的取值应剥离后再查表，不应回退默认值
        self.assertEqual(dtype_size('"FLOAT"'), 4)
        self.assertEqual(dtype_size("'INT64'"), 8)

    def test_low_precision_types_and_packed_tensor_bytes(self):
        for dtype in ("FLOAT8_E4M3FN", "DT_FLOAT8_E5M2"):
            self.assertEqual(dtype_size(dtype), 1)
        self.assertEqual(dtype_size("DT_INT4"), 0.5)
        self.assertEqual(dtype_size("UINT4"), 0.5)
        self.assertEqual(compute_access_bytes("3;4", "INT4;UINT4", "3", "INT4"), 6)

    def test_unknown_dtype_warning_is_cached(self):
        dtype_size.cache_clear()
        with patch("msprof_analyze.cluster_analyse.cluster_kernels_analysis.operator_mbu.operator_bytes.logger") as log:
            self.assertEqual(dtype_size("UNKNOWN"), 2)
            self.assertEqual(dtype_size("UNKNOWN"), 2)
        log.warning.assert_called_once()

    def test_parse_shapes_with_empty_segment(self):
        self.assertEqual(parse_shapes("1,2;3,4;"), [[1, 2], [3, 4], []])

    def test_compute_access_bytes_matmul_fp16(self):
        # 输入 A[2,3] B[3,4] (FP16=2B)，输出 C[2,4] (FP16=2B)
        # bytes = (2*3 + 3*4)*2 + (2*4)*2 = (6+12)*2 + 8*2 = 36 + 16 = 52
        result = compute_access_bytes("2,3;3,4", "FLOAT16;FLOAT16", "2,4", "FLOAT16")
        self.assertEqual(result, 52)

    def test_compute_access_bytes_mixed_dtype_and_missing_types(self):
        # 输入两张量但只给一个 dtype，第二个按位置回退 FP16(2B)
        # 输入 [10] INT8(1B) + [10] FP16(2B) = 10 + 20 = 30; 输出 [10] FP16 = 20
        result = compute_access_bytes("10;10", "INT8", "10", "")
        self.assertEqual(result, 30 + 20)

    def test_compute_access_bytes_empty_inputs_return_zero(self):
        self.assertEqual(compute_access_bytes("", "", "", ""), 0)

    def test_compute_access_bytes_skips_dynamic_negative_dim(self):
        # 动态维度记为 -1 的张量应被跳过，不产生负字节
        # 输入张量1 [-1,512] 跳过；张量2 [4] FP16=8；输出 [4] FP16=8
        result = compute_access_bytes("-1,512;4", "FLOAT16;FLOAT16", "4", "FLOAT16")
        self.assertEqual(result, 8 + 8)

    def test_compute_access_bytes_middle_empty_dtype_keeps_alignment(self):
        # 中间 dtype 缺失时，类型与 shape 仍按位置对齐(不串位)
        # shapes [8,16]=128,[4,8]=32,[2,64]=128; types FLOAT(4),''->FP16(2),INT8(1)
        # bytes = 128*4 + 32*2 + 128*1 = 512 + 64 + 128 = 704
        result = compute_access_bytes("8,16;4,8;2,64", "FLOAT;;INT8", "", "")
        self.assertEqual(result, 704)

    def test_parse_types_non_string_returns_empty(self):
        self.assertEqual(parse_types(None), [])

    def test_parse_shapes_non_string_and_invalid_dim(self):
        self.assertEqual(parse_shapes(None), [])
        # 非整数维度触发 ValueError 分支 -> 该段解析为空 list
        self.assertEqual(parse_shapes("1,2;a,b"), [[1, 2], []])


if __name__ == "__main__":
    unittest.main()
