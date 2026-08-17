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

import unittest
from unittest.mock import MagicMock

import click
from click.formatting import HelpFormatter
from click.testing import CliRunner

from msprof_analyze.cli.unified_cli import UnifiedChoice, UnifiedCommand


class TestUnifiedChoice(unittest.TestCase):
    def test_get_metavar_should_return_curly_brace_format_when_choices_exist(self):
        choice = UnifiedChoice(["a", "b", "c"])
        result = choice.get_metavar(None)
        self.assertEqual(result, "{a,b,c}")

    def test_get_metavar_should_return_empty_braces_when_no_choices(self):
        choice = UnifiedChoice([])
        result = choice.get_metavar(None)
        self.assertEqual(result, "{}")


class TestUnifiedCommandInit(unittest.TestCase):
    def test_init_should_set_description_from_help_when_help_provided(self):
        cmd = UnifiedCommand(name="test", help="Test description")
        self.assertEqual(cmd._description, "Test description")

    def test_init_should_set_description_from_short_help_when_help_not_provided(self):
        cmd = UnifiedCommand(name="test", short_help="Short description")
        self.assertEqual(cmd._description, "Short description")

    def test_init_should_set_examples_when_examples_provided(self):
        cmd = UnifiedCommand(name="test", examples="example text")
        self.assertEqual(cmd._examples, "example text")

    def test_init_should_set_empty_examples_when_examples_not_provided(self):
        cmd = UnifiedCommand(name="test")
        self.assertEqual(cmd._examples, "")

    def test_init_should_set_output_when_output_provided(self):
        cmd = UnifiedCommand(name="test", output="output text")
        self.assertEqual(cmd._output, "output text")

    def test_init_should_set_none_output_when_output_not_provided(self):
        cmd = UnifiedCommand(name="test")
        self.assertIsNone(cmd._output)


class TestUnifiedCommandFormatUsage(unittest.TestCase):
    def test_format_usage_should_include_required_params_and_options_when_params_exist(self):
        cmd = UnifiedCommand(
            name="test",
            params=[
                click.Option(["-d", "--data"], required=True, type=click.STRING),
                click.Option(["-o", "--output"], required=False, type=click.STRING),
            ],
        )
        ctx = MagicMock()
        ctx.command_path = "test"
        ctx.command = cmd
        formatter = HelpFormatter()
        cmd.format_usage(ctx, formatter)
        output = formatter.getvalue()
        self.assertIn("Usage:", output)
        self.assertIn("-d", output)
        self.assertIn("[options]", output)


class TestUnifiedCommandFormatOptions(unittest.TestCase):
    def test_format_options_should_separate_required_and_optional_when_both_exist(self):
        cmd = UnifiedCommand(
            name="test",
            params=[
                click.Option(["-d", "--data"], required=True, help="Data path"),
                click.Option(["-o", "--output"], required=False, help="Output path"),
            ],
        )
        ctx = MagicMock()
        ctx.command = cmd
        formatter = HelpFormatter()
        cmd.format_options(ctx, formatter)
        output = formatter.getvalue()
        self.assertIn("Required arguments", output)
        self.assertIn("Optional arguments", output)
        self.assertIn("--help", output)

    def test_format_options_should_show_only_required_when_no_optional_params(self):
        cmd = UnifiedCommand(
            name="test",
            params=[
                click.Option(["-d", "--data"], required=True, help="Data path"),
            ],
        )
        ctx = MagicMock()
        ctx.command = cmd
        formatter = HelpFormatter()
        cmd.format_options(ctx, formatter)
        output = formatter.getvalue()
        self.assertIn("Required arguments", output)
        self.assertNotIn("Optional arguments", output)


class TestUnifiedCommandFormatHelp(unittest.TestCase):
    def _make_cmd_and_ctx(self, **kwargs):
        cmd = UnifiedCommand(
            name="test",
            params=[
                click.Option(["-d", "--data"], required=True, help="Data path"),
            ],
            **kwargs,
        )
        ctx = MagicMock()
        ctx.command = cmd
        ctx.command_path = "test"
        return cmd, ctx

    def test_format_help_should_include_description_usage_and_options_when_all_sections_present(self):
        cmd, ctx = self._make_cmd_and_ctx(
            help="Test description",
            examples="  test -d /data\n  test -d /data -o /out",
            output="Output format info",
        )
        formatter = HelpFormatter()
        cmd.format_help(ctx, formatter)
        output = formatter.getvalue()
        self.assertIn("Description", output)
        self.assertIn("Test description", output)
        self.assertIn("Usage:", output)
        self.assertIn("Required arguments", output)
        self.assertIn("Examples", output)
        self.assertIn("test -d /data", output)
        self.assertIn("Output", output)
        self.assertIn("Output format info", output)

    def test_format_help_should_not_include_optional_sections_when_not_provided(self):
        cmd, ctx = self._make_cmd_and_ctx()
        formatter = HelpFormatter()
        cmd.format_help(ctx, formatter)
        output = formatter.getvalue()
        self.assertNotIn("Description", output)
        self.assertNotIn("Examples", output)
        self.assertNotIn("Output", output)
        self.assertIn("Usage:", output)
        self.assertIn("Required arguments", output)

    def test_format_help_should_strip_leading_newline_from_examples_when_examples_start_with_newline(self):
        cmd, ctx = self._make_cmd_and_ctx(
            help="Test description",
            examples="\n  test -d /data\n  test -d /data -o /out",
        )
        formatter = HelpFormatter()
        cmd.format_help(ctx, formatter)
        output = formatter.getvalue()
        self.assertIn("test -d /data", output)


class TestUnifiedCommandIntegration(unittest.TestCase):
    def setUp(self):
        self.runner = CliRunner()

    def test_cli_should_display_full_help_when_all_sections_provided(self):
        @click.command(
            cls=UnifiedCommand,
            name="test-cmd",
            help="Test command description",
            examples="  test-cmd -d /data\n  test-cmd -d /data -o /out",
            output="Output section content",
            params=[
                click.Option(["-d", "--data"], required=True, help="Required data path"),
                click.Option(["-o", "--output"], required=False, help="Optional output path"),
            ],
        )
        def cmd(data, output):
            pass

        result = self.runner.invoke(cmd, ["--help"])
        self.assertEqual(result.exit_code, 0)
        self.assertIn("Description", result.output)
        self.assertIn("Test command description", result.output)
        self.assertIn("Usage:", result.output)
        self.assertIn("Required arguments", result.output)
        self.assertIn("Optional arguments", result.output)
        self.assertIn("Examples", result.output)
        self.assertIn("test-cmd -d /data", result.output)
        self.assertIn("Output", result.output)
        self.assertIn("Output section content", result.output)

    def test_cli_should_display_curly_brace_choices_when_unified_choice_used(self):
        @click.command(
            cls=UnifiedCommand,
            name="test-cmd",
            help="Test command",
            params=[
                click.Option(
                    ["-t", "--type"],
                    type=UnifiedChoice(["a", "b", "c"]),
                    help="Type choice",
                ),
            ],
        )
        def cmd(type):
            pass

        result = self.runner.invoke(cmd, ["--help"])
        self.assertEqual(result.exit_code, 0)
        self.assertIn("{a,b,c}", result.output)

    def test_cli_should_display_default_value_when_option_has_default(self):
        @click.command(
            cls=UnifiedCommand,
            name="test-cmd",
            help="Test command",
            params=[
                click.Option(["-n", "--count"], default=10, help="Count value"),
                click.Option(["--flag"], is_flag=True, default=True, help="Enable flag"),
            ],
        )
        def cmd(count, flag):
            pass

        result = self.runner.invoke(cmd, ["--help"])
        self.assertEqual(result.exit_code, 0)
        self.assertIn("[default: 10]", result.output)
        self.assertIn("[default: on]", result.output)
