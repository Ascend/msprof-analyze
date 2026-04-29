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
from msprof_analyze.advisor.version import print_version_callback, cli_version
from msprof_analyze.prof_common.logger import get_logger
from msprof_analyze.prof_common.path_manager import is_root

logger = get_logger()
CONTEXT_SETTINGS = dict(help_option_names=['-H', '-h', '--help'],
                        max_content_width=160)

COMMAND_PRIORITY = {
    "advisor": 1,
    "compare": 2,
    "cluster": 3,
    "auto-completion": 4
}


class SpecialHelpOrder(click.Group):

    def __init__(self, *args, **kwargs):
        super(SpecialHelpOrder, self).__init__(*args, **kwargs)

    def list_commands_for_help(self, ctx):
        """
        reorder the list of commands when listing the help
        """
        commands = super(SpecialHelpOrder, self).list_commands(ctx)
        priority_items = []
        for command in commands:
            priority_items.append((COMMAND_PRIORITY.get(command, float('INF')), command))
        return [item[1] for item in sorted(priority_items)]

    def get_help(self, ctx):
        self.list_commands = self.list_commands_for_help
        return super(SpecialHelpOrder, self).get_help(ctx)

    def parse_args(self, ctx, args):
        # 检查是否有已知的子命令
        has_subcommand = any(arg in self.list_commands(ctx) for arg in args if not arg.startswith('-'))

        # 如果没有子命令但有参数，自动添加 cluster 子命令
        if not has_subcommand and args:
            args = ['cluster'] + args
        # 如果没有子命令也没有参数，执行--help
        elif not has_subcommand and not args:
            args = ['cluster', '--help']

        return super(SpecialHelpOrder, self).parse_args(ctx, args)


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
            "=================================================================" "\n"
            "                   >>>>>   MindStudio   <<<<<" "\n"
            "    THE END-TO-END TOOLCHAIN TO UNLEASH HUAWEI ASCEND COMPUTE" "\n"
            "=================================================================" "\n\n"
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


@click.group(context_settings=CONTEXT_SETTINGS, cls=SpecialHelpOrder, invoke_without_command=True)
@click.option('--version', '-V', '-v', is_flag=True,
              callback=print_version_callback, expose_value=False,
              is_eager=True, help=cli_version())
@click.pass_context
def msprof_analyze_cli(ctx, **kwargs):
    """如果没有子命令，默认执行 cluster"""
    # 检查是否包含帮助选项
    if not _has_help_option(ctx):
        logo = CliLogo()
        logo.print_logo()

    if is_root():
        logger.warning(
            "Security Warning: Do not run this tool as root. "
            "Running with elevated privileges may compromise system security. "
            "Use a regular user account."
        )
    if ctx.invoked_subcommand is None:
        ctx.invoke(cluster_cli)

msprof_analyze_cli.add_command(analyze_cli, name="advisor")
msprof_analyze_cli.add_command(compare_cli, name="compare")
msprof_analyze_cli.add_command(cluster_cli, name="cluster")
msprof_analyze_cli.add_command(auto_complete_cli, name="auto-completion")

