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
