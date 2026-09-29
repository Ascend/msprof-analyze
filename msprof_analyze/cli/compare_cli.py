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
import ast
import click

from msprof_analyze.prof_common.path_manager import PathManager
from msprof_analyze.prof_common.constant import Constant
from msprof_analyze.prof_common.analyze_dict import AnalyzeDict
from msprof_analyze.compare_tools.compare_backend.comparison_generator import ComparisonGenerator
from msprof_analyze.advisor.utils.utils import debug_option
from msprof_analyze.cli.unified_cli import UnifiedCommand, help_callback


@click.command(
    cls=UnifiedCommand,
    context_settings=Constant.CONTEXT_SETTINGS,
    name="compare",
    help="Compare the performance differences between GPUs and NPUs.",
    short_help="Compare the performance differences between GPUs and NPUs, use 'msprof-analyze compare --help' for details.",
    output='<output_path>/performance_comparison_result_*.xlsx',
    examples="msprof-analyze compare -d ./ascend_pt -bp ./gpu_trace.json -o ./compare_output",
)
@click.option("-H", is_flag=True, expose_value=False, hidden=True, callback=help_callback)
@click.option(
    '--profiling_path',
    '-d',
    'comparison_profiling_path',
    type=click.Path(exists=True, resolve_path=True),
    required=True,
    metavar='<DIR>',
    callback=PathManager.expanduser_for_cli,
    help='Path of the profiling data',
)
@click.option(
    '--benchmark_profiling_path',
    '-bp',
    'base_profiling_path',
    type=click.Path(exists=True, resolve_path=True),
    required=True,
    metavar='<DIR>',
    callback=PathManager.expanduser_for_cli,
    help="Path of the benchmark data",
)
@click.option('--enable_profiling_compare', is_flag=True, help="Enable overall performance comparison")
@click.option('--enable_operator_compare', is_flag=True, help="Enable operator performance comparison")
@click.option('--enable_memory_compare', is_flag=True, help="Enable operator memory comparison")
@click.option('--enable_communication_compare', is_flag=True, help="Enable communication performance comparison")
@click.option('--enable_api_compare', is_flag=True, help="Enable API performance comparison")
@click.option('--enable_kernel_compare', is_flag=True, help="Enable kernel performance comparison")
@click.option('--disable_details', is_flag=True, help="Hide detailed comparison")
@click.option('--disable_module', is_flag=True, help="Hide module comparison")
@click.option(
    '--output_path',
    '-o',
    'output_path',
    type=click.Path(file_okay=False, writable=True, executable=True),
    callback=PathManager.expanduser_for_cli,
    help="Path of comparison result. [default: pwd]",
)
@click.option('--max_kernel_num', 'max_kernel_num', type=int, help="The number of kernels per torch op is limited")
@click.option(
    '--op_name_map',
    type=ast.literal_eval,
    default='{}',
    help="The mapping of operator names equivalent to GPUs and NPUs in the form of dictionaries",
    required=False,
)
@click.option('--use_input_shape', is_flag=True, help="Enable precise matching of operators")
@click.option('--gpu_flow_cat', type=str, default='', help="Identifier of the GPU connection")
@click.option('--base_step', type=str, default='', help="Comparison step for performance data to be compared")
@click.option('--comparison_step', type=str, default='', help="Comparison step for benchmark performance data")
@click.option(
    '--force', is_flag=True, help="Indicates whether to skip verification of the owner, size, and permissions."
)
@click.option('--use_kernel_type', is_flag=True, help="Indicates whether kernel compare use op_statistic.csv")
@debug_option
def compare_cli(**kwargs) -> None:
    args = AnalyzeDict(kwargs)
    ComparisonGenerator(args).run()
