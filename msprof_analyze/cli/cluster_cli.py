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
import click
import os

from msprof_analyze.prof_common.constant import Constant
from msprof_analyze.cluster_analyse.cluster_analysis import ALL_FEATURE_LIST, Interface
from msprof_analyze.prof_common.path_manager import PathManager
from msprof_analyze.prof_common.logger import set_agent_mode
from msprof_analyze.prof_common.json_output import cli_json_output
from msprof_analyze.cli.unified_cli import UnifiedCommand, UnifiedChoice, help_callback

context_settings = dict(Constant.CONTEXT_SETTINGS)
context_settings['ignore_unknown_options'] = True


@click.command(
    cls=UnifiedCommand,
    context_settings=context_settings,
    name="cluster",
    help="Analyze cluster data to locate performance bottleneck.",
    short_help="Analyze cluster data to locate performance bottleneck, use 'msprof-analyze cluster --help' for details. (default command)",
    output='<output_path>/cluster_analysis_output',
    examples="#'cluster' can be omitted (default command)\nmsprof-analyze -d ./profiling_data\nmsprof-analyze cluster -d ./profiling_data",
)
@click.option("-H", is_flag=True, expose_value=False, hidden=True, callback=help_callback)
@click.option(
    '--profiling_path',
    '-d',
    type=click.Path(exists=True, file_okay=False, resolve_path=True),
    required=True,
    callback=PathManager.expanduser_for_cli,
    help='Path of the profiling data',
)
@click.option(
    '--mode',
    '-m',
    type=UnifiedChoice(ALL_FEATURE_LIST),
    default='all',
    help='Analysis mode, select specific feature type for cluster analysis',
)
@click.option(
    '--output_path',
    '-o',
    type=click.Path(file_okay=False, writable=True, executable=True),
    callback=PathManager.expanduser_for_cli,
    help='Path of cluster analysis output [default: same as input directory]',
)
@click.option(
    '--force', is_flag=True, help="Indicates whether to skip verification of the owner, size, and permissions."
)
@click.option("--parallel_mode", type=str, help="Context mode", default="concurrent")
@click.option("--export_type", help="Recipe export type", type=UnifiedChoice(["db", "notebook", "text"]), default="db")
@click.option("--rank_list", type=str, metavar='<ID>[,<ID>...]', help="Rank id list", default='all')
@click.option("--step_id", type=int, help="Step id", default=Constant.VOID_STEP)
@click.option(
    '--agent', is_flag=True, help='Agent mode: save logs to temp file, only output structured JSON to terminal'
)
@click.argument('args', nargs=-1)
@cli_json_output
def cluster_cli(**kwargs) -> None:
    if kwargs.get('agent'):
        os.environ["AGENT_MODE"] = "agent"
        set_agent_mode()
    Interface(kwargs).run()
