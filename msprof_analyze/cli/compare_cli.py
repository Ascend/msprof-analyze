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
import ast
import click

from msprof_analyze.prof_common.path_manager import PathManager
from msprof_analyze.prof_common.constant import Constant
from msprof_analyze.prof_common.analyze_dict import AnalyzeDict
from msprof_analyze.compare_tools.compare_backend.comparison_generator import ComparisonGenerator
from msprof_analyze.advisor.utils.utils import debug_option


@click.command(context_settings=Constant.CONTEXT_SETTINGS, name="compare",
               short_help='Compare the performance differences between GPUs and NPUs.')
@click.option('--profiling_path', '-d', 'comparison_profiling_path',
              type=click.Path(exists=True, resolve_path=True), required=True,
              callback=PathManager.expanduser_for_cli, help='Path of the profiling data')
@click.option('--benchmark_profiling_path', '-bp', 'base_profiling_path',
              type=click.Path(exists=True, resolve_path=True), required=True,
              callback=PathManager.expanduser_for_cli, help="Path of the benchmark data")
@click.option('--enable_profiling_compare', is_flag=True, help="Enable overall performance comparison")
@click.option('--enable_operator_compare', is_flag=True, help="Enable operator performance comparison")
@click.option('--enable_memory_compare', is_flag=True, help="Enable operator memory comparison")
@click.option('--enable_communication_compare', is_flag=True, help="Enable communication performance comparison")
@click.option('--enable_api_compare', is_flag=True, help="Enable API performance comparison")
@click.option('--enable_kernel_compare', is_flag=True, help="Enable kernel performance comparison")
@click.option('--disable_details', is_flag=True, help="Hide detailed comparison")
@click.option('--disable_module', is_flag=True, help="Hide module comparison")
@click.option('--output_path', '-o', 'output_path',
              type=click.Path(file_okay=False, writable=True, executable=True),
              callback=PathManager.expanduser_for_cli,
              help="Path of comparison result")
@click.option('--max_kernel_num', 'max_kernel_num', type=int, help="The number of kernels per torch op is limited")
@click.option('--op_name_map', type=ast.literal_eval, default='{}',
              help="The mapping of operator names equivalent to GPUs and NPUs in the form of dictionaries",
              required=False)
@click.option('--use_input_shape', is_flag=True, help="Enable precise matching of operators")
@click.option('--gpu_flow_cat', type=str, default='', help="Identifier of the GPU connection")
@click.option('--base_step', type=str, default='', help="Comparison step for performance data to be compared")
@click.option('--comparison_step', type=str, default='', help="Comparison step for benchmark performance data")
@click.option('--force', is_flag=True,
              help="Indicates whether to skip verification of the owner, size, and permissions.")
@click.option('--use_kernel_type', is_flag=True, help="Indicates whether kernel compare use op_statistic.csv")
@debug_option
def compare_cli(**kwargs) -> None:
    args = AnalyzeDict(kwargs)
    ComparisonGenerator(args).run()
