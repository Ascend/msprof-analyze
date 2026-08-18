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

import click
import os

from msprof_analyze.prof_common.path_manager import PathManager
from msprof_analyze.advisor.analyzer.analyzer_controller import AnalyzerController
from msprof_analyze.prof_common.constant import Constant
from msprof_analyze.advisor.common.enum_params_parser import EnumParamsParser
from msprof_analyze.advisor.utils.utils import debug_option
from msprof_analyze.advisor.interface.interface import Interface
from msprof_analyze.prof_common.logger import get_logger, set_agent_mode
from msprof_analyze.prof_common.json_output import cli_json_output
from msprof_analyze.cli.unified_cli import UnifiedCommand, UnifiedChoice, help_callback

logger = get_logger()


def common_analyze_options(func):
    func = click.option("-H", is_flag=True, expose_value=False, hidden=True, callback=help_callback)(func)
    func = click.option(
        '--profiling_path',
        '-d',
        'profiling_path',
        type=click.Path(exists=True, file_okay=False, resolve_path=True),
        required=True,
        callback=PathManager.expanduser_for_cli,
        help='Directory of profiling data',
    )(func)
    func = click.option(
        '--output_path',
        '-o',
        'output_path',
        type=click.Path(file_okay=False, writable=True, executable=True),
        callback=PathManager.expanduser_for_cli,
        help='Path of analysis output [default: pwd]',
    )(func)
    func = click.option(
        '--cann_version',
        '-cv',
        'cann_version',
        type=UnifiedChoice(EnumParamsParser().get_options(Constant.CANN_VERSION), case_sensitive=False),
        default=EnumParamsParser().get_default(Constant.CANN_VERSION),
        help='The CANN software version, which can be viewed by executing the following command: '
        '"cat /usr/local/Ascend/ascend-toolkit/latest/aarch64-linux/ascend_toolkit_install.info"',
    )(func)
    func = click.option(
        '--torch_version',
        '-tv',
        'torch_version',
        type=UnifiedChoice(EnumParamsParser().get_options(Constant.TORCH_VERSION), case_sensitive=False),
        default=EnumParamsParser().get_default(Constant.TORCH_VERSION),
        help='The runtime torch version, which can be detected by exec command "pip show torch"',
    )(func)
    func = click.option(
        "-pt",
        "--profiling_type",
        required=False,
        type=UnifiedChoice(EnumParamsParser().get_options(Constant.PROFILING_TYPE_UNDER_LINE)),
        help="Enter the profiling type, selectable range pytorch, mindspore, mslite ,msprof",
        default=EnumParamsParser().get_default(Constant.PROFILING_TYPE_UNDER_LINE),
    )(func)
    func = click.option(
        "--force", is_flag=True, help="Indicates whether to skip verification of the owner, size, and permissions."
    )(func)
    func = click.option(
        "-l",
        "--language",
        type=UnifiedChoice(["cn", "en"]),
        required=False,
        default="cn",
        help="Language of the profiling advisor.",
    )(func)
    func = click.option(
        '--agent', is_flag=True, help='Agent mode: save logs to temp file, only output structured JSON to terminal'
    )(func)
    func = debug_option(func)
    func = cli_json_output(func)
    return func


def _handle_agent_mode(kwargs):
    if kwargs.get('agent'):
        os.environ["AGENT_MODE"] = "agent"
        set_agent_mode()


@click.group(
    name="analyze",
    context_settings=Constant.CONTEXT_SETTINGS,
    help="Analyze timeline fusion operators, operators and graph, operators dispatching and cluster.",
    short_help="Analyze timeline fusion operators, operators and graph, operators dispatching and cluster, use 'msprof-analyze advisor --help' for details.",
)
@click.option("-H", is_flag=True, expose_value=False, hidden=True, callback=help_callback)
def analyze_cli(**kwargs):
    pass


_output = "Terminal, <output_path>/mstt_advisor_<timestamp>.html and <output_path>/log/mstt_advisor_<timestamp>.xlsx"


@analyze_cli.command(
    context_settings=Constant.CONTEXT_SETTINGS,
    cls=UnifiedCommand,
    name="all",
    help='Analyze timeline fusion operators, operators and graph, operators dispatching and cluster.',
    short_help="Analyze timeline fusion operators, operators and graph, operators dispatching and cluster, use 'msprof-analyze advisor all --help' for details.",
    output=_output,
    examples='msprof-analyze advisor all -d /path/to/profiling_data/ -o /path/to/advisor_output',
)
@click.option(
    '--benchmark_profiling_path',
    '-bp',
    'benchmark_profiling_path',
    type=click.Path(exists=True, file_okay=False, resolve_path=True),
    callback=PathManager.expanduser_for_cli,
    help='Directory of benchmark profiling data, used for compare performance',
)
@common_analyze_options
def analyze_all(**kwargs) -> None:
    _handle_agent_mode(kwargs)
    try:
        AnalyzerController().do_analysis(Interface.all_dimension, **kwargs)
    except Exception as e:
        logger.error(e)


@analyze_cli.command(
    context_settings=Constant.CONTEXT_SETTINGS,
    cls=UnifiedCommand,
    name="schedule",
    help='Analyze operators dispatching and timeline fusion operators.',
    short_help="Analyze operators dispatching and timeline fusion operators, use 'msprof-analyze advisor schedule --help' for details.",
    output=_output,
    examples='msprof-analyze advisor schedule -d /path/to/profiling_data/ -o /path/to/advisor_output',
)
@common_analyze_options
def analyze_schedule(**kwargs) -> None:
    _handle_agent_mode(kwargs)
    try:
        AnalyzerController().do_analysis([Interface.SCHEDULE], **kwargs)
    except Exception as e:
        logger.error(e)


@analyze_cli.command(
    context_settings=Constant.CONTEXT_SETTINGS,
    cls=UnifiedCommand,
    name="computation",
    help='Analyze operators and graph.',
    short_help="Analyze operators and graph, use 'msprof-analyze advisor computation --help' for details.",
    output=_output,
    examples='msprof-analyze advisor computation -d /path/to/profiling_data/ -o /path/to/advisor_output',
)
@common_analyze_options
def analyze_computation(**kwargs) -> None:
    _handle_agent_mode(kwargs)
    try:
        AnalyzerController().do_analysis([Interface.COMPUTATION], **kwargs)
    except Exception as e:
        logger.error(e)
