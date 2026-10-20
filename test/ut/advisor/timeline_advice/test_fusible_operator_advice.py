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
import shutil
import stat
import csv
import multiprocessing
import unittest
from msprof_analyze.advisor.interface.interface import Interface
from msprof_analyze.advisor.common.analyzer_scopes import SupportedScopes


class TestFusibleOperatorAdvice(unittest.TestCase):
    TMP_DIR = "./ascend_pt"
    OUTPUT_DIR = "./ascend_pt/ASCEND_PROFILER_OUTPUT"
    interface = None

    @staticmethod
    def run_should_run_success_when_kernel_details_not_contain_fusible_operators():
        interface = Interface(profiling_path="./ascend_pt")
        dimension = "schedule"
        scope = SupportedScopes.FUSIBLE_OPERATOR_ANALYSIS
        result = interface.get_result(dimension, scope, render_html=1, output_dict=False, profiling_path="./ascend_pt")
        assert len(result.data) == 0
        result.clear()

    @staticmethod
    def run_should_run_success_when_kernel_details_contain_host_bound():
        interface = Interface(profiling_path="./ascend_pt")
        dimension = "schedule"
        scope = SupportedScopes.FUSIBLE_OPERATOR_ANALYSIS
        result = interface.get_result(dimension, scope, render_html=1, output_dict=False, profiling_path="./ascend_pt")
        assert len(result.data.get("基于host瓶颈的算子序列分析", {}).get("data", [])) == 3
        result.clear()

    @staticmethod
    def run_should_run_success_when_kernel_details_contain_mte_bound():
        interface = Interface(profiling_path="./ascend_pt")
        dimension = "schedule"
        scope = SupportedScopes.FUSIBLE_OPERATOR_ANALYSIS
        result = interface.get_result(dimension, scope, render_html=1, output_dict=False, profiling_path="./ascend_pt")
        assert len(result.data.get("基于mte瓶颈的算子序列分析", {}).get("data", [])) == 4
        result.clear()

    @staticmethod
    def run_should_run_success_when_kernel_details_contain_mte_and_host_bound():
        interface = Interface(profiling_path="./ascend_pt")
        dimension = "schedule"
        scope = SupportedScopes.FUSIBLE_OPERATOR_ANALYSIS
        result = interface.get_result(dimension, scope, render_html=1, output_dict=False, profiling_path="./ascend_pt")
        assert len(result.data.get("基于mte瓶颈的算子序列分析", {}).get("data", [])) == 3
        assert len(result.data.get("基于host瓶颈的算子序列分析", {}).get("data", [])) == 3
        result.clear()

    @classmethod
    def create_kernel_details_without_bound(cls):
        # create csv files
        csv_header = [
            'Name', 'Type', 'Accelerator Core', 'Start Time(us)', 'Duration(us)', 'aicore_time(us)',
            'aic_mte2_time(us)', 'aic_fixpipe_time(us)', 'aiv_mte2_time(us)', 'aiv_mte3_time(us)', "Input Shapes",
            "Output Shapes"
        ]
        csv_row1 = ['MatMul56', 'MatMul', 'AI_CORE', "0\t", 10, 8, 2, 0, 0, 0, 0, "1;1", "2;2"]
        csv_row2 = ['Add2', 'Add', 'AI_VECTOR_CORE', "13\t", 5, 3, 1, 0, 0, 0, 0, "1;1", "3;3"]
        csv_row3 = ['MatMul57', 'MatMul', 'AI_CORE', "19\t", 12, 9, 2, 0, 0, 0, 0, "1;1", "4;4"]
        csv_row4 = ['Add1', 'Add', 'AI_CORE', "33\t", 3.14, 2.56, 1, 0, 0, 0, 0, "1;1", "4;4"]

        with os.fdopen(os.open(f"{TestFusibleOperatorAdvice.OUTPUT_DIR}/kernel_details.csv",
                               os.O_WRONLY | os.O_CREAT, stat.S_IWUSR | stat.S_IRUSR), 'w', newline='') as fp:
            csv_writer = csv.writer(fp)
            csv_writer.writerow(csv_header)
            csv_writer.writerow(csv_row1)
            csv_writer.writerow(csv_row2)
            csv_writer.writerow(csv_row3)
            csv_writer.writerow(csv_row4)

    @classmethod
    def create_kernel_details_with_mte_bound(cls):
        # create csv files
        csv_header = [
            'Name', 'Type', 'Accelerator Core', 'Start Time(us)', 'Duration(us)', 'aicore_time(us)',
            'aic_mte2_time(us)', 'aic_fixpipe_time(us)', 'aiv_mte2_time(us)', 'aiv_mte3_time(us)', "Input Shapes",
            "Output Shapes"
        ]
        csv_row1 = ['MatMul56', 'MatMul', 'AI_CORE', "0\t", 10, 8, 7, 0, 0, 0, 0, "1;1", "2;2"]
        csv_row2 = ['Add2', 'Add', 'AI_VECTOR_CORE', "13\t", 5, 3, 2, 0, 0, 0, 0, "1;1", "21;2"]
        csv_row3 = ['MatMul57', 'MatMul', 'AI_CORE', "19\t", 12, 9, 8, 0, 0, 0, 0, "1;1", "23;2"]
        csv_row4 = ['Add1', 'Add', 'AI_CORE', "33\t", 3.14, 2.56, 1, 0, 0, 0, 0, "1;1", "24;2"]

        with os.fdopen(os.open(f"{TestFusibleOperatorAdvice.OUTPUT_DIR}/kernel_details.csv",
                               os.O_WRONLY | os.O_CREAT, stat.S_IWUSR | stat.S_IRUSR), 'w', newline='') as fp:
            csv_writer = csv.writer(fp)
            csv_writer.writerow(csv_header)
            for _ in range(7):
                csv_writer.writerow(csv_row1)
                csv_writer.writerow(csv_row2)
                csv_writer.writerow(csv_row3)
                csv_writer.writerow(csv_row4)

    @classmethod
    def create_kernel_details_with_host_bound(cls):
        # create csv files
        csv_header = [
            'Name', 'Type', 'Accelerator Core', 'Start Time(us)', 'Duration(us)', 'aicore_time(us)',
            'aic_mte2_time(us)', 'aic_fixpipe_time(us)', 'aiv_mte2_time(us)', 'aiv_mte3_time(us)', "Input Shapes",
            "Output Shapes"
        ]
        csv_row1 = ['MatMul56', 'MatMul', 'AI_CORE', "0\t", 20, 18, 7, 0, 0, 0, 0, "1;1", "2;2"]
        csv_row2 = ['Add2', 'Add', 'AI_VECTOR_CORE', "83\t", 25, 13, 2, 0, 0, 0, 0, "1;1", "21;2"]
        csv_row3 = ['MatMul57', 'MatMul', 'AI_CORE', "169\t", 12, 9, 8, 0, 0, 0, 0, "1;1", "23;2"]
        csv_row4 = ['Add1', 'Add', 'AI_CORE', "183\t", 3.14, 2.56, 1, 0, 0, 0, 0, "1;1", "24;2"]
        csv_row5 = ['hcom_allreduce', 'allreduce', "HCCL", "233\t", 3.14, 2.56, 1, 0, 0, 0, 0, "1;1", "24;2"]

        with os.fdopen(os.open(f"{TestFusibleOperatorAdvice.OUTPUT_DIR}/kernel_details.csv",
                               os.O_WRONLY | os.O_CREAT, stat.S_IWUSR | stat.S_IRUSR), 'w', newline='') as fp:
            csv_writer = csv.writer(fp)
            csv_writer.writerow(csv_header)
            for _ in range(7):
                csv_writer.writerow(csv_row1)
                csv_writer.writerow(csv_row2)
                csv_writer.writerow(csv_row3)
                csv_writer.writerow(csv_row4)
                csv_writer.writerow(csv_row5)

    @classmethod
    def create_kernel_details_with_host_and_mte_bound(cls):
        # create csv files
        csv_header = [
            'Name', 'Type', 'Accelerator Core', 'Start Time(us)', 'Duration(us)', 'aicore_time(us)',
            'aic_mte2_time(us)', 'aic_fixpipe_time(us)', 'aiv_mte2_time(us)', 'aiv_mte3_time(us)', "Input Shapes",
            "Output Shapes"
        ]
        csv_row1 = ['MatMul56', 'MatMul', 'AI_CORE', "0\t", 20, 18, 17, 0, 0, 0, 0, "1;1", "2;2"]
        csv_row2 = ['Add2', 'Add', 'AI_VECTOR_CORE', "83\t", 25, 13, 12, 0, 0, 0, 0, "1;1", "21;2"]
        csv_row3 = ['MatMul57', 'MatMul', 'AI_CORE', "169\t", 12, 9, 8, 0, 0, 0, 0, "1;1", "23;2"]
        csv_row4 = ['Add1', 'Add', 'AI_CORE', "183\t", 3.14, 2.56, 1, 0, 0, 0, 0, "1;1", "24;2"]
        csv_row5 = ['hcom_allreduce', 'allreduce', "HCCL", "233\t", 3.14, 2.56, 1, 0, 0, 0, 0, "1;1", "24;2"]

        with os.fdopen(os.open(f"{TestFusibleOperatorAdvice.OUTPUT_DIR}/kernel_details.csv",
                               os.O_WRONLY | os.O_CREAT, stat.S_IWUSR | stat.S_IRUSR), 'w', newline='') as fp:
            csv_writer = csv.writer(fp)
            csv_writer.writerow(csv_header)
            for _ in range(7):
                csv_writer.writerow(csv_row1)
                csv_writer.writerow(csv_row2)
                csv_writer.writerow(csv_row3)
                csv_writer.writerow(csv_row4)
                csv_writer.writerow(csv_row5)

    @classmethod
    def clear_htmls(cls):
        current_path = os.path.dirname(os.path.abspath(__file__))
        for filename in os.listdir(current_path):
            # 检查文件是否以“att”开头
            if filename.startswith("mstt"):
                # 构建文件的完整路径
                file_path = os.path.join(current_path, filename)
                # 删除文件
                os.remove(file_path)

    def tearDown(self):
        if os.path.exists(TestFusibleOperatorAdvice.TMP_DIR):
            shutil.rmtree(TestFusibleOperatorAdvice.TMP_DIR)
        self.clear_htmls()

    def setUp(self):
        if os.path.exists(TestFusibleOperatorAdvice.TMP_DIR):
            shutil.rmtree(TestFusibleOperatorAdvice.TMP_DIR)
        if not os.path.exists(TestFusibleOperatorAdvice.TMP_DIR):
            os.makedirs(TestFusibleOperatorAdvice.TMP_DIR)
        if not os.path.exists(TestFusibleOperatorAdvice.OUTPUT_DIR):
            os.makedirs(TestFusibleOperatorAdvice.OUTPUT_DIR)
        self.clear_htmls()

    def test_run_should_run_success_when_kernel_details_not_contain_fusible_operators(self):
        self.create_kernel_details_without_bound()
        new_process = multiprocessing.Process(
            target=self.run_should_run_success_when_kernel_details_not_contain_fusible_operators)
        new_process.start()
        new_process.join()

    def test_run_should_run_success_when_kernel_details_contain_mte_bound(self):
        self.create_kernel_details_with_mte_bound()
        new_process = multiprocessing.Process(
            target=self.run_should_run_success_when_kernel_details_contain_mte_bound)
        new_process.start()
        new_process.join()

    def test_run_should_run_success_when_kernel_details_contain_host_bound(self):
        self.create_kernel_details_with_host_bound()
        new_process = multiprocessing.Process(
            target=self.run_should_run_success_when_kernel_details_contain_host_bound)
        new_process.start()
        new_process.join()

    def test_run_should_run_success_when_kernel_details_contain_mte_and_host_bound(self):
        self.create_kernel_details_with_host_and_mte_bound()
        new_process = multiprocessing.Process(
            target=self.run_should_run_success_when_kernel_details_contain_mte_and_host_bound)
        new_process.start()
        new_process.join()
