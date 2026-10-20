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
from unittest import TestCase

import pandas as pd

from msprof_analyze.prof_common.path_manager import PathManager
from test.st.utils import execute_cmd, check_result_file
from test.st.utils import ST_DATA_PATH


class TestCompareToolsCmdPytorchNpuVsNpuEnableKernelCompare(TestCase):
    BASE_PROFILING_PATH = os.path.join(ST_DATA_PATH, "cluster_data_3", "n122-122-067_12380_20240912033946038_ascend_pt")
    COMPARISON_PROFILING_PATH = os.path.join(ST_DATA_PATH, "cluster_data_3",
                                             "n122-122-067_12380_20240912033946038_ascend_pt")
    OUTPUT_PATH = os.path.join(os.path.abspath(os.path.dirname(__file__)),
                               "CompareToolsCmdPytorchNpuVsNpuEnableKernelCompare")
    RE_MATCH_EXP = r"^performance_comparison_result_\d{1,20}\.xlsx"
    COMMAND_SUCCESS = 0

    def setup_class(self):
        PathManager.make_dir_safety(self.OUTPUT_PATH)
        cmd = ["msprof-analyze", "compare", "-d", self.COMPARISON_PROFILING_PATH, "-bp", self.BASE_PROFILING_PATH,
               "--enable_kernel_compare", "-o", self.OUTPUT_PATH, "--force"]
        if execute_cmd(cmd) != self.COMMAND_SUCCESS or not os.path.exists(self.OUTPUT_PATH):
            self.assertTrue(False, msg="enable kernel compare comparison task failed.")
        if not check_result_file(self.OUTPUT_PATH):
            self.assertTrue(False, msg="enable kernel compare comparison result excel is not find.")
        self.result_excel = os.path.join(self.OUTPUT_PATH, check_result_file(self.OUTPUT_PATH))

    def teardown_class(self):
        PathManager.remove_path_safety(self.OUTPUT_PATH)

    def test_kernel_compare(self):
        headers = ["Order Id", "Kernel", "Input Shape", "Total Duration(us)", "Avg Duration(us)",
                   "Max Duration(us)", "Min Duration(us)", "Calls", "Total Duration(us).1", "Avg Duration(us).1",
                   "Max Duration(us).1", "Min Duration(us).1", "Calls.1", "Diff Total Ratio", "Diff Avg Ratio"]
        df = pd.read_excel(self.result_excel, sheet_name="KernelCompare", header=2)
        self.assertEqual(len(df), 709, msg="pytorch npu vs npu kernel compare results quantity is wrong")
        self.assertEqual(headers, df.columns.tolist(), msg="pytorch npu vs npu kernel compare results headers is wrong")
