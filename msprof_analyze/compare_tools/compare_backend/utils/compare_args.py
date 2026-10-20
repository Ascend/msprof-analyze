# -------------------------------------------------------------------------
# This file is part of the MindStudio project.
# Copyright (c) 2024 Huawei Technologies Co.,Ltd.
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


class Args:
    def __init__(
        self,
        base_profiling_path: str = "",
        comparison_profiling_path: str = "",
        enable_profiling_compare: bool = False,
        enable_operator_compare: bool = False,
        enable_memory_compare: bool = False,
        enable_communication_compare: bool = False,
        enable_api_compare: bool = False,
        enable_kernel_compare: bool = False,
        disable_details: bool = False,
        output_path: str = "",
        max_kernel_num: int = None,
        op_name_map: dict = None,
        use_input_shape: bool = False,
        gpu_flow_cat: str = "",
        base_step: str = "",
        comparison_step: str = "",
        use_kernel_type: bool = False,
    ):
        self.base_profiling_path = base_profiling_path
        self.comparison_profiling_path = comparison_profiling_path
        self.enable_profiling_compare = enable_profiling_compare
        self.enable_operator_compare = enable_operator_compare
        self.enable_memory_compare = enable_memory_compare
        self.enable_communication_compare = enable_communication_compare
        self.enable_api_compare = enable_api_compare
        self.enable_kernel_compare = enable_kernel_compare
        self.disable_details = disable_details
        self.output_path = output_path
        self.max_kernel_num = max_kernel_num
        self.op_name_map = op_name_map if op_name_map is not None else {}
        self.use_input_shape = use_input_shape
        self.gpu_flow_cat = gpu_flow_cat
        self.base_step = base_step
        self.comparison_step = comparison_step
        self.use_kernel_type = use_kernel_type
