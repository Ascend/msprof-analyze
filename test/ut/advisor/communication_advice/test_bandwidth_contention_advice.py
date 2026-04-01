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
import shutil
import stat
import json
import csv
import unittest

from msprof_analyze.advisor.interface.interface import Interface
from msprof_analyze.advisor.common.analyzer_scopes import SupportedScopes


class TestBandwidthContentionAdvice(unittest.TestCase):
    TMP_DIR = "./ascend_pt"
    OUTPUT_DIR = "./ascend_pt/ASCEND_PROFILER_OUTPUT"
    interface = None
    err_interface = None

    @classmethod
    def clear_htmls(cls):
        current_path = os.path.dirname(os.path.abspath(__file__))
        for filename in os.listdir(current_path):
            # 检查文件是否以“mstt”开头
            if filename.startswith("mstt"):
                # 构建文件的完整路径
                file_path = os.path.join(current_path, filename)
                # 删除文件
                os.remove(file_path)

    @classmethod
    def get_communication_view(cls):
        data = {"step1": {"collective": {
            "hcom_broadcast__844_1_1@13681369207305868844": {
                "Communication Time Info": {
                    "Start Timestamp(us)": 171317.0,
                    "Elapse Time(ms)": 10.6086,
                    "Transit Time(ms)": 0.00126,
                    "Wait Time(ms)": 0.014939999999999998,
                    "Synchronization Time(ms)": 0.00714,
                    "Idle Time(ms)": 0.044660000000000005,
                    "Wait Time Ratio": 0.9222,
                    "Synchronization Time Ratio": 0.85
                },
                "Communication Bandwidth Info": {
                    "RDMA": {
                        "Transit Size(MB)": 0,
                        "Transit Time(ms)": 0,
                        "Bandwidth(GB/s)": 0,
                        "Large Packet Ratio": 0,
                        "Size Distribution": {}
                    },
                    "HCCS": {
                        "Transit Size(MB)": 0.28575999999999997,
                        "Transit Time(ms)": 1.8620000000000001,
                        "Bandwidth(GB/s)": 13.3151,
                        "Large Packet Ratio": 0.0,
                        "Size Distribution": {
                            "0.004224": [
                                6,
                                0.00736
                            ],
                            "0.003232": [
                                1,
                                0.00126
                            ]
                        }
                    },
                    "PCIE": {
                        "Transit Size(MB)": 0,
                        "Transit Time(ms)": 0,
                        "Bandwidth(GB/s)": 0,
                        "Large Packet Ratio": 0,
                        "Size Distribution": {}
                    },
                    "SDMA": {
                        "Transit Size(MB)": 0.28575999999999997,
                        "Transit Time(ms)": 1.8620000000000001,
                        "Bandwidth(GB/s)": 3.3151,
                        "Large Packet Ratio": 0,
                        "Size Distribution": {}
                    },
                    "SIO": {
                        "Transit Size(MB)": 0,
                        "Transit Time(ms)": 0,
                        "Bandwidth(GB/s)": 0,
                        "Large Packet Ratio": 0,
                        "Size Distribution": {}
                    }
                }
            },
            "hcom_allReduce__844_2_1@13681369207305868844": {
                "Communication Time Info": {
                    "Start Timestamp(us)": 188417.2,
                    "Elapse Time(ms)": 10.9042,
                    "Transit Time(ms)": 1.35236,
                    "Wait Time(ms)": 1.47632,
                    "Synchronization Time(ms)": 1.44524,
                    "Idle Time(ms)": 0.07551999999999981,
                    "Wait Time Ratio": 0.5219,
                    "Synchronization Time Ratio": 0.5166
                },
                "Communication Bandwidth Info": {
                    "RDMA": {
                        "Transit Size(MB)": 0,
                        "Transit Time(ms)": 0,
                        "Bandwidth(GB/s)": 0,
                        "Large Packet Ratio": 0,
                        "Size Distribution": {}
                    },
                    "HCCS": {
                        "Transit Size(MB)": 176.16076799999996,
                        "Transit Time(ms)": 9.55658,
                        "Bandwidth(GB/s)": 18.4335,
                        "Large Packet Ratio": 0.0,
                        "Size Distribution": {
                            "12.582912": [
                                14,
                                9.55658
                            ]
                        }
                    },
                    "PCIE": {
                        "Transit Size(MB)": 0,
                        "Transit Time(ms)": 0,
                        "Bandwidth(GB/s)": 0,
                        "Large Packet Ratio": 0,
                        "Size Distribution": {}
                    },
                    "SDMA": {
                        "Transit Size(MB)": 176.16076799999996,
                        "Transit Time(ms)": 9.55658,
                        "Bandwidth(GB/s)": 18.4335,
                        "Large Packet Ratio": 0,
                        "Size Distribution": {}
                    },
                    "SIO": {
                        "Transit Size(MB)": 0,
                        "Transit Time(ms)": 0,
                        "Bandwidth(GB/s)": 0,
                        "Large Packet Ratio": 0,
                        "Size Distribution": {}
                    }
                }
            },
        }}}
        return data

    @classmethod
    def create_kernel_details(cls):
        # create csv files
        csv_header = ['Step Id', 'Model ID', 'Task ID', 'Stream ID', 'Name', 'Type', 'Accelerator Core',
                      'Start Time(us)',
                      'Duration(us)', 'Wait Time(us)', 'Block Num', 'Mix Block Num', 'Input Shapes', 'Input Data Types',
                      'Input Formats', 'Output Shapes', 'Output Data Types', 'Output Formats', 'Context ID',
                      'aicore_time(us)',
                      'aic_total_cycles', 'aic_mac_ratio', 'aic_mac_int8_ratio', 'aic_cube_fops',
                      'aic_vector_fops',
                      'aiv_time(us)', 'aiv_total_cycles', 'aiv_vec_fp32_ratio', 'aiv_vec_fp16_ratio',
                      'aiv_vec_int32_ratio',
                      'aiv_vec_misc_ratio', 'aiv_cube_fops', 'aiv_vector_fops']
        csv_row1 = [1, 4294967295, 1265, 16, 'MatMul56', 'MatMul', 'AI_CORE', "172317\t", 21.2, 261.56, 9,
                    0,
                    '4,1025', 'INT64', 'FORMAT_ND', '4,1025', 'INT32', 'FORMAT_ND', 'N/A',
                    0, 0, 0, 0, 0, 0,
                    1.77, 29508, 0, 0, 0.0062, 0, 0, 5856]
        csv_row2 = [1, 4294967295, 1265, 16, 'Add2', 'Add', 'AI_VECTOR_CORE', "183317\t", 1.5, 261.56, 9,
                    0,
                    '4,1025', 'INT64', 'FORMAT_ND', '4,1025', 'INT32', 'FORMAT_ND', 'N/A',
                    0, 0, 0, 0, 0, 0,
                    1.77, 29508, 0, 0, 0.0062, 0, 0, 5856]
        csv_row3 = [1, 4294967295, 1265, 16, 'MatMul57', 'MatMul', 'AI_CORE', "189233\t", 3.14, 261.56, 9, 0,
                    '4,1025', 'INT64', 'FORMAT_ND', '4,1025', 'INT32', 'FORMAT_ND', 'N/A',
                    0, 0, 0, 0, 0, 0,
                    1.77, 29508, 0, 0, 0.0062, 0, 0, 5856]
        csv_row4 = [1, 4294967295, 1265, 16, 'Add1', 'Add', 'AI_CORE', "189933\t", 3.14, 261.56, 9, 0,
                    '4,1025', 'INT64', 'FORMAT_ND', '4,1025', 'INT32', 'FORMAT_ND', 'N/A',
                    2.3, 28888, 0.2, 0.1, 0.1, 0.7,
                    0, 0, 0, 0, 0, 0, 0, 0]

        with os.fdopen(os.open(f"{TestBandwidthContentionAdvice.OUTPUT_DIR}/kernel_details.csv",
                               os.O_WRONLY | os.O_CREAT, stat.S_IWUSR | stat.S_IRUSR), 'w', newline='') as fp:
            csv_writer = csv.writer(fp)
            csv_writer.writerow(csv_header)
            csv_writer.writerow(csv_row1)
            csv_writer.writerow(csv_row2)
            csv_writer.writerow(csv_row3)
            csv_writer.writerow(csv_row4)

    @classmethod
    def create_communicaton_json(cls):
        raw_data = cls.get_communication_view()
        with os.fdopen(os.open(f"{TestBandwidthContentionAdvice.OUTPUT_DIR}/communication.json",
                               os.O_WRONLY | os.O_CREAT, stat.S_IWUSR | stat.S_IRUSR), 'w') as fp:
            fp.write(json.dumps(raw_data))

    def tearDown(self):
        if os.path.exists(TestBandwidthContentionAdvice.TMP_DIR):
            shutil.rmtree(TestBandwidthContentionAdvice.TMP_DIR)
        self.clear_htmls()

    def setUp(self):
        if os.path.exists(TestBandwidthContentionAdvice.TMP_DIR):
            shutil.rmtree(TestBandwidthContentionAdvice.TMP_DIR)
        if not os.path.exists(TestBandwidthContentionAdvice.TMP_DIR):
            os.makedirs(TestBandwidthContentionAdvice.TMP_DIR)
        if not os.path.exists(TestBandwidthContentionAdvice.OUTPUT_DIR):
            os.makedirs(TestBandwidthContentionAdvice.OUTPUT_DIR)
        self.clear_htmls()

    def test_run_should_run_success_when_ascend_pt_contain_communication_json(self):
        self.create_communicaton_json()
        self.create_kernel_details()
        interface = Interface(profiling_path=self.TMP_DIR)
        dimension = Interface.COMMUNICATION
        scope = SupportedScopes.BANDWIDTH_CONTENTION_DETECTION
        result = interface.get_result(dimension, scope, render_html=1, output_dict=False, profiling_path=self.TMP_DIR)
        self.assertEqual(2, len(result.data.get("带宽分析", [])))
        self.assertEqual(1, len(result.data.get("带宽分析", []).get('data')))
        result.clear()
