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

from msprof_analyze.cli.compare_cli import compare_cli


class TestCompareCli(unittest.TestCase):
    def setUp(self):
        self.runner = CliRunner()
        self.cwd = os.getcwd()

    @patch("msprof_analyze.cli.compare_cli.ComparisonGenerator")
    def test_compare_cli_should_call_comparison_generator_when_all_options_provided(self, mock_generator):
        mock_instance = MagicMock()
        mock_generator.return_value = mock_instance

        result = self.runner.invoke(
            compare_cli,
            [
                "-d",
                self.cwd,
                "-bp",
                self.cwd,
                "--enable_profiling_compare",
                "--enable_operator_compare",
                "--enable_memory_compare",
                "--enable_communication_compare",
                "--enable_api_compare",
                "--enable_kernel_compare",
                "--disable_details",
                "--disable_module",
                "-o",
                self.cwd,
                "--max_kernel_num",
                "100",
                "--op_name_map",
                '{"op1": "op2"}',
                "--use_input_shape",
                "--gpu_flow_cat",
                "gpu_flow",
                "--base_step",
                "1",
                "--comparison_step",
                "2",
                "--force",
                "--use_kernel_type",
            ],
        )
        self.assertEqual(result.exit_code, 0)
        mock_generator.assert_called_once()
        mock_instance.run.assert_called_once()

    def test_compare_cli_should_fail_when_required_paths_missing(self):
        result = self.runner.invoke(compare_cli, [])
        self.assertNotEqual(result.exit_code, 0)
