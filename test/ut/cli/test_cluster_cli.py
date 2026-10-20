# -------------------------------------------------------------------------
# This file is part of the MindStudio project.
# Copyright (c) 2025 Huawei Technologies Co.,Ltd.
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
