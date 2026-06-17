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


class TestAdvisorCmdSingleAscendPtNoCompare(TestCase):
    ST_DATA_PATH = os.getenv("MSPROF_ANALYZE_ST_DATA_PATH", "/data/msprof-analyze-st-data")
    BASE_PROFILING_PATH = os.path.join(ST_DATA_PATH, "cluster_data_3", "n122-122-067_12380_20240912033946038_ascend_pt")
    OUTPUT_PATH = os.path.join(os.path.abspath(os.path.dirname(__file__)), "TestAdvisorCmdSingleAscendPtNoCompare")
    ALL_OUTPUT_PATH = os.path.join(OUTPUT_PATH, "all")
    COMPUTATION_OUTPUT_PATH = os.path.join(OUTPUT_PATH, "computation")
    SCHEDULE_OUTPUT_PATH = os.path.join(OUTPUT_PATH, "schedule")
    COMMAND_SUCCESS = 0
    result_html = {}
    result_excel = {}

    def setup_class(self):
        PathManager.make_dir_safety(self.ALL_OUTPUT_PATH)
        PathManager.make_dir_safety(self.COMPUTATION_OUTPUT_PATH)
        PathManager.make_dir_safety(self.SCHEDULE_OUTPUT_PATH)
        cmd_all = [
            "msprof-analyze",
            "advisor",
            "all",
            "-d",
            self.BASE_PROFILING_PATH,
            "-o",
            self.ALL_OUTPUT_PATH,
            "-l",
            "en",
            "--force",
        ]
        if execute_cmd(cmd_all) != self.COMMAND_SUCCESS or not os.path.exists(self.ALL_OUTPUT_PATH):
            self.fail(msg="advisor [all] task failed.")

        cmd_computation = [
            "msprof-analyze",
            "advisor",
            "computation",
            "-d",
            self.BASE_PROFILING_PATH,
            "-o",
            self.COMPUTATION_OUTPUT_PATH,
            "-l",
            "en",
            "--force",
        ]
        if execute_cmd(cmd_computation) != self.COMMAND_SUCCESS or not os.path.exists(self.COMPUTATION_OUTPUT_PATH):
            self.fail(msg="advisor [computation] task failed.")

        cmd_schedule = [
            "msprof-analyze",
            "advisor",
            "schedule",
            "-d",
            self.BASE_PROFILING_PATH,
            "-o",
            self.SCHEDULE_OUTPUT_PATH,
            "-l",
            "en",
            "--force",
        ]
        if execute_cmd(cmd_schedule) != self.COMMAND_SUCCESS or not os.path.exists(self.SCHEDULE_OUTPUT_PATH):
            self.fail(msg="advisor [schedule] task failed.")

        self.result_html, self.result_excel = get_files(self.OUTPUT_PATH)

    def teardown_class(self):
        PathManager.remove_path_safety(self.OUTPUT_PATH)

    def test_all_problems(self):
        category = [
            "Overall Summary",
            "Byte Alignment Analysis",
            "Bandwidth Contention Analysis",
            "Cube Operator Perf Analysis",
            "AICPU Issues",
            "Operator Dynamic Shape Issues",
            "Fusible Operator Analysis",
            "Affinity API Issues",
            "Operator Dispatch Issues",
        ]

        # True presents the attr is nan
        description_len = [6, 1, 3, 1, 2, 1, 1, 1, 1]
        suggestion_len = [True, 1, 1, 1, 2, 4, 2, 1, 1]
        problem_count = [True, True, True, True, 2.0, 1.0, True, True, True]
        total_time = [True, True, True, True, 57674709.54, True, True, True, True]
        time_ratio = [True, True, True, True, 0.0, True, True, True, True]
        income = [True, True, True, True, True, True, True, True, True]
        income_ratio = [True, True, True, True, True, True, True, True, True]
        try:
            df = pd.read_excel(self.result_excel.get("all", None), sheet_name='problems', header=0)
        except FileNotFoundError:
            logging.error("File %s not found.", self.result_excel.get("all", None))
            return

        for index, row in df.iterrows():
            self.assertEqual(category[index], row["category"])
            self.assertEqual(description_len[index], len(row["description"].split("\n")))
            self.assertEqual(
                suggestion_len[index], isinstance(row["suggestion"], float) or len(row["suggestion"].split("\n"))
            )
            self.assertEqual(problem_count[index], (math.isnan(row["problem count"]) or row["problem count"]))
            self.assertEqual(total_time[index], (math.isnan(row["total_time(us)"]) or round(row["total_time(us)"], 2)))
            self.assertEqual(time_ratio[index], (math.isnan(row["time ratio"]) or round(row["time ratio"], 2)))
            self.assertEqual(income[index], (math.isnan(row["income(us)"]) or round(row["income(us)"], 2)))
            self.assertEqual(income_ratio[index], (math.isnan(row["income ratio"]) or round(row["income ratio"], 2)))

    def test_computation_problems(self):
        category = [
            "overall summary",
            "AICPU operator",
            "Dynamic shape operator",
        ]

        # True presents the attr is nan
        description_len = [6, 2, 1]
        suggestion_len = [True, 2, 5]
        problem_count = [True, 2.0, 1.0]
        total_time = [True, 57674709.54, True]
        time_ratio = [True, 0.0, True]
        income = [True, True, True]
        income_ratio = [True, True, True]
        try:
            df = pd.read_excel(self.result_excel.get("computation", None), sheet_name='problems', header=0)
        except FileNotFoundError:
            logging.error("File %s not found.", self.result_excel.get("computation", None))
            return

        for index, row in df.iterrows():
            self.assertEqual(category[index], row["category"])
            self.assertEqual(description_len[index], len(row["description"].split("\n")))
            self.assertEqual(
                suggestion_len[index], (isinstance(row["suggestion"], float) or len(row["suggestion"].split("\n")))
            )
            self.assertEqual(problem_count[index], (math.isnan(row["problem count"]) or row["problem count"]))
            self.assertEqual(total_time[index], (math.isnan(row["total_time(us)"]) or round(row["total_time(us)"], 2)))
            self.assertEqual(time_ratio[index], (math.isnan(row["time ratio"]) or round(row["time ratio"], 2)))
            self.assertEqual(income[index], (math.isnan(row["income(us)"]) or round(row["income(us)"], 2)))
            self.assertEqual(income_ratio[index], (math.isnan(row["income ratio"]) or round(row["income ratio"], 2)))

    def test_schedule_problems(self):
        category = ["overall summary", "Affinity apis", "Operator dispatch"]

        # True presents the attr is nan
        description_len = [6, 1, 1]
        suggestion_len = [True, 1, 1]
        problem_count = [True, True, True]
        total_time = [True, True, True]
        time_ratio = [True, True, True]
        income = [True, True, True]
        income_ratio = [True, True, True]
        try:
            df = pd.read_excel(self.result_excel.get("schedule", None), sheet_name='problems', header=0)
        except FileNotFoundError:
            logging.error("File %s not found.", self.result_excel.get("schedule", None))
            return

        for index, row in df.iterrows():
            self.assertEqual(category[index], row["category"])
            self.assertEqual(description_len[index], len(row["description"].split("\n")))
            self.assertEqual(
                suggestion_len[index], (isinstance(row["suggestion"], float) or len(row["suggestion"].split("\n")))
            )
            self.assertEqual(problem_count[index], (math.isnan(row["problem count"]) or row["problem count"]))
            self.assertEqual(total_time[index], (math.isnan(row["total_time(us)"]) or round(row["total_time(us)"], 2)))
            self.assertEqual(time_ratio[index], (math.isnan(row["time ratio"]) or round(row["time ratio"], 2)))
            self.assertEqual(income[index], (math.isnan(row["income(us)"]) or round(row["income(us)"], 2)))
            self.assertEqual(income_ratio[index], (math.isnan(row["income ratio"]) or round(row["income ratio"], 2)))

    def test_overall_summary(self):
        performance_index = [
            "Computing Time",
            "    -- Flash Attention",
            "    -- Conv",
            "    -- Matmul",
            "    -- Vector",
            "    -- SDMA(Tensor Move)",
            "    -- Other Cube",
            "Uncovered Communication Time",
            "    -- Wait",
            "    -- Transmit",
            "Free Time",
            "    -- SDMA",
            "    -- Free",
            "E2E Time",
        ]
        duration = [
            14474.856,
            1194.014,
            0.000,
            10442.616,
            2821.569,
            16.473,
            0.0,
            23922.059,
            138.275,
            23783.785,
            373.722,
            0.000,
            373.722,
            38770.637,
        ]
        duration_ratio = [
            "37.33%",
            "3.08%",
            "0.00%",
            "26.93%",
            "7.28%",
            "0.04%",
            "0.00%",
            "61.70%",
            "0.36%",
            "61.34%",
            "0.96%",
            "0.00%",
            "0.96%",
            "100.00%",
        ]

        test_pattern = ["all", "computation", "schedule"]
        for pattern in test_pattern:
            try:
                df = pd.read_excel(self.result_excel.get(pattern, None), sheet_name='overall summary', header=0)
            except FileNotFoundError:
                logging.error("File %s not found.", self.result_excel.get(pattern, None))
                return

            for index, row in df.iterrows():
                self.assertEqual(performance_index[index], row["Performance Index"])
                self.assertEqual(duration[index], row["Duration(ms)"])
                self.assertEqual(duration_ratio[index], row["Duration Ratio"])

            with open(self.result_html.get(pattern, None), encoding='utf-8') as f:
                soup = BeautifulSoup(f, 'html.parser')
            for h2 in soup.find_all('h2'):
                if h2.contents[0] == "overall summary":
                    div_content = h2.next.next.next
                    table = div_content.find_all('table')
                    for row_index, row in enumerate(table[0].find_all('tr')):
                        if row_index == 0:
                            continue
                        self.assertEqual(performance_index[row_index - 1], row.find_all('td')[0].text)
                        self.assertEqual("{:.3f}".format(duration[row_index - 1]), row.find_all('td')[1].text)
                        self.assertEqual(duration_ratio[row_index - 1], row.find_all('td')[2].text)

    def test_all_bandwidth_contention_analysis(self):
        bandwidth_contention_analysis = [
            "hcom_allGather__508_1_1",
            "hcom_allGather__508_4_1",
            "hcom_allGather__508_8_1",
            "hcom_allGather__508_108_1",
            "hcom_allGather__508_112_1",
            "hcom_allGather__508_113_1",
            "hcom_allGather__508_137_1",
            "hcom_allGather__508_141_1",
            "hcom_allGather__508_145_1",
            "hcom_allGather__508_153_1",
            "hcom_allGather__508_157_1",
            "hcom_allGather__508_173_1",
            "hcom_allGather__508_177_1",
            "hcom_allGather__508_181_1",
            "hcom_allGather__508_209_1",
            "hcom_reduceScatter__868_261_1",
            "hcom_reduceScatter__868_266_1",
            "hcom_allGather__508_276_1",
            "hcom_reduceScatter__508_283_1",
            "hcom_reduceScatter__508_291_1",
            "hcom_reduceScatter__508_299_1",
            "hcom_reduceScatter__508_307_1",
            "hcom_allGather__508_308_1",
            "hcom_reduceScatter__508_315_1",
            "hcom_reduceScatter__508_323_1",
            "hcom_reduceScatter__508_331_1",
            "hcom_reduceScatter__508_339_1",
            "hcom_reduceScatter__508_347_1",
            "hcom_reduceScatter__508_355_1",
            "hcom_allGather__508_356_1",
            "hcom_reduceScatter__508_363_1",
            "hcom_reduceScatter__508_371_1",
            "hcom_allGather__508_372_1",
            "hcom_reduceScatter__508_379_1",
            "hcom_reduceScatter__508_387_1",
            "hcom_allGather__508_388_1",
            "hcom_reduceScatter__508_395_1",
            "hcom_reduceScatter__508_403_1",
            "hcom_allGather__508_404_1",
            "hcom_reduceScatter__508_411_1",
            "hcom_reduceScatter__508_419_1",
            "hcom_reduceScatter__508_427_1",
            "hcom_reduceScatter__508_435_1",
            "hcom_reduceScatter__508_443_1",
            "hcom_reduceScatter__508_451_1",
            "hcom_reduceScatter__508_459_1",
            "hcom_reduceScatter__508_467_1",
            "hcom_allGather__508_468_1",
            "hcom_reduceScatter__508_475_1",
            "hcom_reduceScatter__508_483_1",
            "hcom_reduceScatter__508_491_1",
            "hcom_reduceScatter__508_499_1",
            "hcom_reduceScatter__508_507_1",
            "hcom_reduceScatter__508_515_1",
            "hcom_allGather__508_516_1",
            "hcom_reduceScatter__508_523_1",
            "hcom_reduceScatter__508_531_1",
            "hcom_reduceScatter__508_539_1",
            "hcom_reduceScatter__508_547_1",
            "hcom_reduceScatter__508_555_1",
            "hcom_reduceScatter__508_563_1",
            "hcom_reduceScatter__508_571_1",
            "hcom_reduceScatter__508_579_1",
            "hcom_reduceScatter__508_587_1",
            "hcom_allGather__508_588_1",
            "hcom_reduceScatter__508_595_1",
            "hcom_reduceScatter__508_603_1",
            "hcom_reduceScatter__508_611_1",
            "hcom_reduceScatter__508_619_1",
            "hcom_reduceScatter__508_627_1",
            "hcom_reduceScatter__508_635_1",
            "hcom_reduceScatter__508_643_1",
            "hcom_allGather__508_644_1",
            "hcom_reduceScatter__508_651_1",
            "hcom_reduceScatter__508_659_1",
            "hcom_reduceScatter__508_667_1",
            "hcom_reduceScatter__508_675_1",
            "hcom_reduceScatter__508_683_1",
        ]
        duration = [
            8.3454,
            13.8113,
            39.8263,
            21.6036,
            38.2598,
            5.3913,
            13.4007,
            9.6871,
            8.8002,
            10.0535,
            8.3423,
            9.3205,
            11.3891,
            9.473,
            12.7247,
            19.4176,
            13.2621,
            16.3541,
            127.5414,
            127.288,
            126.6839,
            129.0707,
            11.8205,
            128.8378,
            130.0548,
            128.3927,
            124.9711,
            128.0221,
            122.8157,
            11.7839,
            127.0278,
            123.3328,
            11.9078,
            122.3141,
            123.1837,
            11.2561,
            123.8337,
            127.5955,
            11.5881,
            123.0412,
            128.4852,
            122.3674,
            127.1958,
            127.5779,
            129.6155,
            127.2981,
            125.5495,
            11.0916,
            127.4827,
            126.4632,
            125.0414,
            123.9187,
            125.168,
            127.1,
            12.6763,
            126.3728,
            126.9693,
            127.677,
            127.1439,
            127.2013,
            127.9102,
            125.7989,
            126.4961,
            127.6573,
            12.2088,
            127.6283,
            126.3803,
            129.8238,
            126.2997,
            127.4806,
            129.2007,
            127.2733,
            12.0963,
            126.8322,
            127.5317,
            126.482,
            127.8283,
            129.2951,
        ]
        bandwidth = [
            5.49,
            4.8,
            5.99,
            14.13,
            3.24,
            6.25,
            8.52,
            5.17,
            5.34,
            8.24,
            5.43,
            6.15,
            9.79,
            5.55,
            4.39,
            13.35,
            13.14,
            3.61,
            2.51,
            2.88,
            2.83,
            3.07,
            4.81,
            2.55,
            2.57,
            2.73,
            2.84,
            2.44,
            3.01,
            4.95,
            2.63,
            3.06,
            3.77,
            2.88,
            3.44,
            4.72,
            2.91,
            3.21,
            4.47,
            2.38,
            2.31,
            2.9,
            4.26,
            3.57,
            2.31,
            2.24,
            2.81,
            4.37,
            2.67,
            2.8,
            2.74,
            2.16,
            2.79,
            2.88,
            5.79,
            2.75,
            2.93,
            2.88,
            2.31,
            2.72,
            2.39,
            2.6,
            2.55,
            2.58,
            4.29,
            2.69,
            2.86,
            2.09,
            3.12,
            2.31,
            2.28,
            2.87,
            6.97,
            3.1,
            2.35,
            3.4,
            2.61,
            2.62,
        ]
        try:
            df = pd.read_excel(self.result_excel.get("all", None), sheet_name='Bandwidth Contention Analysis', header=0)
        except FileNotFoundError:
            logging.error("File %s not found.", self.result_excel.get("all", None))
            return

        for index, row in df.iterrows():
            self.assertEqual(bandwidth_contention_analysis[index], row["op name"])
            self.assertEqual(duration[index], round(row["duration(ms)"], 4))
            self.assertEqual(bandwidth[index], round(row["bandwidth(GB/s)"], 2))

        # wait repair bugs to check html

    def test_aicpu_operator(self):
        op_name = ["aclnnPowTensorScalar_SquareAiCpu_Square", "aclnnEqScalar_EqualAiCpu_Equal"]
        op_type = ["Square", "Equal"]
        task_duration = [92.06, 90.72]
        input_shapes = ["\"41\"", "\"41;\""]
        input_data_types = ["INT64", "DOUBLE;DOUBLE"]
        input_formats = ["FORMAT_ND", "FORMAT_ND;FORMAT_ND"]
        output_shapes = ["\"41\"", "\"41\""]
        output_data_types = ["INT64", "BOOL"]
        output_formats = ["FORMAT_ND", "FORMAT_ND"]
        stack_info = [True, True]

        t0_description = ["Square, Equal"]
        t0_suggestion = ["aclnnEqScalar_EqualAiCpu_Equal"]
        t0_elapsed_time = ["182.78"]
        t0_time_ratio = ["0.0"]
        t1_operator_type = ["Square"]
        t1_counts = ["1"]
        t1_elapsed_time = ["92.06"]
        t2_operator_type = ["Equal"]
        t2_counts = ["1"]
        t2_elapsed_time = ["90.72"]
        b_names = ["Square", "Suggestion 1:", "Equal", "Suggestion 1:"]

        test_pattern = ["all", "computation"]
        for pattern in test_pattern:
            try:
                df = pd.read_excel(self.result_excel.get(pattern, None), sheet_name='AICPU operator', header=0)
            except FileNotFoundError:
                logging.error("File %s not found.", self.result_excel.get(pattern, None))
                return

            for index, row in df.iterrows():
                self.assertEqual(op_name[index], row["op_name"])
                self.assertEqual(op_type[index], row["op_type"])
                self.assertEqual(task_duration[index], round(row["task_duration"], 2))
                self.assertEqual(input_shapes[index], row["input_shapes"])
                self.assertEqual(input_data_types[index], row["input_data_types"])
                self.assertEqual(input_formats[index], row["input_formats"])
                self.assertEqual(output_shapes[index], row["output_shapes"])
                self.assertEqual(output_data_types[index], row["output_data_types"])
                self.assertEqual(output_formats[index], row["output_formats"])
                self.assertEqual(stack_info[index], math.isnan(row["stack_info"]))

            with open(self.result_html.get(pattern, None), encoding='utf-8') as f:
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

    def test_affinity_api(self):
        affinity_api = ["torch_npu.npu_confusion_transpose", "torch_npu.optim.NpuFusedAdamW"]
        code_stacks = [True, True]
        stack_called_counts = [True, True]
        ignore_api = ["torch_npu.optim.NpuFusedAdamW", "torch_npu.npu_confusion_transpose"]

        test_pattern = ["all", "schedule"]
        for pattern in test_pattern:
            try:
                df = pd.read_excel(self.result_excel.get(pattern, None), sheet_name='Affinity apis', header=0)
            except FileNotFoundError:
                logging.error("File %s not found.", self.result_excel.get(pattern, None))
                return

            for index, row in df.iterrows():
                self.assertEqual(affinity_api[index], row["Affinity API"])
                self.assertEqual(code_stacks[index], math.isnan(row["Code stacks"]))
                self.assertEqual(stack_called_counts[index], math.isnan(row["Stack called counts"]))

            with open(self.result_html.get(pattern, None), encoding='utf-8') as f:
                soup = BeautifulSoup(f, 'html.parser')
            for h2 in soup.find_all('h2'):
                if h2.contents[0] == "Affinity API Issues":
                    div_content = h2.next.next.next
                    self.assertEqual(ignore_api[0], div_content.contents[-2].contents[-2].text)
                    self.assertEqual(ignore_api[1], div_content.contents[-2].contents[-4].text)

    def test_operator_dispatch(self):
        issues = ["operator dispatch"]
        op_name = ["aclopCompileAndExecute"]
        counts = [381]
        total_time = [58486.7048]

        t0_description = ["381"]
        t0_suggestion = ["torch_npu.npu.set_compile_mode(jit_compile=False)"]
        t1_issue = ["aclopCompileAndExecute"]
        t1_counts = ['381']
        t1_elapsed_time = ['58486.704798215804']

        test_pattern = ["all", "schedule"]
        for pattern in test_pattern:
            try:
                df = pd.read_excel(self.result_excel.get(pattern, None), sheet_name='operator dispatch', header=0)
            except FileNotFoundError:
                logging.error("File %s not found.", self.result_excel.get(pattern, None))
                return
            for index, row in df.iterrows():
                self.assertEqual(issues[index], row["Issues"])
                self.assertEqual(op_name[index], row["op name"])
                self.assertEqual(counts[index], row["counts"])
                self.assertEqual(total_time[index], round(row["total time"], 4))

            with open(self.result_html.get(pattern, None), encoding='utf-8') as f:
                soup = BeautifulSoup(f, 'html.parser')
            for h2 in soup.find_all('h2'):
                if h2.contents[0] == "Operator Dispatch Issues":
                    div_content = h2.next.next.next
                    table = div_content.find_all('table')
                    for row_index, row in enumerate(table[0].find_all('tr')):
                        if row_index == 0:
                            continue
                        self.assertEqual(t0_description[row_index - 1], row.find_all('td')[0].text.split(' ')[1])
                        self.assertEqual(
                            t0_suggestion[row_index - 1], row.find_all('td')[1].text.split('`')[1].split(';')[0]
                        )
                    for row_index, row in enumerate(table[1].find_all('tr')):
                        if row_index == 0:
                            continue
                        self.assertEqual(t1_issue[row_index - 1], row.find_all('td')[0].text)
                        self.assertEqual(t1_counts[row_index - 1], row.find_all('td')[1].text)
                        self.assertEqual(t1_elapsed_time[row_index - 1], row.find_all('td')[2].text)
