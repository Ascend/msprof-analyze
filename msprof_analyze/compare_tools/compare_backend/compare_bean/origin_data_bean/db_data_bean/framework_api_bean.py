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
from decimal import Decimal

from msprof_analyze.compare_tools.compare_backend.utils.common_func import convert_to_decimal
from msprof_analyze.compare_tools.compare_backend.utils.common_func import convert_to_float
from msprof_analyze.prof_common.constant import Constant
from msprof_analyze.compare_tools.compare_backend.compare_config.compare_config import CompareConfig


class FrameworkApiBean:
    def __init__(self, data):
        self._data = data
        self.is_torch_op = False
        self.x_mode = True
        self._name = data.get("name") or ""
        self.pid = Constant.INVALID_VALUE

    @property
    def dur(self) -> float:
        return convert_to_float(self.end_time - self.start_time)

    @property
    def start_time(self) -> Decimal:
        return convert_to_decimal(self._data.get("startNs", 0)) / Constant.NS_TO_US

    @property
    def end_time(self) -> Decimal:
        return convert_to_decimal(self._data.get("endNs", 0)) / Constant.NS_TO_US

    @property
    def name(self) -> str:
        return self._name

    @property
    def lower_name(self) -> str:
        return self.name.lower()

    @property
    def connection_id(self):
        return self._data.get("connectionId", "")

    @property
    def cann_connection_id(self):
        return self._data.get("cann_connectionId", "")

    @property
    def input_dims(self):
        return self._data.get("inputShapes", Constant.NA)

    @property
    def input_type(self):
        return self._data.get("inputDtypes", Constant.NA)

    @property
    def call_stack(self):
        return self._data.get("callStack", Constant.NA)

    def reset_name(self, name):
        self._name = name

    def is_optimizer(self):
        return self.lower_name.startswith("optimizer")

    def is_step_profiler(self):
        return self.name.find("ProfilerStep#") != -1

    def is_fa_for_cpu_op(self) -> bool:
        """
        这个类在cpu op和gpu中均有用到，这里是在cpu op阶段判断
        """
        return any(cube_mask in self.lower_name for cube_mask in CompareConfig().fa_mask)

    def is_conv_for_cpu_op(self) -> bool:
        """
        这个类在cpu op和gpu中均有用到，这里是在cpu op阶段判断
        """
        return any(conv_mask in self.lower_name for conv_mask in CompareConfig().conv_mask)

    def is_matmul_for_cpu_op(self) -> bool:
        """
        这个类在cpu op和gpu中均有用到，这里是在cpu op阶段判断
        """
        return any(mm_mask in self.lower_name for mm_mask in CompareConfig().mm_mask)

    def is_bwd_for_cpu_op(self) -> bool:
        """
        这个类在cpu op和gpu中均有用到，这里是在cpu op阶段判断
        """
        return any(bwd_mask in self.lower_name for bwd_mask in Constant.BWD_LIST)

    def is_cpu_cube_op(self) -> bool:
        return self.is_matmul_for_cpu_op() or self.is_fa_for_cpu_op() or self.is_conv_for_cpu_op()

    def is_x_mode(self) -> bool:
        return self.x_mode
