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
from msprof_analyze.compare_tools.compare_backend.comparison_generator import ComparisonGenerator
from msprof_analyze.compare_tools.compare_backend.disaggregate.overall_perf_interface import OverallPerfInterface
from msprof_analyze.compare_tools.compare_backend.utils.compare_args import Args
from msprof_analyze.prof_common.constant import Constant
from msprof_analyze.prof_common.analyze_dict import AnalyzeDict
from msprof_analyze.prof_common.logger import get_logger

logger = get_logger()


class ComparisonInterface:
    def __init__(
        self,
        base_profiling_path: str,
        comparison_profiling_path: str = "",
        base_step: str = "",
        comparison_step: str = "",
        **kwargs,
    ):
        self.base_profiling_path = base_profiling_path
        if comparison_profiling_path:
            self._args = Args(
                base_profiling_path=base_profiling_path,
                comparison_profiling_path=comparison_profiling_path,
                base_step=base_step,
                comparison_step=comparison_step,
                use_kernel_type=kwargs.get("use_kernel_type", False),
            )

    def compare(self, compare_type: str) -> dict:
        return ComparisonGenerator(AnalyzeDict(vars(self._args))).run_interface(compare_type)

    def disaggregate_perf(self, compare_type: str) -> dict:
        if compare_type != Constant.OVERALL_COMPARE:
            logger.error('Invalid compare_type value: %s which not supported.', compare_type)
            return {}
        return OverallPerfInterface(self.base_profiling_path).run()
