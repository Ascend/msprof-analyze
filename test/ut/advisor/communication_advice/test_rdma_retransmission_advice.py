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


class TestRdmaAdvice(unittest.TestCase):
    TMP_DIR = "./tmp/"
    OUTPUT_DIR = "./tmp/cluster_analysis_output"
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
    def get_cluster_communication_view(cls):
        data = {"p2p": {"step1": {
            "hcom_broadcast__844_0_1@13681369207305868844": {
                "0": {
                    "Communication Time Info": {
                        "Start Timestamp(us)": 1713174287354248.0,
                        "Elapse Time(ms)": 4688,
                        "Transit Time(ms)": 0,
                        "Wait Time(ms)": 0.01162,
                        "Synchronization Time(ms)": 0.01162,
                        "Idle Time(ms)": 39.0606,
                        "Wait Time Ratio": 1.0,
                        "Synchronization Time Ratio": 1.0
                    },
                    "Communication Bandwidth Info": {
                        "RDMA": {
                            "Transit Size(MB)": 80,
                            "Transit Time(ms)": 4600,
                            "Bandwidth(GB/s)": 0.003,
                            "Large Packet Ratio": 0,
                            "Size Distribution": {}
                        },
                        "HCCS": {
                            "Transit Size(MB)": 0,
                            "Transit Time(ms)": 0,
                            "Bandwidth(GB/s)": 0,
                            "Large Packet Ratio": 0,
                            "Size Distribution": {}
                        },
                        "PCIE": {
                            "Transit Size(MB)": 0,
                            "Transit Time(ms)": 0,
                            "Bandwidth(GB/s)": 0,
                            "Large Packet Ratio": 0,
                            "Size Distribution": {}
                        },
                        "SDMA": {
                            "Transit Size(MB)": 0,
                            "Transit Time(ms)": 0,
                            "Bandwidth(GB/s)": 0,
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
                "16": {
                    "Communication Time Info": {
                        "Start Timestamp(us)": 1713174287186619.8,
                        "Elapse Time(ms)": 4788,
                        "Transit Time(ms)": 0.0013,
                        "Wait Time(ms)": 39.037240000000004,
                        "Synchronization Time(ms)": 39.03034,
                        "Idle Time(ms)": 167.66008000000002,
                        "Wait Time Ratio": 1.0,
                        "Synchronization Time Ratio": 1.0
                    },
                    "Communication Bandwidth Info": {
                        "RDMA": {
                            "Transit Size(MB)": 80,
                            "Transit Time(ms)": 4700,
                            "Bandwidth(GB/s)": 0.0033,
                            "Large Packet Ratio": 0,
                            "Size Distribution": {}
                        },
                        "HCCS": {
                            "Transit Size(MB)": 4e-05,
                            "Transit Time(ms)": 0.0013,
                            "Bandwidth(GB/s)": 0.0308,
                            "Large Packet Ratio": 0.0,
                            "Size Distribution": {
                                "4e-05": [
                                    1,
                                    0.0013
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
                            "Transit Size(MB)": 4e-05,
                            "Transit Time(ms)": 0.0013,
                            "Bandwidth(GB/s)": 0.0308,
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
            }
        }}}
        return data

    @classmethod
    def create_communicaton_json(cls):
        raw_data = cls.get_cluster_communication_view()
        with os.fdopen(os.open(f"{TestRdmaAdvice.OUTPUT_DIR}/cluster_communication.json",
                               os.O_WRONLY | os.O_CREAT, stat.S_IWUSR | stat.S_IRUSR), 'w') as fp:
            fp.write(json.dumps(raw_data))

    def tearDown(self):
        if os.path.exists(TestRdmaAdvice.TMP_DIR):
            shutil.rmtree(TestRdmaAdvice.TMP_DIR)
        if os.path.exists(TestRdmaAdvice.OUTPUT_DIR):
            shutil.rmtree(TestRdmaAdvice.OUTPUT_DIR)
        self.clear_htmls()

    def setUp(self):
        if os.path.exists(TestRdmaAdvice.TMP_DIR):
            shutil.rmtree(TestRdmaAdvice.TMP_DIR)
        if not os.path.exists(TestRdmaAdvice.TMP_DIR):
            os.makedirs(TestRdmaAdvice.TMP_DIR)
        if not os.path.exists(TestRdmaAdvice.OUTPUT_DIR):
            os.makedirs((TestRdmaAdvice.OUTPUT_DIR))
        self.clear_htmls()

    def test_run_should_run_success_when_contain_cluster_communication_json(self):
        self.create_communicaton_json()
        interface = Interface(profiling_path=self.TMP_DIR)
        dimension = Interface.COMMUNICATION
        scope = SupportedScopes.COMMUNICATION_RETRANSMISSION_DETECTION
        result = interface.get_result(dimension, scope, render_html=1, output_dict=False, profiling_path=self.TMP_DIR)
        self.assertEqual(2, len(result.data.get("通信重传分析", [])))
        self.assertEqual(2, len(result.data.get("通信重传分析", []).get('data')))
        result.clear()
