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
import argparse
import ast
import datetime
import os.path
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from msprof_analyze.compare_tools.compare_backend.comparison_generator import ComparisonGenerator
from msprof_analyze.prof_common.analyze_dict import AnalyzeDict
from msprof_analyze.prof_common.logger import get_logger
from msprof_analyze.prof_common.path_manager import PathManager

logger = get_logger()


def main():
    parser = argparse.ArgumentParser(description="Compare trace of GPU and NPU")
    parser.add_argument(
        "base_profiling_path",
        type=PathManager.expanduser_for_argumentparser,
        default='',
        help="Path of the profiling data",
    )
    parser.add_argument(
        "comparison_profiling_path",
        type=PathManager.expanduser_for_argumentparser,
        default='',
        help="Path of the benchmark data",
    )
    parser.add_argument(
        "--enable_profiling_compare", default=False, action='store_true', help="Enable overall performance comparison"
    )
    parser.add_argument(
        "--enable_operator_compare", default=False, action='store_true', help="Enable operator performance comparison"
    )
    parser.add_argument(
        "--enable_memory_compare", default=False, action='store_true', help="Enable operator memory comparison"
    )
    parser.add_argument(
        "--enable_communication_compare",
        default=False,
        action='store_true',
        help="Enable communication performance comparison",
    )
    parser.add_argument(
        "--enable_api_compare", default=False, action='store_true', help="Enable API performance comparison"
    )
    parser.add_argument(
        "--enable_kernel_compare", default=False, action='store_true', help="Enable kernel performance comparison"
    )
    parser.add_argument("--disable_details", default=False, action='store_true', help="Hide detailed comparison")
    parser.add_argument("--disable_module", default=False, action='store_true', help="Hide module comparison")
    parser.add_argument(
        '-o',
        "--output_path",
        type=PathManager.expanduser_for_argumentparser,
        default='',
        help="Path of comparison result",
    )
    parser.add_argument("--max_kernel_num", type=int, help="The number of kernels per torch op is limited.")
    parser.add_argument(
        "--op_name_map",
        type=ast.literal_eval,
        default={},
        help="The mapping of operator names equivalent to GPUs and NPUs in the form of dictionaries.",
    )
    parser.add_argument(
        "--use_input_shape", default=False, action='store_true', help="Enable precise matching of operators"
    )
    parser.add_argument("--gpu_flow_cat", type=str, default='', help="Identifier of the GPU connection")
    parser.add_argument("--base_step", type=str, default='', help="Comparison step for performance data to be compared")
    parser.add_argument(
        "--comparison_step", type=str, default='', help="Comparison step for benchmark performance data"
    )
    parser.add_argument(
        "--force",
        action='store_true',
        help="Indicates whether to skip verification of the owner, size, and permissions.",
    )
    parser.add_argument(
        "--use_kernel_type", action='store_true', help="Indicates whether kernel compare use op_statistic.csv"
    )
    args = parser.parse_args()

    ComparisonGenerator(AnalyzeDict(vars(args))).run()


if __name__ == "__main__":
    start_time = datetime.datetime.utcnow()
    main()
    end_time = datetime.datetime.utcnow()
    logger.info('The comparison task has been completed in a total time of %s', end_time - start_time)
