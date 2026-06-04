# Copyright (c) 2025, Huawei Technologies Co., Ltd.
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
import unittest
from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from msprof_analyze.cli.analyze_cli import analyze_cli, _handle_agent_mode


class TestHandleAgentMode(unittest.TestCase):
    def test_handle_agent_mode_should_set_env_when_agent_is_true(self):
        with patch.dict(os.environ, {}, clear=True):
            _handle_agent_mode({"agent": True})
            self.assertEqual(os.environ.get("AGENT_MODE"), "agent")

    def test_handle_agent_mode_should_not_set_env_when_agent_is_false(self):
        with patch.dict(os.environ, {}, clear=True):
            _handle_agent_mode({"agent": False})
            self.assertIsNone(os.environ.get("AGENT_MODE"))


class TestAnalyzeCli(unittest.TestCase):
    def setUp(self):
        self.runner = CliRunner()
        self.cwd = os.getcwd()

    @patch("msprof_analyze.cli.analyze_cli.AnalyzerController")
    def test_analyze_all_should_call_do_analysis_when_all_options_provided(self, mock_controller):
        mock_instance = MagicMock()
        mock_controller.return_value = mock_instance

        result = self.runner.invoke(
            analyze_cli,
            [
                "all",
                "-d",
                self.cwd,
                "-bp",
                self.cwd,
                "-o",
                self.cwd,
                "-cv",
                "8.0.RC1",
                "-pt",
                "pytorch",
                "--force",
                "-l",
                "en",
                "--agent",
            ],
        )
        self.assertEqual(result.exit_code, 0)
        mock_instance.do_analysis.assert_called_once()

    @patch("msprof_analyze.cli.analyze_cli.AnalyzerController")
    def test_analyze_all_should_not_raise_when_do_analysis_throws_exception(self, mock_controller):
        mock_instance = MagicMock()
        mock_instance.do_analysis.side_effect = RuntimeError("test error")
        mock_controller.return_value = mock_instance

        result = self.runner.invoke(analyze_cli, ["all", "-d", self.cwd])
        self.assertEqual(result.exit_code, 0)

    def test_analyze_all_should_fail_when_profiling_path_missing(self):
        result = self.runner.invoke(analyze_cli, ["all"])
        self.assertNotEqual(result.exit_code, 0)
