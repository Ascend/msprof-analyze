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


class TestCompareToolsCmdPytorchNpuVsNpu(TestCase):
    BASE_PROFILING_PATH = os.path.join(ST_DATA_PATH, "cluster_data_2", "n122-120-121_12321_20240911113658382_ascend_pt")
    COMPARISON_PROFILING_PATH = os.path.join(ST_DATA_PATH, "cluster_data_2",
                                             "n122-120-121_12322_20240911113658370_ascend_pt")
    OUTPUT_PATH = os.path.join(os.path.abspath(os.path.dirname(__file__)), "CompareToolsCmdPytorchNpuVsNpu")
    COMMAND_SUCCESS = 0

    def setup_class(self):
        PathManager.make_dir_safety(self.OUTPUT_PATH)
        cmd = ["msprof-analyze", "compare", "-d", self.COMPARISON_PROFILING_PATH, "-bp", self.BASE_PROFILING_PATH, "-o",
               self.OUTPUT_PATH, "--force"]
        if execute_cmd(cmd) != self.COMMAND_SUCCESS or not os.path.exists(self.OUTPUT_PATH):
            self.assertTrue(False, msg="comparison task failed.")
        if not check_result_file(self.OUTPUT_PATH):
            self.assertTrue(False, msg="comparison result excel is not find.")
        self.result_excel = os.path.join(self.OUTPUT_PATH, check_result_file(self.OUTPUT_PATH))

    def teardown_class(self):
        PathManager.remove_path_safety(self.OUTPUT_PATH)

    def test_overall_metrics(self):
        duration_exp = [
            14302.47, 1128.78, 1128.78, 10320.26, 10320.26, 2836.92, 445.59, 2391.33, 16.33, 0.18, 50636.60,
            8412.29, 11.69, 8400.59, 117.70, 116.68, 1.03, 82.64, 0.16, 82.47, 99.71, 0.00, 99.71, 32759.01, 32759.01,
            17478.85, 17308.09, 170.76, 8313.60, 8313.60, 682.94, 682.94, 65622.00
        ]
        diff_exp = [6.48, 4.84, 4.84, -9.23, -9.23, 10.77, -0.83, 11.60, 0.09, 0.01, 33.92, -331.06, 100.38, -431.44,
                    53.12, 53.13, -0.01, -1.53, 0.26, -1.79, -82.30, 0.19, -82.49, -35.74, -35.74, -0.36, -0.27, -0.09,
                    -431.79, -431.79, -48.46, -48.46, -8.05]
        df = pd.read_excel(self.result_excel, sheet_name="OverallMetrics", header=2)
        for index, row in df.iterrows():
            self.assertEqual(duration_exp[index], round(row["Duration(ms)"], 2),
                             msg="pytorch npu vs npu compare results 'Duration(ms)"
                                 "' column is wrong"
                             )
            self.assertEqual(diff_exp[index], round(row["Diff Duration(ms)"], 2),
                             msg="pytorch npu vs npu compare results 'Diff Duration(ms)"
                                 "' column is wrong"
                             )

    def test_kernel_compare(self):
        headers = ["Order Id", "Kernel", "Input Shape", "Total Duration(us)", "Avg Duration(us)", "Max Duration(us)",
                   "Min Duration(us)", "Calls", "Total Duration(us).1", "Avg Duration(us).1", "Max Duration(us).1",
                   "Min Duration(us).1", "Calls.1", "Diff Total Ratio", "Diff Avg Ratio"]
        df = pd.read_excel(self.result_excel, sheet_name="KernelCompare", header=2)
        self.assertEqual(len(df), 710, msg="pytorch npu vs npu compare results quantity is wrong")
        self.assertEqual(headers, df.columns.tolist(), msg="pytorch npu vs npu compare results headers is wrong")
