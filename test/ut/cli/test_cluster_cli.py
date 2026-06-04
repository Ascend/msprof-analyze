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

from msprof_analyze.cli.cluster_cli import cluster_cli


class TestClusterCli(unittest.TestCase):
    def setUp(self):
        self.runner = CliRunner()
        self.cwd = os.getcwd()

    @patch("msprof_analyze.cli.cluster_cli.Interface")
    def test_cluster_cli_should_call_interface_run_when_all_options_provided(self, mock_interface):
        mock_instance = MagicMock()
        mock_interface.return_value = mock_instance

        result = self.runner.invoke(
            cluster_cli,
            [
                "-d",
                self.cwd,
                "-m",
                "all",
                "-o",
                self.cwd,
                "--force",
                "--parallel_mode",
                "concurrent",
                "--export_type",
                "db",
                "--rank_list",
                "0,1,2,3",
                "--step_id",
                "1",
            ],
        )
        self.assertEqual(result.exit_code, 0)
        mock_interface.assert_called_once()
        mock_instance.run.assert_called_once()

    def test_cluster_cli_should_fail_when_profiling_path_missing(self):
        result = self.runner.invoke(cluster_cli, [])
        self.assertNotEqual(result.exit_code, 0)
