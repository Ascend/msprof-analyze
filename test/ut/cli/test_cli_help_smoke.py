# -------------------------------------------------------------------------
# This file is part of the MindStudio project.
# Copyright (c) 2026 Ivan Yampolskiy
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

import os
import tempfile
import unittest
from pathlib import Path

import click
from click.testing import CliRunner

from msprof_analyze.cli.entrance import msprof_analyze_cli


class TestCliStartup(unittest.TestCase):
    def test_help_imports_and_formats_every_command_group(self):
        runner = CliRunner()
        for arguments in (
            ["--help"],
            ["advisor", "--help"],
            ["advisor", "all", "--help"],
            ["cluster", "--help"],
            ["compare", "--help"],
        ):
            with self.subTest(arguments=arguments):
                result = runner.invoke(msprof_analyze_cli, arguments)
                self.assertEqual(result.exit_code, 0, str(result.exception))
                self.assertIn("Usage:", result.output)

    def test_output_options_accept_directories_and_reject_files(self):
        commands = (
            msprof_analyze_cli.commands["cluster"],
            msprof_analyze_cli.commands["compare"],
            msprof_analyze_cli.commands["advisor"].commands["all"],
        )
        with tempfile.TemporaryDirectory() as directory:
            file_path = Path(directory) / "not-a-directory"
            file_path.write_text("data", encoding="utf-8")
            for command in commands:
                with self.subTest(command=command.name):
                    option = next(param for param in command.params if param.name == "output_path")
                    context = click.Context(command)
                    self.assertEqual(option.type.convert(directory, option, context), directory)
                    self.assertEqual(
                        option.type.convert(os.path.join(directory, "new-output"), option, context),
                        os.path.join(directory, "new-output"),
                    )
                    with self.assertRaises(click.BadParameter):
                        option.type.convert(str(file_path), option, context)
