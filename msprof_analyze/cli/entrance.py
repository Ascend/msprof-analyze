#!/usr/bin/python
# -*- coding: utf-8 -*-
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
import sys

from msprof_analyze.cli.analyze_cli import analyze_cli
from msprof_analyze.cli.complete_cli import auto_complete_cli
from msprof_analyze.cli.compare_cli import compare_cli
from msprof_analyze.cli.cluster_cli import cluster_cli
from msprof_analyze.cli.unified_cli import help_callback
from msprof_analyze.cli.version import build_version_text
from msprof_analyze.prof_common.constant import Constant
from msprof_analyze.prof_common.logger import get_logger
from msprof_analyze.prof_common.path_manager import is_root

logger = get_logger()

COMMAND_PRIORITY = {"cluster": 1, "compare": 2, "advisor": 3, "auto-completion": 4}


class SpecialHelpOrder(click.Group):
    def list_commands(self, ctx):
        """
        reorder the list of commands when listing the help
        """
        commands = super().list_commands(ctx)
        priority_items = []
        for command in commands:
            priority_items.append((COMMAND_PRIORITY.get(command, float('inf')), command))
        return [item[1] for item in sorted(priority_items)]

    def parse_args(self, ctx, args):
        # 检查是否有已知的子命令
        has_subcommand = any(arg in self.list_commands(ctx) for arg in args if not arg.startswith('-'))
        # 检查包含help参数
        has_help = any(arg in ['-H', '-h', '--help'] for arg in args)
        # 检查包含version参数
        has_version = any(arg in ['-V', '-v', '--version'] for arg in args)
        # 如果没有子命令但有参数，自动添加 cluster 子命令
        if not has_subcommand and args and not has_help and not has_version:
            args = ['cluster'] + args
        # 如果没有子命令也没有参数，显示所有help信息
        elif not has_subcommand and not args:
            args = ['--help']
        return super().parse_args(ctx, args)


class CliLogo:
    """MindStudio CLI logo printer."""

    RESET = "\033[0m"
    DIM_GRAY = "\033[38;5;240m"
    BOLD_WHITE = "\033[1;97m"
    HIGHLIGHT = "\033[48;5;21;38;5;46m"  # green on blue

    def _should_use_color_logo(self) -> bool:
        """Check if we should use colored logo with ANSI escape codes."""
        if not sys.stderr.isatty():
            return False
        term = os.environ.get("TERM")
        return term is not None and term not in ("dumb", "unknown")

    def _render_simple(self) -> str:
        """Return the plain ASCII logo."""
        return (
            "================================================================="
            "\n"
            "                   >>>>>   MindStudio   <<<<<"
            "\n"
            "    THE END-TO-END TOOLCHAIN TO UNLEASH HUAWEI ASCEND COMPUTE"
            "\n"
            "================================================================="
            "\n\n"
        )

    def _render_colored(self) -> str:
        """Return the colored logo with ANSI escape codes."""
        return (
            f"{self.DIM_GRAY}================================================================="
            f"{self.RESET}\n"
            f"{self.BOLD_WHITE}                   >>>>>  "
            f"{self.HIGHLIGHT} MindStudio {self.RESET}{self.BOLD_WHITE}  <<<<<{self.RESET}\n"
            f"{self.BOLD_WHITE}    THE END-TO-END TOOLCHAIN TO UNLEASH HUAWEI ASCEND COMPUTE"
            f"{self.RESET}\n"
            f"{self.DIM_GRAY}================================================================="
            f"{self.RESET}\n\n"
        )

    def print_logo(self) -> None:
        """Print the MindStudio logo to stderr."""
        content = self._render_colored() if self._should_use_color_logo() else self._render_simple()
        sys.stderr.write(content)
        sys.stderr.flush()


def _has_help_option(ctx) -> bool:
    """检查命令行参数中是否包含帮助选项"""
    # 获取原始命令行参数
    args = sys.argv[1:] if len(sys.argv) > 1 else []

    # 帮助选项列表
    help_options = ['-H', '-h', '--help']

    # 检查是否有帮助选项
    for arg in args:
        if arg in help_options:
            return True

    # 也检查 protected_args（click 内部存储）
    if hasattr(ctx, 'protected_args'):
        for arg in ctx.protected_args:
            if arg in help_options:
                return True

    return False


def _version_callback(ctx: click.Context, param: click.Parameter, value: bool):
    if value and not ctx.resilient_parsing:
        logo = CliLogo()
        logo.print_logo()
        sys.stderr.write(build_version_text())
        sys.stderr.flush()
        ctx.exit()


@click.group(context_settings=Constant.CONTEXT_SETTINGS, cls=SpecialHelpOrder, invoke_without_command=True)
@click.option(
    '--version', '-V', is_flag=True, expose_value=False, callback=_version_callback, help="Show version and exit."
)
@click.option('-v', is_flag=True, expose_value=False, hidden=True, callback=_version_callback)
@click.option('-H', is_flag=True, expose_value=False, hidden=True, callback=help_callback)
@click.pass_context
def msprof_analyze_cli(ctx, **kwargs):
    if not _has_help_option(ctx):
        logo = CliLogo()
        logo.print_logo()

    if is_root():
        logger.warning(
            "Security Warning: Do not run this tool as root. "
            "Running with elevated privileges may compromise system security. "
            "Use a regular user account."
        )


msprof_analyze_cli.add_command(analyze_cli, name="advisor")
msprof_analyze_cli.add_command(compare_cli, name="compare")
msprof_analyze_cli.add_command(cluster_cli, name="cluster")
msprof_analyze_cli.add_command(auto_complete_cli, name="auto-completion")
