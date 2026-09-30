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

from msprof_analyze.prof_common.constant import Constant
from msprof_analyze.cli.unified_cli import UnifiedCommand, help_callback


@click.command(
    context_settings=Constant.CONTEXT_SETTINGS,
    cls=UnifiedCommand,
    short_help='Auto complete ma-advisor command in terminal, support "bash(default)/zsh/fish".',
    examples='#print bash auto complete command to terminal\nmsprof-analyze auto-completion Bash',
)
@click.option("-H", is_flag=True, expose_value=False, hidden=True, callback=help_callback)
@click.argument('shell_type', nargs=1, default="Bash", type=click.Choice(["Bash", "Zsh", "Fish"], case_sensitive=False))
def auto_complete_cli(shell_type):
    """Auto complete ma-advisor command in terminal."""
    click.echo("Tips: please paste following shell command to your terminal to activate auto completion.\n")
    if shell_type.lower() == "bash":
        bash_str = 'eval "$(_MSPROF_ANALYZE_COMPLETE=bash_source msprof-analyze)"'
    elif shell_type.lower() == "zsh":
        bash_str = 'eval "$(_MSPROF_ANALYZE_COMPLETE=zsh_source msprof-analyze)"'
    elif shell_type.lower() == "fish":
        bash_str = 'eval (env _MSPROF_ANALYZE_COMPLETE=fish_source msprof-analyze)'
    else:
        click.echo(f'Unsupported shell type {shell_type}.')
        return
    click.echo(f'{bash_str}\n')
