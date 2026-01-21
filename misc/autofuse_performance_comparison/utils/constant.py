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
from enum import IntEnum


class DataType(IntEnum):
    DT_FLOAT = 0,
    DT_FLOAT16 = 1,
    DT_INT8 = 2,
    DT_INT32 = 3,
    DT_UINT8 = 4,
    DT_INT16 = 6,
    DT_UINT16 = 7,
    DT_UINT32 = 8,
    DT_INT64 = 9,
    DT_UINT64 = 10,
    DT_DOUBLE = 11,
    DT_BOOL = 12,
    DT_STRING = 13,
    DT_DUAL_SUB_INT8 = 14,
    DT_DUAL_SUB_UINT8 = 15,
    DT_COMPLEX64 = 16,
    DT_COMPLEX128 = 17,
    DT_QINT8 = 18,
    DT_QINT16 = 19,
    DT_QINT32 = 20,
    DT_QUINT8 = 21,
    DT_QUINT16 = 22,
    DT_RESOURCE = 23,
    DT_STRING_REF = 24,
    DT_DUAL = 25,
    DT_VARIANT = 26,
    DT_BF16 = 27,
    DT_UNDEFINED = 28,
    DT_INT4 = 29,
    DT_UINT1 = 30,
    DT_INT2 = 31,
    DT_UINT2 = 32,
    DT_COMPLEX32 = 33,
    DT_HIFLOAT8 = 34,
    DT_FLOAT8_E5M2 = 35,
    DT_FLOAT8_E4M3FN = 36,
    DT_FLOAT8_E8M0 = 37,
    DT_FLOAT6_E3M2 = 38,
    DT_FLOAT6_E2M3 = 39,
    DT_FLOAT4_E2M1 = 40,
    DT_FLOAT4_E1M2 = 41,
    DT_MAX = 42

STRING_TO_DTYPE = {name: value for name, value in DataType.__members__.items()}