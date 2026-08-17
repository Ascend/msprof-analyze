# Copyright (c) 2026, Huawei Technologies Co., Ltd.
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

# 不属于业务参数、不进入 Required/Optional arguments 段落的公共参数名。
_EXCLUDE_PARAM_NAMES = ('help', 'version')


def help_callback(ctx: click.Context, param: click.Parameter, value: bool):
    if value and not ctx.resilient_parsing:
        click.echo(ctx.get_help(), color=ctx.color)
        ctx.exit()


class UnifiedChoice(click.Choice):
    """以 {a,b,c} 花括号展示取值集合的 Choice 类型（替代默认的 [a|b|c]）。"""

    def get_metavar(self, param, ctx=None):
        return '{' + ','.join(str(choice) for choice in self.choices) + '}'


class UnifiedCommand(click.Command):
    def __init__(self, *args, examples=None, output=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._description = self.help or self.short_help
        self._examples = examples or ''
        self._output = output

    def _business_params(self, ctx):
        return [p for p in self.get_params(ctx) if isinstance(p, click.Option) and p.name not in _EXCLUDE_PARAM_NAMES]

    @staticmethod
    def _long_opt(param):
        return next((o for o in param.opts if o.startswith('--')), None)

    @staticmethod
    def _short_opt(param):
        return next((o for o in param.opts if not o.startswith('--')), None)

    @staticmethod
    def _semantic_metavar(param):
        if getattr(param, 'metavar', None):
            return param.metavar

        ptype = param.type
        if isinstance(ptype, click.Choice):
            return None

        if isinstance(ptype, click.Path):
            if ptype.dir_okay and not ptype.file_okay:
                return '<DIR>'
            if ptype.file_okay and not ptype.dir_okay:
                return '<FILE>'
            return '<PATH>'

        type_name = getattr(ptype, 'name', '')
        if type_name == 'integer':
            return '<N>'
        if type_name == 'float':
            return '<FLOAT>'
        return '<NAME>'

    @staticmethod
    def _default_suffix(param):
        if param.required:
            return ""
        if param.is_flag:
            return " [default: on]" if param.default else " [default: off]"
        if param.default is None:
            return ""
        if isinstance(param.default, (str, int, float)):
            if param.default == "":
                return ""
            return f' [default: {param.default}]'
        return ""

    @classmethod
    def _make_metavar(cls, param, ctx):
        semantic = cls._semantic_metavar(param)
        if semantic is not None:
            return semantic
        try:
            return param.make_metavar(ctx)
        except TypeError:
            return param.make_metavar()

    def _param_left(self, ctx, param):
        short = self._short_opt(param)
        long = self._long_opt(param)
        left = f"{short}, {long}" if short else f"    {long}"
        if not param.is_flag:
            left = f"{left} {self._make_metavar(param, ctx)}"
        return left

    def _param_right(self, param):
        text = param.help or ''
        suffix = self._default_suffix(param)
        if suffix:
            text = f'{text}{suffix}'
        return text

    def format_usage(self, ctx, formatter):
        pieces = []
        for param in self._business_params(ctx):
            if param.required:
                pieces.append(f"{self._short_opt(param)} {self._make_metavar(param, ctx)}")

        pieces.append('[options]')
        formatter.write(f'Usage:\n  {ctx.command_path} {" ".join(pieces)}\n')

    def format_options(self, ctx, formatter):
        params = self._business_params(ctx)
        visible_params = [p for p in params if not p.hidden]
        required = [p for p in visible_params if p.required]
        optional = [p for p in visible_params if not p.required]

        if required:
            rows = [(self._param_left(ctx, p), self._param_right(p)) for p in required]
            with formatter.section('Required arguments'):
                formatter.write_dl(rows)

        if optional:
            rows = [(self._param_left(ctx, p), self._param_right(p)) for p in optional]
            rows.append(('-h, --help', 'Show this message and exit.'))
            with formatter.section('Optional arguments'):
                formatter.write_dl(rows)

    def format_help(self, ctx, formatter):
        if self._description:
            with formatter.section('Description'):
                formatter.write_text(self._description)
        formatter.write_paragraph()
        self.format_usage(ctx, formatter)
        self.format_options(ctx, formatter)
        if self._examples:
            with formatter.section('Examples'):
                indent = " " * formatter.current_indent
                raw = self._examples.lstrip("\n")
                for line in raw.splitlines():
                    formatter.write(f"{indent}{line}\n")
        if self._output:
            with formatter.section('Output'):
                formatter.write_text(self._output)
