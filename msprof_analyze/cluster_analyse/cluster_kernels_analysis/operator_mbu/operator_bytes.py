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

from math import prod
from typing import List

DEFAULT_DTYPE_BYTES = 2  # 无法识别时按 FP16 处理
DT_PREFIX = "DT_"  # 采集侧数据类型可能带 DT_ 前缀（如 DT_FLOAT16），查表前统一剥离

DTYPE_BYTES = {
    "FLOAT": 4,
    "FLOAT32": 4,
    "FLOAT16": 2,
    "FP16": 2,
    "HALF": 2,
    "BF16": 2,
    "BFLOAT16": 2,
    "INT8": 1,
    "UINT8": 1,
    "BOOL": 1,
    "INT16": 2,
    "UINT16": 2,
    "INT32": 4,
    "UINT32": 4,
    "INT64": 8,
    "UINT64": 8,
    "DOUBLE": 8,
    "FLOAT64": 8,
    "FP8": 1,
    "HIFLOAT8": 1,
}


def dtype_size(dtype: str) -> int:
    """返回 dtype 每个元素的字节数，未知类型按 FP16(2 字节) 处理。

    兼容带引号的取值与 DT_ 前缀变体（如 DT_FLOAT16 与 FLOAT16 等价）。
    """
    if not dtype:
        return DEFAULT_DTYPE_BYTES
    key = dtype.strip().strip("\"'").upper()
    if key not in DTYPE_BYTES and key.startswith(DT_PREFIX):
        key = key[len(DT_PREFIX) :]
    return DTYPE_BYTES.get(key, DEFAULT_DTYPE_BYTES)


def parse_shapes(shape_str: str) -> List[List[int]]:
    """解析形如 "1,2;3,4;" 的字符串为 [[1, 2], [3, 4], []]。"""
    shapes = []
    if not isinstance(shape_str, str):
        return shapes
    for part in shape_str.split(';'):
        part = part.strip()
        if part:
            try:
                shapes.append([int(d.strip()) for d in part.split(',') if d.strip()])
            except ValueError:
                shapes.append([])
        else:
            shapes.append([])
    return shapes


def parse_types(type_str: str) -> List[str]:
    """解析形如 "DT_BF16;;FLOAT" 的字符串为 ["DT_BF16", "", "FLOAT"]（大写）。

    保留空段，使类型与 parse_shapes 解析出的张量按位置一一对应；
    缺失类型在 dtype_size 中按 FP16 回退，避免后续张量 dtype 串位。
    """
    if not isinstance(type_str, str):
        return []
    return [t.strip().upper() for t in type_str.split(';')]


def _tensor_group_bytes(shapes: List[List[int]], types: List[str]) -> int:
    total = 0
    for idx, shape in enumerate(shapes):
        # 跳过空 shape，以及含动态/非法维度(<=0，如动态 shape 记为 -1)的张量，避免负字节。
        if not shape or any(dim <= 0 for dim in shape):
            continue
        dtype = types[idx] if idx < len(types) else ""
        total += prod(shape) * dtype_size(dtype)
    return total


def compute_access_bytes(input_shapes: str, input_types: str, output_shapes: str, output_types: str) -> int:
    """访存字节 = Σ输入张量字节 + Σ输出张量字节（HBM 读写总流量）。

    四个入参均为字符串；dtype 列表长度不足时按位置回退 FP16。
    """
    in_bytes = _tensor_group_bytes(parse_shapes(input_shapes), parse_types(input_types))
    out_bytes = _tensor_group_bytes(parse_shapes(output_shapes), parse_types(output_types))
    return in_bytes + out_bytes
