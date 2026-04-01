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

from abc import abstractmethod, ABC
from enum import Enum
from typing import Tuple, List
import json
import numpy as np


class OperatorType(Enum):
    """算子类型枚举"""
    MATMUL = "Matmul"
    FLASH_ATTENTION = "FlashAttention"


OP_TYPE_MAP = {
    OperatorType.MATMUL: ["MatMulV2", "MatMulV3"],
    OperatorType.FLASH_ATTENTION: ["FlashAttentionScore"]
}


class DataType(Enum):
    FLOAT16 = "FLOAT16"
    INT8 = "INT8"


class OperatorFLOPs(ABC):
    DTYPE_MAP = {
        "FLOAT": DataType.FLOAT16,
        "FLOAT16": DataType.FLOAT16,
        "BF16": DataType.FLOAT16,
        "DT_BF16": DataType.FLOAT16,
        "INT8": DataType.INT8,
    }

    INPUT_TENSOR_INDEX = []
    RELATED_COLUMNS = ['input_shapes', 'input_types']

    def __init__(self, **kwargs):
        self.input_shapes = self.parse_shapes(kwargs.get("input_shapes", ""))
        self.input_types = self.parse_types(kwargs.get("input_types", ""))
        self.kwargs = kwargs

    @staticmethod
    def parse_types(type_str: str) -> List[str]:
        """
        解析数据类型
        type_str: e.g. "DT_BF16;FLOAT;INT32;FLOAT"
        return: e.g. ["DT_BF16", "FLOAT", "INT32", "FLOAT"]
        """
        return [t.strip().upper() for t in type_str.split(';') if t.strip()]

    @staticmethod
    def parse_shapes(shape_str: str) -> List[List[int]]:
        """
        解析inputs/output_shapes
        shape_str: e.g. "64512,10,128;64512,1,128;64512,1,128;;"
        return: [[64512,10,128], [64512,10,128], [64512,10,128], [], []]
        """
        shapes = []
        for shape_part in shape_str.split(';'):
            if shape_part.strip():
                shape = [int(dim.strip()) for dim in shape_part.split(',') if dim.strip()]
                shapes.append(shape)
            else:
                shapes.append([])
        return shapes

    @staticmethod
    def format_data_type(data_type: str):
        # 解析数据类型
        dtype = OperatorFLOPs.DTYPE_MAP.get(data_type.upper(), None)
        if not dtype:
            raise ValueError(f"Not supported data type: {data_type}")
        return dtype

    @abstractmethod
    def calculate_flops(self):
        """计算FLOPs"""
        pass

    def determine_data_type(self):
        """确定数据类型"""
        index_list = self.INPUT_TENSOR_INDEX
        if not index_list:
            raise ValueError(f"Invalid INPUT_TENSOR_INDEX for {self.__class__.__name__} to determine_data_type.")
        if len(self.input_types) < max(index_list) + 1:
            raise ValueError(f"Invalid input types, length of type list should be greater than {max(index_list)}.")
        data_type = self.input_types[index_list[0]]
        for index in index_list[1:]:
            if self.input_types[index] != data_type:
                raise ValueError(f"Invalid input types, tensor data types should be same.")
        return self.format_data_type(self.input_types[0])


class MatmulFLOPs(OperatorFLOPs):
    INPUT_TENSOR_INDEX = [0, 1]
    RELATED_COLUMNS = ['input_shapes', 'input_types', "output_shapes"]

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.output_shapes = self.parse_shapes(kwargs['output_shapes']) if 'output_shapes' in kwargs else None

    def calculate_flops(self):
        """
        计算矩阵乘法的FLOPs = m * n * k * 2 (乘加算2次操作)
        """
        if self.output_shapes is None:
            raise ValueError("Matmul FLOPs calculation requires output_shapes")

        if self._is_input_format_nd():
            m, n, k = self._parse_dims_for_nd_format()
        elif self._is_input_format_nz():
            m, n, k = self._parse_dims_for_nz_format()
        else:
            raise ValueError(f"Unknown format for Matmul.")
        return m * n * k * 2

    def _parse_dims_for_nd_format(self):
        m, n = self.output_shapes[0][0], self.output_shapes[0][1]
        shape_a = self.input_shapes[0]
        k = shape_a[0] if shape_a[0] != m else shape_a[1]
        return m, n, k

    def _parse_dims_for_nz_format(self):
        m = self.output_shapes[0][1] * self.output_shapes[0][2]
        n = self.output_shapes[0][0] * self.output_shapes[0][3]
        shape_a_nd = [self.input_shapes[0][1] * self.input_shapes[0][2],
                      self.input_shapes[0][0] * self.input_shapes[0][3]]
        k = shape_a_nd[0] if shape_a_nd[0] != m else shape_a_nd[1]
        return m, n, k

    def _is_input_format_nd(self) -> bool:
        return self._validate_format(output_dims=2, input_dims=2)

    def _is_input_format_nz(self) -> bool:
        return self._validate_format(output_dims=4, input_dims=4)

    def _validate_format(self, output_dims: int, input_dims: int) -> bool:
        if not (len(self.output_shapes) == 1 and
                len(self.output_shapes[0]) == output_dims):
            return False

        if len(self.input_shapes) < max(self.INPUT_TENSOR_INDEX) + 1:
            return False

        for i in self.INPUT_TENSOR_INDEX:
            if len(self.input_shapes[i]) != input_dims:
                return False

        return True


class FlashAttentionFLOPs(OperatorFLOPs):
    INPUT_TENSOR_INDEX = [0, 1, 2]
    RELATED_COLUMNS = ['input_shapes', 'input_types', "operator_args"]

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.input_layout = None
        self.sparse_mode = None
        self.actual_seq_qlen = None
        self.actual_seq_kvlen = None
        if 'operator_args' in kwargs:
            self._parse_operator_args(kwargs['operator_args'])

    def calculate_flops(self) -> Tuple[int, str]:
        if self.input_layout is None:
            raise ValueError("FlashAttention FLOPs failed")

        if self.input_layout == "TND":
            return self._calculate_tnd_layout_flops()
        else:
            return self._calculate_common_layout_flops()

    def _parse_operator_args(self, args: str):
        args_dict = json.loads(args)
        if 'input_layout' in args_dict:
            self.input_layout = args_dict.get('input_layout')
            self.sparse_mode = args_dict.get('sparse_mode')
            self.actual_seq_qlen = args_dict.get('actual_seq_qlen')
            self.actual_seq_kvlen = args_dict.get('actual_seq_kvlen')
        elif 'is_causal' in args_dict:
            is_causal = args_dict.get('is_causal')
            self.input_layout = 'BNSD'
            self.sparse_mode = 2 if is_causal else 0

    def _calculate_common_layout_flops(self):
        if self.sparse_mode is None:
            raise ValueError("Invalid operator_args, can not get sparse_mode")
        q_b, q_n, q_s, q_d = self._parse_dims(self.input_shapes[0])
        k_b, k_n, k_s, k_d = self._parse_dims(self.input_shapes[1])
        full_attention = 2 * (q_b * q_n * q_s * k_s * (q_d + k_d))
        if self.sparse_mode == 0:
            return full_attention
        elif q_s == k_s and self.sparse_mode in [2, 3]:
            return full_attention * 0.5
        elif q_s > k_s and self.sparse_mode == 2:
            return full_attention * (q_s * k_s - k_s * k_s / 2) / (k_s * k_s)
        elif q_d > k_d and self.sparse_mode == 3:
            return full_attention * (k_s * k_s / 2) / (q_s * k_s)
        elif q_d < k_d and self.sparse_mode == 2:
            return full_attention * (q_s * q_s / 2) / (q_s * k_s)
        elif q_d < k_d and self.sparse_mode == 3:
            return full_attention * (q_s * k_s - q_s * q_s / 2) / (q_s * k_s)
        else:
            raise ValueError("Unknown flops formula.")

    def _calculate_tnd_layout_flops(self):
        if not self.actual_seq_qlen or not self.actual_seq_kvlen:
            raise ValueError("Invalid operator args, should contain actual_seq_qlen and actual_seq_kvlen")
        q_t, q_n, q_d = self.input_shapes[0]
        k_t, k_n, k_d = self.input_shapes[1]

        q_lens = self._parse_seq_len(self.actual_seq_qlen)
        kv_lens = self._parse_seq_len(self.actual_seq_kvlen)
        if len(q_lens) != len(kv_lens) or any(q_lens) <= 0 or any(kv_lens) <= 0:
            raise ValueError("Invalid actual_seq_qlen or actual_seq_kvlen")
        acl_seq_workload = np.dot(q_lens, kv_lens)
        workload = 2 * q_n * (q_d + k_d) * acl_seq_workload
        return workload

    def _parse_seq_len(self, ori_seq_lens):
        seq_lens = ori_seq_lens.copy()
        while seq_lens and seq_lens[-1] == 0:
            seq_lens.pop()
        if not seq_lens:
            return []
        return [seq_lens[0]] + [curr - prev for prev, curr in zip(seq_lens, seq_lens[1:])]

    def _parse_dims(self, tensor_shape):
        if self.input_layout == "BNSD":
            b, n, s, d = tensor_shape
            return b, n, s, d
        elif self.input_layout == "BSND":
            b, s, n, d = tensor_shape
            return b, n, s, d
        elif self.input_layout == "BSH":
            b, s, d = tensor_shape
            return b, 1, s, d
        elif self.input_layout == "SBH":
            s, b, d = tensor_shape
            return b, 1, s, d
        else:
            raise ValueError("Invalid layout for FlashAttention input tensor.")


class FLOPsStrategyFactory:
    """FLOPs策略工厂"""

    strategies = {
        OperatorType.MATMUL: MatmulFLOPs,
        OperatorType.FLASH_ATTENTION: FlashAttentionFLOPs
    }

    @classmethod
    def get_strategy(cls, operator_type: OperatorType):
        return cls.strategies.get(operator_type)

    @classmethod
    def create_strategy(cls, operator_type: OperatorType, **kwargs):
        # 创建策略实例
        strategy_class = cls.get_strategy(operator_type)
        if not strategy_class:
            raise ValueError(f"Unsupported operator type: {operator_type}")
        return strategy_class(**kwargs)
