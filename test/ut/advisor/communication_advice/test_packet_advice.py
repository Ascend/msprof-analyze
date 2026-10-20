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
import json
import unittest

from msprof_analyze.advisor.interface.interface import Interface
from msprof_analyze.advisor.common.analyzer_scopes import SupportedScopes


class TestPacketAdvice(unittest.TestCase):
    TMP_DIR = "./ascend_pt"
    OUTPUT_DIR = "./ascend_pt/ASCEND_PROFILER_OUTPUT"
    interface = None
    err_interface = None

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

    @classmethod
    def get_communication_view(cls):
        data = {"step1": {"collective": {
            "hcom_broadcast__844_1_1@13681369207305868844": {
                "Communication Time Info": {
                    "Start Timestamp(us)": 1713174287407957.0,
                    "Elapse Time(ms)": 0.06086,
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
                        "Transit Size(MB)": 0.028575999999999997,
                        "Transit Time(ms)": 0.008620000000000001,
                        "Bandwidth(GB/s)": 3.3151,
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
                        "Transit Size(MB)": 0.028575999999999997,
                        "Transit Time(ms)": 0.008620000000000001,
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
                    "Start Timestamp(us)": 1713174287432401.2,
                    "Elapse Time(ms)": 2.9042,
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
    def create_communicaton_json(cls):
        raw_data = cls.get_communication_view()
        with os.fdopen(os.open(f"{TestPacketAdvice.OUTPUT_DIR}/communication.json",
                               os.O_WRONLY | os.O_CREAT, stat.S_IWUSR | stat.S_IRUSR), 'w') as fp:
            fp.write(json.dumps(raw_data))

    def tearDown(self):
        if os.path.exists(TestPacketAdvice.TMP_DIR):
            shutil.rmtree(TestPacketAdvice.TMP_DIR)
        self.clear_htmls()

    def setUp(self):
        if os.path.exists(TestPacketAdvice.TMP_DIR):
            shutil.rmtree(TestPacketAdvice.TMP_DIR)
        if not os.path.exists(TestPacketAdvice.TMP_DIR):
            os.makedirs(TestPacketAdvice.TMP_DIR)
        if not os.path.exists(TestPacketAdvice.OUTPUT_DIR):
            os.makedirs(TestPacketAdvice.OUTPUT_DIR)
        self.clear_htmls()

    def test_run_should_run_success_when_ascend_pt_contain_communication_json(self):
        self.create_communicaton_json()
        interface = Interface(profiling_path=self.TMP_DIR)
        dimension = Interface.COMMUNICATION
        scope = SupportedScopes.PACKET
        result = interface.get_result(dimension, scope, render_html=1, output_dict=False, profiling_path=self.TMP_DIR)
        self.assertEqual(2, len(result.data.get("包分析", [])))
        self.assertEqual(1, len(result.data.get("包分析", []).get('data')))
        result.clear()
