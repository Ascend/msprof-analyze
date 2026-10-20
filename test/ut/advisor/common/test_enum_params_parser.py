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
import unittest

from msprof_analyze.advisor.common.enum_params_parser import EnumParamsParser
from test.ut.advisor.advisor_backend.tools.tool import recover_env


class TestEnumParamsParser(unittest.TestCase):
    @classmethod
    def tearDownClass(cls) -> None:
        recover_env()

    def setUp(self) -> None:
        self.enum_params_parser = EnumParamsParser()
        self.argument_keys = sorted(["cann_version", "torch_version", "analysis_dimensions",
                                     "profiling_type", "mindspore_version"])
        self.env_keys = ["ADVISOR_ANALYZE_PROCESSES", "DISABLE_PROFILING_COMPARISON", "DISABLE_AFFINITY_API"]

    def test_get_keys(self):
        total_keys = sorted(self.argument_keys + self.env_keys)
        keys = sorted(self.enum_params_parser.get_keys())
        self.assertIsInstance(keys, list)
        self.assertEqual(keys, total_keys)

    def test_get_argument_keys(self):
        argument_keys = sorted(self.enum_params_parser.get_arguments_keys())
        self.assertIsInstance(argument_keys, list)
        self.assertEqual(argument_keys, self.argument_keys)

    def test_get_env_keys(self):
        env_keys = sorted(self.enum_params_parser.get_envs_keys())
        self.assertIsInstance(env_keys, list)
        self.assertEqual(env_keys, sorted(self.env_keys))

    def test_get_default(self):
        self.assertTrue(self.enum_params_parser.get_default("cann_version"), "8.0.RC1")
        self.assertTrue(self.enum_params_parser.get_default("torch_version"), "2.1.0")
        self.assertTrue(self.enum_params_parser.get_default("analysis_dimensions"),
                        ["computation", "communication", "schedule", "memory"])
        self.assertTrue(self.enum_params_parser.get_default("profiling_type"), "ascend_pytorch_profiler")
        self.assertTrue(self.enum_params_parser.get_default("ADVISOR_ANALYZE_PROCESSES"), 1)

    def test_get_options(self):
        self.assertTrue(self.enum_params_parser.get_options("cann_version"), ["6.3.RC2", "7.0.RC1", "7.0.0", "8.0.RC1"])
        self.assertTrue(self.enum_params_parser.get_options("torch_version"), ["1.11.0", "2.1.0"])
        self.assertTrue(self.enum_params_parser.get_options("analysis_dimensions"),
                        [["computation", "communication", "schedule", "memory"], ["communication"], ["schedule"],
                         ["computation"], ["memory"]])
        self.assertTrue(self.enum_params_parser.get_options("profiling_type"),
                        ["ascend_pytorch_profiler", "mslite", "msprof"])
        self.assertTrue(self.enum_params_parser.get_options("ADVISOR_ANALYZE_PROCESSES"), list(range(1, 9)))
