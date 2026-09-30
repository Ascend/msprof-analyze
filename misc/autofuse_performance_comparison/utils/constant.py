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
from enum import IntEnum


class DataType(IntEnum):
    DT_FLOAT = 0
    DT_FLOAT16 = 1
    DT_INT8 = 2
    DT_INT32 = 3
    DT_UINT8 = 4
    DT_INT16 = 6
    DT_UINT16 = 7
    DT_UINT32 = 8
    DT_INT64 = 9
    DT_UINT64 = 10
    DT_DOUBLE = 11
    DT_BOOL = 12
    DT_STRING = 13
    DT_DUAL_SUB_INT8 = 14
    DT_DUAL_SUB_UINT8 = 15
    DT_COMPLEX64 = 16
    DT_COMPLEX128 = 17
    DT_QINT8 = 18
    DT_QINT16 = 19
    DT_QINT32 = 20
    DT_QUINT8 = 21
    DT_QUINT16 = 22
    DT_RESOURCE = 23
    DT_STRING_REF = 24
    DT_DUAL = 25
    DT_VARIANT = 26
    DT_BF16 = 27
    DT_UNDEFINED = 28
    DT_INT4 = 29
    DT_UINT1 = 30
    DT_INT2 = 31
    DT_UINT2 = 32
    DT_COMPLEX32 = 33
    DT_HIFLOAT8 = 34
    DT_FLOAT8_E5M2 = 35
    DT_FLOAT8_E4M3FN = 36
    DT_FLOAT8_E8M0 = 37
    DT_FLOAT6_E3M2 = 38
    DT_FLOAT6_E2M3 = 39
    DT_FLOAT4_E2M1 = 40
    DT_FLOAT4_E1M2 = 41
    DT_MAX = 42


STRING_TO_DTYPE = dict(DataType.__members__)
