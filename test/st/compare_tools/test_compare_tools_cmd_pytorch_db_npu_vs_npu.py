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
from unittest import TestCase

import pandas as pd

from msprof_analyze.prof_common.path_manager import PathManager
from test.st.utils import execute_cmd, check_result_file
from test.st.utils import ST_DATA_PATH


class TestCompareToolsCmdPytorchDbNpuVsNpu(TestCase):
    BASE_PROFILING_PATH = os.path.join(ST_DATA_PATH, "cluster_data_2_db",
                                       "n122-120-121_12321_20240911113658382_ascend_pt")
    COMPARISON_PROFILING_PATH = os.path.join(ST_DATA_PATH, "cluster_data_2_db",
                                             "n122-120-121_12322_20240911113658370_ascend_pt")
    OUTPUT_PATH = os.path.join(os.path.abspath(os.path.dirname(__file__)), "CompareToolsCmdPytorchDbNpuVsNpu")
    COMMAND_SUCCESS = 0
    result_excel = ""

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
            14302.47, 1128.78, 1128.78, 10320.26, 10320.26, 2837.1, 445.59, 2391.52, 16.33, 50636.60, 8412.29, 11.69,
            8400.59, 117.70, 116.68, 1.03, 82.64, 0.16, 82.47, 99.71, 0.00, 99.71, 32759.01, 4480.88, 28278.13,
            17478.85, 17308.09, 170.76, 0.00, 0.00, 0.00, 0.00, 0.00, 0.00, 0.00, 0.00, 0.00, 0.00, 0.00, 0.00, 8313.6,
            8313.6, 0.00, 709.02, 709.02, 65648.08
        ]

        diff_exp = [6.48, 4.84, 4.84, -9.23, -9.23, 10.78, -0.83, 11.61, 0.09, 33.92, -331.06, 100.38, -431.44, -117.70,
                    -116.68, -1.03, -82.64, -0.16, -82.47, -82.30, 0.19, -82.49, -32759.01, -4480.88,
                    -28278.13, -17478.85, -17308.09, -170.76, 170.83, 169.81, 1.02, 81.11, 0.42, 80.69, 32723.27,
                    4472.89, 28250.38, 17478.49, 17307.83, 170.67, -431.79, -8313.6, 7881.82, -47.14, -47.14, -6.73]

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
        self.assertEqual(len(df), 706, msg="pytorch npu vs npu compare results quantity is wrong")
        self.assertEqual(headers, df.columns.tolist(), msg="pytorch npu vs npu compare results headers is wrong")
