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

import logging
import click

from msprof_analyze.prof_common.path_manager import PathManager
from msprof_analyze.advisor.analyzer.analyzer_controller import AnalyzerController
from msprof_analyze.advisor.utils.tools import CONTEXT_SETTINGS, ClickAliasedGroup
from msprof_analyze.prof_common.constant import Constant
from msprof_analyze.advisor.common.enum_params_parser import EnumParamsParser
from msprof_analyze.advisor.utils.utils import debug_option
from msprof_analyze.advisor.interface.interface import Interface

logger = logging.getLogger()


@click.group(name="analyze", cls=ClickAliasedGroup)
def analyze_cli(**kwargs):
    """Analyze profiling datasets and give performance optimization suggestion."""
    pass


@analyze_cli.command(context_settings=CONTEXT_SETTINGS,
                     name="all",
                     short_help='Analyze timeline fusion operators, operators and graph,\
                                 operators dispatching and cluster.')
@click.option('--profiling_path', '-d', 'profiling_path',
              type=click.Path(exists=True, file_okay=False, resolve_path=True), required=True,
              callback=PathManager.expanduser_for_cli, help='Directory of profiling data')
@click.option('--benchmark_profiling_path', '-bp', 'benchmark_profiling_path',
              type=click.Path(exists=True, file_okay=False, resolve_path=True),
              callback=PathManager.expanduser_for_cli,
              help='Directory of benchmark profiling data, used for compare performance')
@click.option('--output_path', '-o', 'output_path',
              type=click.Path(file_okay=False, writable=True, executable=True),
              callback=PathManager.expanduser_for_cli,
              help='Path of analysis output')
@click.option('--cann_version', '-cv', 'cann_version',
              type=click.Choice(EnumParamsParser().get_options(Constant.CANN_VERSION), case_sensitive=False),
              default=EnumParamsParser().get_default(Constant.CANN_VERSION),
              help='The CANN software version, which can be viewed by executing the following command: '
                   '"cat /usr/local/Ascend/ascend-toolkit/latest/aarch64-linux/ascend_toolkit_install.info"')
@click.option("-pt",
              "--profiling_type",
              metavar="",
              required=False,
              type=click.Choice(EnumParamsParser().get_options(Constant.PROFILING_TYPE_UNDER_LINE)),
              help="enter the profiling type, selectable range pytorch, mindspore, mslite ,msprof")
@click.option("--force",
              is_flag=True,
              help="Indicates whether to skip verification of the owner, size, and permissions.")
@click.option("-l",
              "--language",
              type=click.Choice(["cn", "en"]),
              required=False,
              default="cn",
              help="Language of the profiling advisor.")
@debug_option
def analyze_all(**kwargs) -> None:
    try:
        AnalyzerController().do_analysis(Interface.all_dimension, **kwargs)
    except Exception as e:
        logger.error(e)


@analyze_cli.command(context_settings=CONTEXT_SETTINGS,
                     name="schedule",
                     short_help='Analyze operators dispatching and timeline fusion operators.')
@click.option('--profiling_path', '-d', 'profiling_path', type=click.Path(), required=True,
              callback=PathManager.expanduser_for_cli, help='Directory of profiling data')
@click.option('--output_path', '-o', 'output_path', type=click.Path(), callback=PathManager.expanduser_for_cli,
              help='Path of analysis output')
@click.option('--cann_version', '-cv', 'cann_version',
              type=click.Choice(EnumParamsParser().get_options(Constant.CANN_VERSION), case_sensitive=False),
              default=EnumParamsParser().get_default(Constant.CANN_VERSION),
              help='The CANN software version, which can be viewed by executing the following command: '
                   '"cat /usr/local/Ascend/ascend-toolkit/latest/aarch64-linux/ascend_toolkit_install.info"')
@click.option('--torch_version', '-tv', 'torch_version',
              type=click.Choice(EnumParamsParser().get_options(Constant.TORCH_VERSION), case_sensitive=False),
              default=EnumParamsParser().get_default(Constant.TORCH_VERSION),
              help='The runtime torch version, which can be detected by exec command "pip show torch"')
@click.option("-pt",
              "--profiling_type",
              metavar="",
              required=False,
              type=click.Choice(EnumParamsParser().get_options(Constant.PROFILING_TYPE_UNDER_LINE)),
              help="enter the profiling type, selectable range ascend_pytorch_profiler, mslite ,msprof")
@click.option("--force",
              is_flag=True,
              help="Indicates whether to skip verification of the owner, size, and permissions.")
@click.option("-l",
              "--language",
              type=click.Choice(["cn", "en"]),
              required=False,
              default="cn",
              help="Language of the profiling advisor.")
@debug_option
def analyze_schedule(**kwargs) -> None:
    try:
        AnalyzerController().do_analysis([Interface.SCHEDULE], **kwargs)
    except Exception as e:
        logger.error(e)


@analyze_cli.command(context_settings=CONTEXT_SETTINGS,
                     name="computation",
                     short_help='Analyze operators and graph.')
@click.option('--profiling_path', '-d', 'profiling_path', type=click.Path(), required=True,
              callback=PathManager.expanduser_for_cli, help='Directory of profiling data')
@click.option('--output_path', '-o', 'output_path', type=click.Path(), callback=PathManager.expanduser_for_cli,
              help='Path of analysis output')
@click.option('--cann_version', '-cv', 'cann_version',
              type=click.Choice(EnumParamsParser().get_options(Constant.CANN_VERSION), case_sensitive=False),
              default=EnumParamsParser().get_default(Constant.CANN_VERSION),
              help='The CANN software version, which can be viewed by executing the following command: '
                   '"cat /usr/local/Ascend/ascend-toolkit/latest/aarch64-linux/ascend_toolkit_install.info"')
@click.option('--torch_version', '-tv', 'torch_version',
              type=click.Choice(EnumParamsParser().get_options(Constant.TORCH_VERSION), case_sensitive=False),
              default=EnumParamsParser().get_default(Constant.TORCH_VERSION),
              help='The runtime torch version, which can be detected by exec command "pip show torch"')
@click.option("-pt",
              "--profiling_type",
              metavar="",
              required=False,
              type=click.Choice(EnumParamsParser().get_options(Constant.PROFILING_TYPE_UNDER_LINE)),
              help="enter the profiling type, selectable range ascend_pytorch_profiler, mslite ,msprof")
@click.option("--force",
              is_flag=True,
              help="Indicates whether to skip verification of the owner, size, and permissions.")
@click.option("-l",
              "--language",
              type=click.Choice(["cn", "en"]),
              required=False,
              default="cn",
              help="Language of the profiling advisor.")
@debug_option
def analyze_computation(**kwargs) -> None:
    try:
        AnalyzerController().do_analysis([Interface.COMPUTATION], **kwargs)
    except Exception as e:
        logger.error(e)
