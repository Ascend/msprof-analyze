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
from typing import List
from unittest import TestCase

import pandas as pd

from msprof_analyze.prof_common.path_manager import PathManager
from test.st.utils import execute_cmd, check_result_file
from test.st.utils import ST_DATA_PATH


class TestCompareToolsCmdPytorchNpuVsNpuEnableProfiling(TestCase):
    BASE_PROFILING_PATH = os.path.join(ST_DATA_PATH, "cluster_data_4",
                                       "n122-197-168_1333345_20241105122131111_ascend_pt")
    COMPARISON_PROFILING_PATH = os.path.join(ST_DATA_PATH, "cluster_data_4",
                                             "n122-197-168_1632305_20241105124759292_ascend_pt")
    OUTPUT_PATH = os.path.join(os.path.abspath(os.path.dirname(__file__)),
                               "CompareToolsCmdPytorchNpuVsNpuEnableProfiling")
    COMMAND_SUCCESS = 0

    def setup_class(self):
        PathManager.make_dir_safety(self.OUTPUT_PATH)
        cmd = ["msprof-analyze", "compare", "-d", self.COMPARISON_PROFILING_PATH, "-bp", self.BASE_PROFILING_PATH,
               "--enable_profiling_compare", "-o", self.OUTPUT_PATH, "--force"]
        if execute_cmd(cmd) != self.COMMAND_SUCCESS or not os.path.exists(self.OUTPUT_PATH):
            self.assertTrue(False, msg="enable profiling comparison task failed.")
        if not check_result_file(self.OUTPUT_PATH):
            self.assertTrue(False, msg="enable profiling comparison result excel is not find.")
        self.result_excel = os.path.join(self.OUTPUT_PATH, check_result_file(self.OUTPUT_PATH))

    def teardown_class(self):
        PathManager.remove_path_safety(self.OUTPUT_PATH)

    def test_overall_metrics(self):
        duration_exp: List[float] = [
            1725.15, 11.98, 11.98, 31.78, 31.78, 756.62, 705.49, 51.13, 879.83, 66.23, 813.60, 32.90, 12.04, 520.82,
            307.11, 13.12, 293.99, 0.00, 0.00, 207.81, 0.01, 207.80, 5.87, 0.01, 5.86, 0.03, 0.03, 2897.92, 2897.92,
            5143.89
        ]
        diff_exp: List[float] = [
            0.34, 0.00, 0.00, 0.01, 0.01, 0.15, 0.14, 0.01, 0.17, 0.01, 0.16, 0.01, 0.00, 0.10, 0.06, 0.00, 0.06, 0.00,
            0.00, 0.04, 0.00, 0.04, 0.00, 0.00, 0.00, 0.00, 0.00, 0.56, 0.56, 1.00]
        df = pd.read_excel(self.result_excel, sheet_name="OverallMetrics", header=2)
        for index, row in df.iterrows():
            self.assertEqual(duration_exp[index], round(row["Duration(ms)"], 2),
                             msg="pytorch npu vs npu enable profiling compare results 'Duration(ms)"
                                 "' column is wrong")
            self.assertEqual(diff_exp[index], round(row["Duration Ratio"], 2),
                             msg="pytorch npu vs npu enable profiling compare results 'Duration Ratio"
                                 "' column is wrong")
