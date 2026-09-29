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


class TestCompareToolsCmdPytorchNpuVsNpuEnableCommunicationCompare(TestCase):
    BASE_PROFILING_PATH = os.path.join(ST_DATA_PATH, "cluster_data_3", "n122-122-067_12380_20240912033946038_ascend_pt")
    COMPARISON_PROFILING_PATH = os.path.join(ST_DATA_PATH, "cluster_data_3",
                                             "n122-122-067_12380_20240912033946038_ascend_pt")
    OUTPUT_PATH = os.path.join(os.path.abspath(os.path.dirname(__file__)),
                               "CompareToolsCmdPytorchNpuVsNpuEnableCommunicationCompare")
    RE_MATCH_EXP = r"^performance_comparison_result_\d{1,20}\.xlsx"
    COMMAND_SUCCESS = 0

    def setup_class(self):
        PathManager.make_dir_safety(self.OUTPUT_PATH)
        cmd = ["msprof-analyze", "compare", "-d", self.COMPARISON_PROFILING_PATH, "-bp", self.BASE_PROFILING_PATH,
               "--enable_communication_compare", "-o", self.OUTPUT_PATH, "--force"]
        if execute_cmd(cmd) != self.COMMAND_SUCCESS or not os.path.exists(self.OUTPUT_PATH):
            self.assertTrue(False, msg="enable communication compare comparison task failed.")
        if not check_result_file(self.OUTPUT_PATH):
            self.assertTrue(False, msg="enable communication compare comparison result excel is not find.")
        self.result_excel = os.path.join(self.OUTPUT_PATH, check_result_file(self.OUTPUT_PATH))

    def teardown_class(self):
        PathManager.remove_path_safety(self.OUTPUT_PATH)

    def test_communication_compare(self):
        total_duration: List[float] = [
            9354.86, 1046.68, 9191.52, 24.74, 27743477.86, 12418099.90, 23832.90, 28928712.46,
            18411.66, 2939703.28, 327934.12, 17074.96, 77.58, 931489.92, 2894.42, 75.46, 80.86,
            15119087.00, 3594561.44, 12963.36, 12692002.20, 6180907.46, 9859.70
        ]
        cvg_duration: List[float] = [
            3118.29, 174.45, 340.43, 0.92, 36504.58, 399.89, 0.77, 389.03, 0.32, 7988.32, 27327.84,
            148.48, 0.71, 2957.11, 144.72, 0.32, 3.85, 32374.92, 392.81, 0.76, 316.17, 790.20, 0.32]
        df = pd.read_excel(self.result_excel, sheet_name="CommunicationCompare", header=2)
        for index, row in df.iterrows():
            self.assertEqual(total_duration[index], round(row["Total Duration(us)"], 2),
                             msg="pytorch npu vs npu communication compare results 'Total Duration(us)"
                                 "' column is wrong")
            self.assertEqual(cvg_duration[index], round(row["Avg Duration(us)"], 2),
                             msg="pytorch npu vs npu communication compare results 'Avg Duration(us)"
                                 "' column is wrong"
                             )
