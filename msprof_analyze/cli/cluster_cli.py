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

from msprof_analyze.prof_common.constant import Constant
from msprof_analyze.cluster_analyse.cluster_analysis import ALL_FEATURE_LIST, Interface
from msprof_analyze.prof_common.path_manager import PathManager
from msprof_analyze.advisor.version import print_version_callback, cli_version
from msprof_analyze.prof_common.logger import set_agent_mode
from msprof_analyze.prof_common.json_output import cli_json_output

context_settings = dict(Constant.CONTEXT_SETTINGS)
context_settings['ignore_unknown_options'] = True


@click.command(context_settings=context_settings, name="cluster",
               short_help='Analyze cluster data to locate performance bottleneck')
@click.option('--profiling_path', '-d', type=click.Path(exists=True, file_okay=False, resolve_path=True),
              required=True, callback=PathManager.expanduser_for_cli, help='path of the profiling data')
@click.option('--mode', '-m', type=click.Choice(ALL_FEATURE_LIST), default='all')
@click.option('--output_path', '-o',
              type=click.Path(file_okay=False, writable=True, executable=True),
              callback=PathManager.expanduser_for_cli, help='Path of cluster analysis output')
@click.option('--force', is_flag=True,
              help="Indicates whether to skip verification of the owner, size, and permissions.")
@click.option("--parallel_mode", type=str, help="context mode", default="concurrent")
@click.option("--export_type", help="recipe export type", type=click.Choice(["db", "notebook", "text"]), default="db")
@click.option("--rank_list", type=str, help="Rank id list", default='all')
@click.option("--step_id", type=int, help="Step id", default=Constant.VOID_STEP)
@click.option('--version', '-V', '-v', is_flag=True,
              callback=print_version_callback, expose_value=False,
              is_eager=True, help=cli_version())
@click.option('--agent', is_flag=True, help='Agent mode: save logs to temp file, only output structured JSON to terminal')
@click.argument('args', nargs=-1)
@cli_json_output
def cluster_cli(**kwargs) -> None:
    if kwargs.get('agent'):
        os.environ["AGENT_MODE"] = "agent"
        set_agent_mode()
    Interface(kwargs).run()

