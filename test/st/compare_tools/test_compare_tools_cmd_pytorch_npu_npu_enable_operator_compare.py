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


class TestCompareToolsCmdPytorchNpuVsNpuEnableOperatorCompare(TestCase):
    BASE_PROFILING_PATH = os.path.join(ST_DATA_PATH, "cluster_data_4",
                                       "n122-197-168_1333345_20241105122131111_ascend_pt")
    COMPARISON_PROFILING_PATH = os.path.join(ST_DATA_PATH, "cluster_data_4",
                                             "n122-197-168_1632305_20241105124759292_ascend_pt")
    OUTPUT_PATH = os.path.join(os.path.abspath(os.path.dirname(__file__)),
                               "CompareToolsCmdPytorchNpuVsNpuEnableOperatorCompare")
    IS_OUTPUT_PATH = os.path.join(os.path.abspath(os.path.dirname(__file__)),
                                  "CompareToolsCmdPytorchNpuVsNpuEnableOperatorInputShapeCompare")
    MKN_OUTPUT_PATH = os.path.join(os.path.abspath(os.path.dirname(__file__)),
                                   "CompareToolsCmdPytorchNpuVsNpuEnableOperatorMaxKernelNumCompare")
    ONM_OUTPUT_PATH = os.path.join(os.path.abspath(os.path.dirname(__file__)),
                                   "CompareToolsCmdPytorchNpuVsNpuEnableOperatorOpNameMapCompare")
    RE_MATCH_EXP = r"^performance_comparison_result_\d{1,20}\.xlsx"
    COMMAND_SUCCESS = 0

    def setup_class(self):
        PathManager.make_dir_safety(self.OUTPUT_PATH)
        PathManager.make_dir_safety(self.IS_OUTPUT_PATH)
        PathManager.make_dir_safety(self.MKN_OUTPUT_PATH)
        PathManager.make_dir_safety(self.ONM_OUTPUT_PATH)
        # 1. no params compare
        cmd = ["msprof-analyze", "compare", "-d", self.COMPARISON_PROFILING_PATH, "-bp", self.BASE_PROFILING_PATH,
               "--enable_operator_compare", "--disable_details", "-o", self.OUTPUT_PATH, "--force"]
        if execute_cmd(cmd) != self.COMMAND_SUCCESS or not os.path.exists(self.OUTPUT_PATH):
            self.assertTrue(False, msg="enable operator compare comparison task failed.")
        if not check_result_file(self.OUTPUT_PATH):
            self.assertTrue(False, msg="enable operator compare comparison result excel is not find.")
        self.result_excel = os.path.join(self.OUTPUT_PATH, check_result_file(self.OUTPUT_PATH))

        # 2. use_input_shape compare
        is_cmd = ["msprof-analyze", "compare", "-d", self.COMPARISON_PROFILING_PATH, "-bp", self.BASE_PROFILING_PATH,
                  "--enable_operator_compare", "--disable_details", "--use_input_shape", "-o", self.IS_OUTPUT_PATH,
                  "--force"]
        if execute_cmd(is_cmd) != self.COMMAND_SUCCESS or not os.path.exists(self.IS_OUTPUT_PATH):
            self.assertTrue(False, msg="enable use input shape operator compare comparison task failed.")
        if not check_result_file(self.IS_OUTPUT_PATH):
            self.assertTrue(False, msg="enable use input shape operator compare comparison result excel is not find.")
        self.is_result_excel = os.path.join(self.IS_OUTPUT_PATH, check_result_file(self.IS_OUTPUT_PATH))

        # 3. max_kernel_num compare
        mkn_cmd = ["msprof-analyze", "compare", "-d", self.COMPARISON_PROFILING_PATH, "-bp", self.BASE_PROFILING_PATH,
                   "--enable_operator_compare", "--disable_details", "--max_kernel_num=10", "-o", self.MKN_OUTPUT_PATH,
                   "--force"]
        if execute_cmd(mkn_cmd) != self.COMMAND_SUCCESS or not os.path.exists(self.MKN_OUTPUT_PATH):
            self.assertTrue(False, msg="enable max kernel num operator compare comparison task failed.")
        if not check_result_file(self.MKN_OUTPUT_PATH):
            self.assertTrue(False, msg="enable max kernel num operator compare comparison result excel is not find.")
        self.mkn_result_excel = os.path.join(self.MKN_OUTPUT_PATH, check_result_file(self.MKN_OUTPUT_PATH))

        # 4. op_name_map compare
        onm_cmd = ["msprof-analyze", "compare", "-d", self.COMPARISON_PROFILING_PATH, "-bp", self.BASE_PROFILING_PATH,
                   "--enable_operator_compare", "--disable_details", "--op_name_map={'aten':'to','aten':'item'}", "-o",
                   self.ONM_OUTPUT_PATH, "--force"]
        if execute_cmd(onm_cmd) != self.COMMAND_SUCCESS or not os.path.exists(self.ONM_OUTPUT_PATH):
            self.assertTrue(False, msg="enable op name map operator compare comparison task failed.")
        if not check_result_file(self.ONM_OUTPUT_PATH):
            self.assertTrue(False, msg="enable op name map operator compare comparison result excel is not find.")
        self.onm_result_excel = os.path.join(self.ONM_OUTPUT_PATH, check_result_file(self.ONM_OUTPUT_PATH))

    def teardown_class(self):
        PathManager.remove_path_safety(self.OUTPUT_PATH)
        PathManager.remove_path_safety(self.IS_OUTPUT_PATH)
        PathManager.remove_path_safety(self.MKN_OUTPUT_PATH)
        PathManager.remove_path_safety(self.ONM_OUTPUT_PATH)

    def test_operator_compare_statistic(self):
        headers = ["Top", "Operator Name", "Base Device Duration(ms)", "Base Operator Number",
                   "Comparison Device Duration(ms)", "Comparison Operator Number", "Diff Duration(ms)", "Diff Ratio"]
        df = pd.read_excel(self.result_excel, sheet_name="OperatorCompareStatistic", header=2)
        self.assertEqual(len(df), 139, msg="pytorch npu vs npu operator compare results 'OperatorCompareStatistic'"
                                           "quantity is wrong")
        self.assertEqual(headers, df.columns.tolist(), msg="pytorch npu vs npu operator compare results "
                                                           "'OperatorCompareStatistic' headers is wrong")

    def test_is_operator_compare_statistic(self):
        headers = ["Top", "Operator Name", "Base Device Duration(ms)", "Base Operator Number",
                   "Comparison Device Duration(ms)", "Comparison Operator Number", "Diff Duration(ms)", "Diff Ratio"]
        df = pd.read_excel(self.is_result_excel, sheet_name="OperatorCompareStatistic", header=2)
        self.assertEqual(len(df), 139, msg="pytorch npu vs npu use input shape operator compare results "
                                           "'OperatorCompareStatistic' quantity is wrong")
        self.assertEqual(headers, df.columns.tolist(), msg="pytorch npu vs npu use input shape operator compare "
                                                           "results 'OperatorCompareStatistic' headers is wrong")

    def test_mkn_operator_compare_statistic(self):
        headers = ["Top", "Operator Name", "Base Device Duration(ms)", "Base Operator Number",
                   "Comparison Device Duration(ms)", "Comparison Operator Number", "Diff Duration(ms)", "Diff Ratio"]
        df = pd.read_excel(self.mkn_result_excel, sheet_name="OperatorCompareStatistic", header=2)
        self.assertEqual(len(df), 139, msg="pytorch npu vs npu use input shape operator compare results "
                                           "'OperatorCompareStatistic' quantity is wrong")
        self.assertEqual(headers, df.columns.tolist(), msg="pytorch npu vs npu use input shape operator compare "
                                                           "results 'OperatorCompareStatistic' headers is wrong")

    def test_onm_operator_compare_statistic(self):
        headers = ["Top", "Operator Name", "Base Device Duration(ms)", "Base Operator Number",
                   "Comparison Device Duration(ms)", "Comparison Operator Number", "Diff Duration(ms)", "Diff Ratio"]
        df = pd.read_excel(self.onm_result_excel, sheet_name="OperatorCompareStatistic", header=2)
        self.assertEqual(len(df), 139, msg="pytorch npu vs npu use input shape operator compare results "
                                           "'OperatorCompareStatistic' quantity is wrong")
        self.assertEqual(headers, df.columns.tolist(), msg="pytorch npu vs npu use input shape operator compare "
                                                           "results 'OperatorCompareStatistic' headers is wrong")
