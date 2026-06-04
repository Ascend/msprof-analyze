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

import os
import sys
import unittest
from unittest.mock import MagicMock, patch

import click
from click.testing import CliRunner

from msprof_analyze.cli.entrance import (
    SpecialHelpOrder,
    CliLogo,
    _has_help_option,
    msprof_analyze_cli,
)


class TestSpecialHelpOrder(unittest.TestCase):
    def setUp(self):
        self.cli = SpecialHelpOrder(name="test_cli")

    def test_list_commands_for_help_should_order_by_priority_when_commands_exist(self):
        ctx = MagicMock()
        with patch.object(
            click.Group, 'list_commands', return_value=["advisor", "compare", "auto-completion", "cluster"]
        ):
            result = self.cli.list_commands_for_help(ctx)
            self.assertEqual(result, ["cluster", "compare", "advisor", "auto-completion"])

    def test_parse_args_should_prepend_first_command_when_no_subcommand_with_args(self):
        ctx = MagicMock()
        with patch.object(SpecialHelpOrder, 'list_commands', return_value=["cluster", "compare", "advisor"]):
            with patch.object(click.Group, 'parse_args', return_value=["cluster", "arg1"]) as mock_super:
                self.cli.parse_args(ctx, ["arg1"])
                mock_super.assert_called_once_with(ctx, ["cluster", "arg1"])

    def test_parse_args_should_prepend_help_when_no_subcommand_and_no_args(self):
        ctx = MagicMock()
        with patch.object(SpecialHelpOrder, 'list_commands', return_value=["cluster", "compare", "advisor"]):
            with patch.object(click.Group, 'parse_args', return_value=["--help"]) as mock_super:
                self.cli.parse_args(ctx, [])
                mock_super.assert_called_once_with(ctx, ["--help"])

    def test_should_skip_param_should_return_true_when_param_name_is_help(self):
        param = MagicMock()
        param.name = "help"
        self.assertTrue(self.cli._should_skip_param(param))

    def test_should_skip_param_should_return_true_when_param_name_is_version(self):
        param = MagicMock()
        param.name = "version"
        self.assertTrue(self.cli._should_skip_param(param))

    def test_should_skip_param_should_return_true_when_param_is_eager(self):
        param = MagicMock()
        param.name = "normal_param"
        param.is_eager = True
        self.assertTrue(self.cli._should_skip_param(param))

    def test_should_skip_param_should_return_true_when_param_has_no_opts(self):
        param = MagicMock()
        param.name = "normal_param"
        param.is_eager = False
        param.opts = []
        self.assertTrue(self.cli._should_skip_param(param))

    def test_should_skip_param_should_return_false_when_param_is_valid(self):
        param = MagicMock()
        param.name = "normal_param"
        param.is_eager = False
        param.opts = ["--test-opt"]
        self.assertFalse(self.cli._should_skip_param(param))

    def test_format_param_should_include_required_label_when_param_is_required(self):
        param = MagicMock()
        param.opts = ["--test-opt"]
        param.help = "Test help text"
        param.required = True
        result = self.cli._format_param(param)
        self.assertIn("--test-opt", result)
        self.assertIn("<required>", result)
        self.assertIn("Test help text", result)

    def test_format_param_should_include_optional_label_when_param_is_optional(self):
        param = MagicMock()
        param.opts = ["--test-opt"]
        param.help = "Test help text"
        param.required = False
        result = self.cli._format_param(param)
        self.assertIn("<optional>", result)

    def test_format_param_should_still_format_when_param_has_no_help(self):
        param = MagicMock()
        param.opts = ["--test-opt"]
        param.help = ""
        param.required = False
        result = self.cli._format_param(param)
        self.assertIn("--test-opt", result)

    def test_get_command_params_should_return_empty_when_cmd_has_no_params(self):
        cmd = MagicMock(spec=[])
        result = self.cli._get_command_params(cmd)
        self.assertEqual(result, [])

    def test_get_command_params_should_return_formatted_params_when_cmd_has_params(self):
        param = MagicMock()
        param.name = "test_param"
        param.is_eager = False
        param.opts = ["--test-opt"]
        param.help = "Test help"
        param.required = False

        cmd = MagicMock()
        cmd.params = [param]
        result = self.cli._get_command_params(cmd)
        self.assertEqual(len(result), 1)
        self.assertIn("--test-opt", result[0])

    def test_get_command_params_should_skip_when_param_name_is_help(self):
        param = MagicMock()
        param.name = "help"
        param.is_eager = False
        param.opts = ["--help"]
        param.help = "Show help"

        cmd = MagicMock()
        cmd.params = [param]
        result = self.cli._get_command_params(cmd)
        self.assertEqual(result, [])

    def test_get_command_params_should_skip_when_param_has_empty_help(self):
        param = MagicMock()
        param.name = "test_param"
        param.is_eager = False
        param.opts = ["--test-opt"]
        param.help = ""

        cmd = MagicMock()
        cmd.params = [param]
        result = self.cli._get_command_params(cmd)
        self.assertEqual(result, [])

    def test_get_subcommand_help_should_return_empty_when_cmd_has_no_list_commands(self):
        cmd = MagicMock(spec=[])
        ctx = MagicMock()
        result = self.cli._get_subcommand_help(cmd, "parent", ctx)
        self.assertEqual(result, [])

    def test_get_subcommand_help_should_return_empty_when_subcommands_are_empty(self):
        cmd = MagicMock()
        cmd.list_commands.return_value = []
        ctx = MagicMock()
        result = self.cli._get_subcommand_help(cmd, "parent", ctx)
        self.assertEqual(result, [])

    def test_get_subcommand_help_should_return_help_lines_when_subcommands_exist(self):
        subcmd = MagicMock()
        subcmd.get_short_help_str.return_value = "Subcommand help"
        subcmd.params = []

        cmd = MagicMock()
        cmd.list_commands.return_value = ["sub1"]
        cmd.get_command.return_value = subcmd

        ctx = MagicMock()
        result = self.cli._get_subcommand_help(cmd, "parent", ctx)
        self.assertEqual(len(result), 1)
        self.assertIn("parent sub1", result[0])
        self.assertIn("Subcommand help", result[0])

    def test_get_help_should_include_subcommands_options_when_commands_exist(self):
        ctx = MagicMock()
        with patch.object(SpecialHelpOrder, 'list_commands_for_help', return_value=["cluster", "compare"]):
            with patch.object(click.Group, 'get_help', return_value="Base help"):
                with patch.object(SpecialHelpOrder, 'get_command') as mock_get_cmd:
                    mock_cmd = MagicMock()
                    mock_cmd.get_short_help_str.return_value = "Cluster analysis"
                    mock_cmd.params = []
                    mock_get_cmd.return_value = mock_cmd

                    result = self.cli.get_help(ctx)
                    self.assertIn("Base help", result)
                    self.assertIn("Subcommands Options", result)
                    self.assertIn("cluster", result)


class TestCliLogo(unittest.TestCase):
    def setUp(self):
        self.logo = CliLogo()

    @patch.object(sys, 'stderr')
    def test_should_use_color_logo_should_return_false_when_stderr_is_not_tty(self, mock_stderr):
        mock_stderr.isatty.return_value = False
        self.assertFalse(self.logo._should_use_color_logo())

    @patch.object(sys, 'stderr')
    def test_should_use_color_logo_should_return_true_when_tty_and_term_is_color(self, mock_stderr):
        mock_stderr.isatty.return_value = True
        with patch.dict(os.environ, {"TERM": "xterm-256color"}):
            self.assertTrue(self.logo._should_use_color_logo())

    def test_render_simple_should_contain_mindstudio_when_rendered(self):
        result = self.logo._render_simple()
        self.assertIn("MindStudio", result)
        self.assertIn("ASCEND", result)
        self.assertNotIn("\033", result)

    def test_render_colored_should_contain_escape_codes_when_rendered(self):
        result = self.logo._render_colored()
        self.assertIn("MindStudio", result)
        self.assertIn("\033", result)

    @patch.object(sys, 'stderr')
    def test_print_logo_should_use_colored_output_when_terminal_supports_color(self, mock_stderr):
        mock_stderr.isatty.return_value = True
        with patch.dict(os.environ, {"TERM": "xterm-256color"}):
            self.logo.print_logo()
            mock_stderr.write.assert_called_once()
            call_args = mock_stderr.write.call_args[0][0]
            self.assertIn("\033", call_args)
            mock_stderr.flush.assert_called_once()

    @patch.object(sys, 'stderr')
    def test_print_logo_should_use_simple_output_when_terminal_does_not_support_color(self, mock_stderr):
        mock_stderr.isatty.return_value = False
        self.logo.print_logo()
        mock_stderr.write.assert_called_once()
        call_args = mock_stderr.write.call_args[0][0]
        self.assertNotIn("\033", call_args)
        mock_stderr.flush.assert_called_once()


class TestHasHelpOption(unittest.TestCase):
    def test_has_help_option_should_return_true_when_short_h_in_argv(self):
        with patch.object(sys, 'argv', ['msprof-analyze', '-h']):
            ctx = MagicMock()
            self.assertTrue(_has_help_option(ctx))

    def test_has_help_option_should_return_true_when_double_dash_help_in_argv(self):
        with patch.object(sys, 'argv', ['msprof-analyze', '--help']):
            ctx = MagicMock()
            self.assertTrue(_has_help_option(ctx))

    def test_has_help_option_should_return_false_when_no_help_in_argv(self):
        with patch.object(sys, 'argv', ['msprof-analyze', 'cluster', '--data']):
            ctx = MagicMock()
            self.assertFalse(_has_help_option(ctx))

    def test_has_help_option_should_return_true_when_help_in_protected_args(self):
        with patch.object(sys, 'argv', ['msprof-analyze']):
            ctx = MagicMock()
            ctx.protected_args = ['-h']
            self.assertTrue(_has_help_option(ctx))


class TestMsprofAnalyzeCli(unittest.TestCase):
    def setUp(self):
        self.runner = CliRunner()

    @patch('msprof_analyze.cli.entrance.is_root', return_value=False)
    @patch.object(CliLogo, 'print_logo')
    def test_cli_should_show_help_when_no_args_provided(self, mock_print_logo, mock_is_root):
        result = self.runner.invoke(msprof_analyze_cli, [])
        self.assertEqual(result.exit_code, 0)

    @patch('msprof_analyze.cli.entrance.is_root', return_value=False)
    @patch.object(CliLogo, 'print_logo')
    def test_cli_should_show_help_when_help_option_provided(self, mock_print_logo, mock_is_root):
        result = self.runner.invoke(msprof_analyze_cli, ['--help'])
        self.assertEqual(result.exit_code, 0)

    @patch('msprof_analyze.cli.entrance.is_root', return_value=False)
    @patch.object(CliLogo, 'print_logo')
    def test_cli_should_show_version_when_version_option_provided(self, mock_print_logo, mock_is_root):
        result = self.runner.invoke(msprof_analyze_cli, ['--version'])
        self.assertEqual(result.exit_code, 0)

    @patch('msprof_analyze.cli.entrance.is_root', return_value=True)
    @patch.object(CliLogo, 'print_logo')
    def test_cli_should_still_work_when_running_as_root(self, mock_print_logo, mock_is_root):
        result = self.runner.invoke(msprof_analyze_cli, ['--help'])
        self.assertEqual(result.exit_code, 0)

    @patch('msprof_analyze.cli.entrance.is_root', return_value=False)
    @patch.object(CliLogo, 'print_logo')
    def test_cli_help_should_order_subcommands_by_priority_when_help_invoked(self, mock_print_logo, mock_is_root):
        result = self.runner.invoke(msprof_analyze_cli, ['--help'])
        self.assertEqual(result.exit_code, 0)
        output = result.output
        cluster_idx = output.find("cluster")
        compare_idx = output.find("compare")
        advisor_idx = output.find("advisor")
        auto_idx = output.find("auto-completion")
        self.assertLess(cluster_idx, compare_idx)
        self.assertLess(compare_idx, advisor_idx)
        self.assertLess(advisor_idx, auto_idx)

    @patch('msprof_analyze.cli.entrance.is_root', return_value=False)
    @patch.object(CliLogo, 'print_logo')
    def test_cli_help_should_not_print_logo_when_help_invoked(self, mock_print_logo, mock_is_root):
        result = self.runner.invoke(msprof_analyze_cli, ['--help'])
        self.assertEqual(result.exit_code, 0)
        mock_print_logo.assert_not_called()

    @patch('msprof_analyze.cli.entrance.is_root', return_value=False)
    @patch.object(CliLogo, 'print_logo')
    def test_cli_should_print_logo_when_subcommand_without_help_invoked(self, mock_print_logo, mock_is_root):
        result = self.runner.invoke(msprof_analyze_cli, ['cluster', '--help'])
        self.assertEqual(result.exit_code, 0)
        mock_print_logo.assert_called_once()
