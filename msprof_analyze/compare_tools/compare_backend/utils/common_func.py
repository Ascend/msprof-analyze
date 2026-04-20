# Copyright (c) 2024, Huawei Technologies Co., Ltd.
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
from decimal import Decimal
from difflib import SequenceMatcher
from msprof_analyze.prof_common.logger import get_logger

logger = get_logger()


def calculate_diff_ratio(base_value: float, comparison_value: float):
    if not base_value and not comparison_value:
        ratio = 1.0
    else:
        ratio = float('inf') if not base_value else round(comparison_value / base_value, 4)
    return [round(comparison_value - base_value, 2), ratio]


def update_order_id(data_list: list):
    for index, data in enumerate(data_list):
        if data:
            data[0] = index + 1


def convert_to_float(data: any) -> float:
    try:
        float_value = float(data)
    except Exception:
        logger.warning('Invalid profiling data which failed to convert data to float.')
        return 0.0
    return float_value


def convert_to_decimal(data: any) -> Decimal:
    try:
        decimal_value = Decimal(data)
    except Exception:
        logger.warning('Invalid profiling data which failed to convert data to decimal.')
        return Decimal(0)
    return decimal_value


def longest_common_subsequence_matching(base_ops, comparison_ops, name_func):
    base_sequence = [name_func(op) for op in base_ops]
    comparison_sequence = [name_func(op) for op in comparison_ops]
    matcher = SequenceMatcher(None, base_sequence, comparison_sequence, autojunk=False)
    result = []
    i = j = 0
    for block in matcher.get_matching_blocks():
        while i < block.a:
            result.append([base_ops[i], None])
            i += 1
        while j < block.b:
            result.append([None, comparison_ops[j]])
            j += 1
        match_len = block.size
        for k in range(match_len):
            result.append([base_ops[i + k], comparison_ops[j + k]])
        i += match_len
        j += match_len
    while i < len(base_ops):
        result.append([base_ops[i], None])
        i += 1
    while j < len(comparison_ops):
        result.append([None, comparison_ops[j]])
        j += 1
    return result


class BitMap:

    def __init__(self, size):
        self.size = size
        # 使用 bytearray 存储位信息
        self.bits = bytearray((size + 7) // 8)

    def __contains__(self, n: int) -> bool:
        """检查数字是否在位图中"""
        return bool(self.bits[n >> 3] & (1 << (n & 7)))

    def add(self, n: int):
        """添加一个数字到位图"""
        self.bits[n >> 3] |= 1 << (n & 7)  # n >> 3 等价于 n // 8, n & 7 等价于 n % 8
