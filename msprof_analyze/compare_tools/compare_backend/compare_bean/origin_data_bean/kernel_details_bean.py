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
import math
from decimal import Decimal

import pandas as pd

from msprof_analyze.compare_tools.compare_backend.utils.common_func import convert_to_float, convert_to_decimal
from msprof_analyze.compare_tools.compare_backend.compare_config.compare_config import CompareConfig
from msprof_analyze.prof_common.constant import Constant


class KernelDetailsBean:
    __slots__ = ['_data', '_op_type', '_name', '_input_shapes', '_aiv_vec_time', '_aicore_time', '_mac_time',
                 '_duration', '_start_time', '_step_id']

    def __init__(self, data: dict):
        self._data = data
        self._op_type = ""
        self._name = ""
        self._input_shapes = ""
        self._aiv_vec_time = 0.0
        self._aicore_time = 0.0
        self._mac_time = 0.0
        self._duration = 0.0
        self._start_time = Decimal("0")
        self._step_id = ""
        self.init()

    @property
    def op_type(self) -> str:
        return self._op_type

    @property
    def name(self) -> str:
        return self._name

    @property
    def input_shapes(self) -> str:
        return self._input_shapes

    @property
    def aiv_vec_time(self) -> float:
        if self._aiv_vec_time == "" or self._aiv_vec_time == "N/A":
            return float("nan")
        return convert_to_float(self._aiv_vec_time)

    @property
    def aicore_time(self) -> float:
        if self._aicore_time == "" or self._aicore_time == "N/A":
            return float("nan")
        return convert_to_float(self._aicore_time)

    @property
    def mac_time(self) -> float:
        if self._mac_time == "" or self._mac_time == "N/A":
            return float("nan")
        return convert_to_float(self._mac_time)

    @property
    def duration(self) -> float:
        return convert_to_float(self._duration)

    @property
    def dur(self) -> float:
        return convert_to_float(self._duration)

    @property
    def start_time(self) -> Decimal:
        return convert_to_decimal(self._start_time)

    @property
    def end_time(self) -> Decimal:
        return self.start_time + convert_to_decimal(self._duration)

    @property
    def step_id(self) -> int:
        return int(self._step_id) if self._step_id else Constant.VOID_STEP

    @property
    def mc2_computing_time(self):
        return (max(float(self._data.get("aic_mac_time(us)", 0)), float(self._data.get("aic_mte2_time(us)", 0))) +
                float(self._data.get("aiv_time(us)", 0)))

    def is_hide_op_pmu(self):
        if "mac_time(us)" in self._data.keys() or "aiv_vec_time(us)" in self._data.keys():
            return False
        return True

    def is_vector(self):
        if not pd.isna(self.aiv_vec_time) and self.aiv_vec_time > 0:
            return True
        if not pd.isna(self.mac_time) and math.isclose(self.mac_time, 0.0):
            return True
        return False

    def is_invalid(self):
        if pd.isna(self.aiv_vec_time) and pd.isna(self.mac_time):
            return True
        return False

    def is_invalid_op_type(self):
        if pd.isna(self.op_type) or self.op_type == "N/A" or self.op_type == "":
            return True
        return False

    def is_fa_bwd(self):
        return 'bwd' in self.op_type.lower() or 'grad' in self.op_type.lower()

    def is_sdma(self):
        return self.name.lower().startswith("aclnninplacecopy") and "tensormove" in self.name.lower()

    def is_flash_attention(self):
        return "flashattention" in self.op_type.lower() or "fusedinferattention" in self.op_type.lower()

    def is_matmul(self):
        return "matmul" in self.op_type.lower()

    def is_conv(self):
        return self.op_type.lower().startswith("conv")

    def is_conv_bwd(self):
        lower_op_type = self.op_type.lower()
        return any(bwd in lower_op_type for bwd in Constant.BWD_LIST)

    def is_page_attention(self):
        return "pagedattention" in self.op_type.lower()

    def is_trans(self):
        return any(trans_mask in self.name.lower() for trans_mask in CompareConfig().trans_mask)

    def is_cube_kernel_cat(self):
        return self.mac_time > 0 or self.aicore_time > 0

    def is_mc2(self):
        return self._name.lower() in CompareConfig().mc2_kernel

    def init(self):
        self._op_type = self._data.get('Type', "")
        self._name = self._data.get('Name', "")
        self._input_shapes = self._data.get('Input Shapes', "")
        self._aiv_vec_time = self._data.get('aiv_vec_time(us)', "")
        self._aicore_time = self._data.get("aicore_time(us)", "")
        self._mac_time = self._data.get('mac_time(us)', "")
        self._duration = self._data.get('Duration(us)', 0)
        self._step_id = self._data.get('Step Id', self._data.get('Step ID', ""))
        self._start_time = Decimal(self._data.get("Start Time(us)", "0"))
