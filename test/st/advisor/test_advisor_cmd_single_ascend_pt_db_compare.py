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

# pylint: disable=R0801

import os
import logging
from unittest import TestCase

import math
import pandas as pd
from bs4 import BeautifulSoup


from msprof_analyze.prof_common.path_manager import PathManager
from test.st.advisor.utils import get_files, execute_cmd
from test.st.utils import ST_DATA_PATH


class TestAdvisorCmdSingleAscendPtDBCompare(TestCase):
    BASE_PROFILING_PATH = os.path.join(
        ST_DATA_PATH, "cluster_data_2_db", "n122-120-121_12321_20240911113658382_ascend_pt"
    )
    COMPARISON_PROFILING_PATH = os.path.join(
        ST_DATA_PATH, "cluster_data_2_db", "n122-120-121_12322_20240911113658370_ascend_pt"
    )
    OUTPUT_PATH = os.path.join(os.path.abspath(os.path.dirname(__file__)), "TestAdvisorCmdSingleAscendPtDBCompare")
    ALL_OUTPUT_PATH = os.path.join(OUTPUT_PATH, "all")
    result_excel = {}
    result_html = {}
    COMMAND_SUCCESS = 0

    def setup_class(self):
        PathManager.make_dir_safety(self.ALL_OUTPUT_PATH)
        cmd_all = [
            "msprof-analyze",
            "advisor",
            "all",
            "-d",
            self.BASE_PROFILING_PATH,
            "-bp",
            self.COMPARISON_PROFILING_PATH,
            "-o",
            self.ALL_OUTPUT_PATH,
            "-l",
            "en",
            "--force",
        ]
        if execute_cmd(cmd_all) != self.COMMAND_SUCCESS or not os.path.exists(self.ALL_OUTPUT_PATH):
            self.fail(msg="advisor [all] [bp] task failed.")
        self.result_html, self.result_excel = get_files(self.OUTPUT_PATH)

    def teardown_class(self):
        PathManager.remove_path_safety(self.OUTPUT_PATH)

    def test_all_problems(self):
        category = [
            "Kernel compare of Target and Benchmark",
            "Byte Alignment Analysis",
            "Bandwidth Contention Analysis",
            "Cube Operator Perf Analysis",
            "Block Dim Issues",
            "AICPU Issues",
            "Fusible Operator Analysis",
            "Operator Dispatch Issues",
        ]

        # True presents the attr is nan
        description_len = [1, 1, 3, 1, 6, 2, 1, 1]
        suggestion_len = [True, 1, 1, 1, True, 2, 2, 1]
        problem_count = [True, True, True, True, 5921, 2, True, True]
        total_time = [True, True, True, True, 87840734.826, 87840734.826, True, True]
        time_ratio = [True, True, True, True, 0.0033, 0, True, True]
        income = [True, True, True, True, True, True, True, True]
        income_ratio = [True, True, True, True, True, True, True, True]
        try:
            df = pd.read_excel(self.result_excel.get("all", None), sheet_name='problems', header=0)
        except FileNotFoundError:
            logging.error("File %s not found.", str(self.result_excel.get("all", None)))
            return

        for index, row in df.iterrows():
            self.assertEqual(category[index], row["category"])
            self.assertEqual(description_len[index], len(row["description"].split("\n")))
            self.assertEqual(
                suggestion_len[index], isinstance(row["suggestion"], float) or len(row["suggestion"].split("\n"))
            )
            self.assertEqual(problem_count[index], (math.isnan(row["problem count"]) or row["problem count"]))
            self.assertEqual(total_time[index], (math.isnan(row["total_time(us)"]) or round(row["total_time(us)"], 3)))
            self.assertEqual(time_ratio[index], (math.isnan(row["time ratio"]) or round(row["time ratio"], 4)))
            self.assertEqual(income[index], (math.isnan(row["income(us)"]) or round(row["income(us)"], 2)))
            self.assertEqual(income_ratio[index], (math.isnan(row["income ratio"]) or round(row["income ratio"], 2)))

    def test_byte_alignment_analysis(self):
        op_name = ["hcom_broadcast__568_2_1", "hcom_reduceScatter__257_1_1", "hcom_allGather__257_2_1"]

        total_size = [24274052, 670986240, 335493120]

        duration = [997.164, 35740.428, 17278.562]

        abnormal_duration = [997.164, 35740.428, 17278.562]

        bandwidth = [24.3431, 18.7739, 19.4167]

        test_pattern = ["all"]
        for pattern in test_pattern:
            try:
                df = pd.read_excel(self.result_excel.get(pattern, None), sheet_name='Byte Alignment Analysis', header=0)
            except FileNotFoundError:
                logging.error("File %s not found.", self.result_excel.get(pattern, None))
                return

            for index, row in df.iterrows():
                self.assertEqual(op_name[index], row["op name"])
                self.assertEqual(total_size[index], row["total size(Byte)"])
                self.assertEqual(duration[index], row["duration(us)"])
                self.assertEqual(abnormal_duration[index], row["abnormal duration(us)"])
                self.assertEqual(bandwidth[index], row["bandwidth(GB/s)"])

            with open(self.result_html.get(pattern, None), encoding='utf-8') as f:
                soup = BeautifulSoup(f, 'html.parser')
            for h2 in soup.find_all('h2'):
                if h2.contents[0] == "Byte Alignment Analysis":
                    div_content = h2.next.next.next
                    table = div_content.find_all('table')
                    for row_index, row in enumerate(table[1].find_all('tr')):
                        if row_index == 0:
                            continue
                        self.assertEqual(str(op_name[row_index - 1]), row.find_all('td')[0].text)
                        self.assertEqual(str(total_size[row_index - 1]), row.find_all('td')[1].text)
                        self.assertEqual(str(round(duration[row_index - 1], 3)), row.find_all('td')[2].text)
                        self.assertEqual(str(round(abnormal_duration[row_index - 1], 3)), row.find_all('td')[3].text)
                        self.assertEqual(str(round(bandwidth[row_index - 1], 4)), row.find_all('td')[4].text)

    def test_all_bandwidth_contention_analysis(self):
        bandwidth_contention_analysis = [
            "hcom_allGather__114_1_1",
            "hcom_allGather__114_4_1",
            "hcom_allGather__114_109_1",
            "hcom_allGather__114_113_1",
            "hcom_allGather__114_117_1",
            "hcom_allGather__114_121_1",
            "hcom_allGather__114_125_1",
            "hcom_allGather__114_129_1",
            "hcom_allGather__114_133_1",
            "hcom_allGather__114_173_1",
            "hcom_allGather__114_177_1",
            "hcom_allGather__114_181_1",
            "hcom_allGather__114_185_1",
            "hcom_allGather__114_189_1",
            "hcom_allGather__114_193_1",
            "hcom_allGather__114_197_1",
            "hcom_allGather__114_209_1",
            "hcom_reduceScatter__568_261_1",
            "hcom_reduceScatter__114_275_1",
            "hcom_reduceScatter__114_283_1",
            "hcom_reduceScatter__114_315_1",
            "hcom_allGather__114_316_1",
            "hcom_reduceScatter__114_331_1",
            "hcom_reduceScatter__114_347_1",
            "hcom_allGather__114_348_1",
            "hcom_reduceScatter__114_355_1",
            "hcom_reduceScatter__114_363_1",
            "hcom_reduceScatter__114_371_1",
            "hcom_reduceScatter__114_379_1",
            "hcom_reduceScatter__114_387_1",
            "hcom_allGather__114_388_1",
            "hcom_reduceScatter__114_411_1",
            "hcom_allGather__114_412_1",
            "hcom_reduceScatter__114_419_1",
            "hcom_allGather__114_420_1",
            "hcom_reduceScatter__114_427_1",
            "hcom_reduceScatter__114_435_1",
            "hcom_reduceScatter__114_443_1",
            "hcom_reduceScatter__114_451_1",
            "hcom_reduceScatter__114_467_1",
            "hcom_allGather__114_468_1",
            "hcom_reduceScatter__114_475_1",
            "hcom_allGather__114_476_1",
            "hcom_reduceScatter__114_483_1",
            "hcom_reduceScatter__114_491_1",
            "hcom_reduceScatter__114_499_1",
            "hcom_reduceScatter__114_507_1",
            "hcom_reduceScatter__114_515_1",
            "hcom_reduceScatter__114_531_1",
            "hcom_reduceScatter__114_539_1",
            "hcom_reduceScatter__114_547_1",
            "hcom_reduceScatter__114_555_1",
            "hcom_allGather__114_556_1",
            "hcom_reduceScatter__114_563_1",
            "hcom_reduceScatter__114_571_1",
            "hcom_reduceScatter__114_579_1",
            "hcom_reduceScatter__114_587_1",
            "hcom_reduceScatter__114_595_1",
            "hcom_reduceScatter__114_603_1",
            "hcom_reduceScatter__114_611_1",
            "hcom_reduceScatter__114_619_1",
            "hcom_reduceScatter__114_635_1",
            "hcom_reduceScatter__114_643_1",
            "hcom_allGather__114_644_1",
            "hcom_reduceScatter__114_651_1",
            "hcom_reduceScatter__114_659_1",
            "hcom_reduceScatter__114_667_1",
            "hcom_allGather__114_668_1",
            "hcom_reduceScatter__114_675_1",
            "hcom_allGather__114_676_1",
            "hcom_reduceScatter__114_683_1",
            "hcom_allGather__114_684_1",
            "hcom_reduceScatter__114_691_1",
        ]

        duration = [
            8.3508,
            15.4094,
            9.5789,
            8.5513,
            8.3012,
            9.1346,
            8.7032,
            9.3836,
            8.7531,
            11.9869,
            9.8575,
            9.7712,
            9.9296,
            12.6163,
            9.6824,
            9.1268,
            11.0426,
            15.7377,
            48.7819,
            73.1451,
            134.33,
            14.7282,
            127.4724,
            127.9985,
            12.5301,
            124.9251,
            123.348,
            122.798,
            123.1688,
            132.2497,
            11.5286,
            120.421,
            12.1733,
            123.3453,
            9.9289,
            124.3953,
            124.8201,
            126.5423,
            122.8442,
            130.256,
            12.7242,
            128.1858,
            12.174,
            123.4281,
            123.2906,
            122.3294,
            123.7423,
            126.1776,
            127.7836,
            127.616,
            123.5298,
            120.636,
            11.249,
            123.3667,
            125.7421,
            123.9869,
            124.2625,
            121.3439,
            124.2089,
            126.8418,
            123.9893,
            125.8097,
            117.6455,
            13.4391,
            124.0685,
            126.6376,
            123.167,
            12.0098,
            121.3413,
            13.7026,
            118.2242,
            13.1474,
            116.1516,
        ]
        bandwidth = [
            6.38,
            11.11,
            5.2,
            6.64,
            7.02,
            4.97,
            7.83,
            8.02,
            6.44,
            8.54,
            4.59,
            4.17,
            6.48,
            5.02,
            6.13,
            4.42,
            5.17,
            12.26,
            13.98,
            3.5,
            4.48,
            2.95,
            3.13,
            2.87,
            4.96,
            2.83,
            2.5,
            2.58,
            3.36,
            2.89,
            3.99,
            3.26,
            3.76,
            2.98,
            5.14,
            2.95,
            2.74,
            2.4,
            2.37,
            2.94,
            3.76,
            3.14,
            4.12,
            2.92,
            2.6,
            2.35,
            2.38,
            2.5,
            2.9,
            3.35,
            2.5,
            2.92,
            4.23,
            2.76,
            2.07,
            2.48,
            2.8,
            3.3,
            2.4,
            2.59,
            2.41,
            2.94,
            5.01,
            3.33,
            2.53,
            2.66,
            2.87,
            4.51,
            3.28,
            3.7,
            6.45,
            3.85,
            9.02,
        ]
        try:
            df = pd.read_excel(self.result_excel.get("all", None), sheet_name='Bandwidth Contention Analysis', header=0)
        except FileNotFoundError:
            logging.error("File %s not found.", str(self.result_excel.get("all", None)))
            return

        for index, row in df.iterrows():
            self.assertEqual(bandwidth_contention_analysis[index], row["op name"])
            self.assertEqual(duration[index], round(row["duration(ms)"], 4))
            self.assertEqual(bandwidth[index], round(row["bandwidth(GB/s)"], 2))

    def test_aicpu_operator(self):
        op_name = ["aclnnEqScalar_EqualAiCpu_Equal", "aclnnPowTensorScalar_SquareAiCpu_Square"]
        op_type = ["Equal", "Square"]
        task_duration = [94.422, 87.862]
        input_shapes = ["\"41;\"", "\"41\""]
        input_data_types = ["DOUBLE;DOUBLE", "INT64"]
        input_formats = ["FORMAT_ND;FORMAT_ND", "FORMAT_ND"]
        output_shapes = ["\"41\"", "\"41\""]
        output_data_types = ["BOOL", "INT64"]
        output_formats = ["FORMAT_ND", "FORMAT_ND"]
        stack_info = [True, True]

        t0_description = ["Square, Equal"]
        t0_suggestion = ["aclnnEqScalar_EqualAiCpu_Equal"]
        t0_elapsed_time = ["182.28"]
        t0_time_ratio = ["0.0"]
        t1_operator_type = ["Equal"]
        t1_counts = ["1"]
        t1_elapsed_time = ["94.42"]
        t2_operator_type = ["Square"]
        t2_counts = ["1"]
        t2_elapsed_time = ["87.86"]
        b_names = ["Equal", "Suggestion 1:", "Square", "Suggestion 1:"]

        try:
            df = pd.read_excel(self.result_excel.get("all", None), sheet_name='AICPU Issues', header=0)
        except FileNotFoundError:
            logging.error("File %s not found.", str(self.result_excel.get("all", None)))
            return

        for index, row in df.iterrows():
            self.assertEqual(op_name[index], row["op_name"])
            self.assertEqual(op_type[index], row["op_type"])
            self.assertEqual(task_duration[index], round(row["task_duration"], 3))
            self.assertEqual(input_shapes[index], row["input_shapes"])
            self.assertEqual(input_data_types[index], row["input_data_types"])
            self.assertEqual(input_formats[index], row["input_formats"])
            self.assertEqual(output_shapes[index], row["output_shapes"])
            self.assertEqual(output_data_types[index], row["output_data_types"])
            self.assertEqual(output_formats[index], row["output_formats"])
            self.assertEqual(stack_info[index], math.isnan(row["stack_info"]))

        with open(self.result_html.get("all", None), encoding='utf-8') as f:
            soup = BeautifulSoup(f, 'html.parser')
        for h2 in soup.find_all('h2'):
            if h2.contents[0] == "AICPU Issues":
                div_content = h2.next.next.next
                table = div_content.find_all('table')
                for row_index, row in enumerate(table[0].find_all('tr')):
                    if row_index == 0:
                        continue
                    self.assertEqual(
                        t0_description[row_index - 1], row.find_all('td')[0].text.split(":")[1].replace("\n", "")
                    )
                    self.assertEqual(t0_suggestion[row_index - 1], row.find_all('td')[1].text.split(" ")[-1])
                    self.assertEqual(t0_elapsed_time[row_index - 1], row.find_all('td')[2].text)
                    self.assertEqual(t0_time_ratio[row_index - 1], row.find_all('td')[3].text)
                for row_index, row in enumerate(table[1].find_all('tr')):
                    if row_index == 0:
                        continue
                    self.assertEqual(t1_operator_type[row_index - 1], row.find_all('td')[0].text)
                    self.assertEqual(t1_counts[row_index - 1], row.find_all('td')[1].text)
                    self.assertEqual(t1_elapsed_time[row_index - 1], row.find_all('td')[2].text)
                for row_index, row in enumerate(table[2].find_all('tr')):
                    if row_index == 0:
                        continue
                    self.assertEqual(t2_operator_type[row_index - 1], row.find_all('td')[0].text)
                    self.assertEqual(t2_counts[row_index - 1], row.find_all('td')[1].text)
                    self.assertEqual(t2_elapsed_time[row_index - 1], row.find_all('td')[2].text)

                b_contents = div_content.find_all('b')
                for b_index, b_content in enumerate(b_contents):
                    self.assertEqual(b_names[b_index], b_content.text)
