# Copyright (c) 2025, Huawei Technologies Co., Ltd. All rights reserved.
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

import sys
import unittest
from unittest.mock import MagicMock, patch, call
import click
from click.testing import CliRunner
from msprof_analyze.advisor.utils.tools import ClickAliasedGroup, CONTEXT_SETTINGS


class TestClickAliasedGroup(unittest.TestCase):
    def setUp(self):
        self.runner = CliRunner()

    def test_init(self):
        group = ClickAliasedGroup()
        self.assertEqual(group._alias_dict, {})
        self.assertEqual(group._commands, {})
        self.assertEqual(group.FORMAT_LIMIT_LEN, 6)

    def test_resolve_alias_existing(self):
        group = ClickAliasedGroup()
        group._alias_dict = {'tc': 'test_cmd'}

        result = group.resolve_alias('tc')
        self.assertEqual(result, 'test_cmd')

    def test_resolve_alias_non_existing(self):
        group = ClickAliasedGroup()
        group._alias_dict = {'tc': 'test_cmd'}

        result = group.resolve_alias('nonexistent')
        self.assertEqual(result, 'nonexistent')

    def test_get_command_non_existing(self):
        group = ClickAliasedGroup()
        mock_ctx = MagicMock()

        command = group.get_command(mock_ctx, 'nonexistent')
        self.assertIsNone(command)

    def test_format_commands_no_commands(self):
        group = ClickAliasedGroup()
        mock_ctx = MagicMock()
        mock_formatter = MagicMock()

        mock_formatter.section.return_value.__enter__ = MagicMock(return_value=None)
        mock_formatter.section.return_value.__exit__ = MagicMock(return_value=None)
        group.format_commands(mock_ctx, mock_formatter)
        mock_formatter.write_dl.assert_not_called()

    def test_decorator_wrapper(self):
        group = ClickAliasedGroup()
        mock_decorator = MagicMock()
        mock_cmd = MagicMock()
        mock_cmd.name = 'test_cmd'
        mock_decorator.return_value = mock_cmd
        
        mock_func = MagicMock()
        result = group._decorator_warpper(mock_decorator, 'tc', mock_func)

        mock_decorator.assert_called_once_with(mock_func)
        self.assertEqual(group._commands['test_cmd'], 'tc')
        self.assertEqual(group._alias_dict['tc'], 'test_cmd')
        self.assertEqual(result, mock_cmd)

    def test_command_help_truncation(self):
        group = ClickAliasedGroup()

        @group.command(alias='tc')
        def test_cmd():
            """This is a very long help text that should be truncated when displayed in the command list"""
            pass

        mock_ctx = MagicMock()
        mock_formatter = MagicMock()
        mock_formatter.width = 40

        captured_rows = []

        def mock_write_dl(rows):
            nonlocal captured_rows
            captured_rows = rows

        mock_formatter.write_dl = mock_write_dl
        mock_formatter.section.return_value.__enter__ = MagicMock(return_value=None)
        mock_formatter.section.return_value.__exit__ = MagicMock(return_value=None)

        group.format_commands(mock_ctx, mock_formatter)

        self.assertEqual(len(captured_rows), 1)
        command_str, help_str = captured_rows[0]
        self.assertTrue(len(help_str) <= 45 - group.FORMAT_LIMIT_LEN - len('test_cmd, tc'))

    def test_format_commands_without_alias(self):
        group = ClickAliasedGroup()

        @group.command()
        def test_cmd():
            pass

        mock_ctx = MagicMock()
        mock_formatter = MagicMock()
        mock_formatter.width = 80

        captured_rows = []
        
        def mock_write_dl(rows):
            nonlocal captured_rows
            captured_rows = rows

        mock_formatter.write_dl = mock_write_dl
        mock_formatter.section.return_value.__enter__ = MagicMock(return_value=None)
        mock_formatter.section.return_value.__exit__ = MagicMock(return_value=None)

        group.format_commands(mock_ctx, mock_formatter)

        self.assertEqual(len(captured_rows), 1)
        command_str, help_str = captured_rows[0]
        self.assertEqual(command_str, 'test-cmd')