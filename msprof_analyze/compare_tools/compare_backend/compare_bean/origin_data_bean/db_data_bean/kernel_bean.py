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
from decimal import Decimal

from msprof_analyze.prof_common.constant import Constant
from msprof_analyze.compare_tools.compare_backend.compare_config.compare_config import CompareConfig
from msprof_analyze.compare_tools.compare_backend.utils.common_func import convert_to_decimal
from msprof_analyze.prof_common.utils import convert_to_float


class KernelBean:
    def __init__(self, data):
        self._data = data

    @property
    def name(self):
        return self._data.get("OpName", "")

    @property
    def dur(self):
        return self._data.get("Duration") / Constant.NS_TO_US if self._data.get("Duration") else 0

    @property
    def start_time(self) -> Decimal:
        return convert_to_decimal(self._data.get("startNs", 0)) / Constant.NS_TO_US

    @property
    def end_time(self) -> Decimal:
        return convert_to_decimal(self._data.get("endNs", 0)) / Constant.NS_TO_US

    @property
    def task_id(self):
        return self._data.get("TaskId", "")

    @property
    def stream_id(self):
        return self._data.get("streamId", "")

    @property
    def task_type(self):
        return self._data.get("TaskType", "")

    @property
    def rts_task_type(self):
        return self._data.get("rtsTaskType", "")

    @property
    def op_type(self):
        return self._data.get("opType", "")

    @property
    def core_type(self):
        return self.task_type

    @property
    def input_shapes(self):
        return self._data.get("InputShapes", "")

    @property
    def connection_id(self):
        return self._data.get("connectionId", "")

    def is_page_attention(self):
        return "pagedattention" in self.op_type.lower()

    def is_sdma(self):
        return self.name.lower().startswith("aclnninplacecopy") and "tensormove" in self.name.lower()

    def is_mc2(self):
        return self.name.lower() in CompareConfig().mc2_kernel

    def is_flash_attention(self):
        return "flashattention" in self.op_type.lower()

    def is_fa_bwd(self):
        return 'bwd' in self.op_type.lower() or 'grad' in self.op_type.lower()

    def is_conv(self):
        return self.op_type.lower().startswith("conv")

    def is_conv_bwd(self):
        lower_op_type = self.op_type.lower()
        return any(bwd in lower_op_type for bwd in Constant.BWD_LIST)

    def is_matmul(self):
        return "matmul" in self.op_type.lower()

    def is_trans(self):
        return any(trans_mask in self.name.lower() for trans_mask in CompareConfig().trans_mask)

    def is_cube_kernel_cat(self, pmu_data):
        if not pmu_data:
            return any((self.rts_task_type == "KERNEL_AICORE", self.rts_task_type == "KERNEL_MIX_AIC"))
        global_task_id = self._data.get("globalTaskId", "")
        return any(
            (
                pmu_data.get(global_task_id, {}).get("aic_total_time"),
                pmu_data.get(global_task_id, {}).get("aic_mac_time"),
            )
        )

    def mc2_computing_time(self, pmu_data):
        task_pmu = pmu_data.get(self._data.get("globalTaskId", ""), {})
        return (
            max(
                convert_to_float(task_pmu.get("aic_mac_time", 0)) / Constant.NS_TO_US,
                convert_to_float(task_pmu.get("aic_mte2_time", 0)) / Constant.NS_TO_US,
            )
            + convert_to_float(task_pmu.get("aiv_time", 0)) / Constant.NS_TO_US
        )
