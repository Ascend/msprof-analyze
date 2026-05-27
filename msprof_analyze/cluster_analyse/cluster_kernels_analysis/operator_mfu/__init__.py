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

from msprof_analyze.cluster_analyse.cluster_kernels_analysis.operator_mfu.npu_flop_registry import (
    register_npu_flop,
    get_flop_func,
    get_npu_flop_registry,
    get_npu_flop_targets,
)
from msprof_analyze.cluster_analyse.cluster_kernels_analysis.operator_mfu.mfu_hook_manager import (
    MFUHookManager,
    is_mfu_enabled,
)
from msprof_analyze.cluster_analyse.cluster_kernels_analysis.operator_mfu.mfu_calculator import MFUCalculator

import msprof_analyze.cluster_analyse.cluster_kernels_analysis.operator_mfu.npu_flop_formulas


def install_mfu_hooks():
    from msprof_analyze.prof_common.logger import get_logger
    logger = get_logger()
    logger.info("[MFU] install_mfu_hooks() called from operator_mfu.__init__")
    MFUHookManager.install_from_env()


def uninstall_mfu_hooks():
    from msprof_analyze.prof_common.logger import get_logger
    logger = get_logger()
    logger.info("[MFU] uninstall_mfu_hooks() called from operator_mfu.__init__")
    MFUHookManager.uninstall()
