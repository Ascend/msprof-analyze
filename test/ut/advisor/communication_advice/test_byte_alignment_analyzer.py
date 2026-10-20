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


class TestByteAlignmentAnalyzer(unittest.TestCase):
    TMP_DIR = "./TestByteAlignmentAnalyzer/ascend_pt"
    OUTPUT_DIR = "./TestByteAlignmentAnalyzer/ascend_pt/ASCEND_PROFILER_OUTPUT"
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
    def create_trace_view(cls):
        # Python pid
        py_pid_data = {"ph": "M", "name": "process_name", "tid": 0, "pid": 1, "args": {"name": "Python"}}
        # ascend pid
        ascend_pid_data = {"ph": "M", "name": "process_name", "tid": 0, "pid": 4, "args": {"name": "Ascend Hardware"}}
        # ascend pid
        cann_pid_data = {"ph": "M", "name": "process_name", "tid": 0, "pid": 5, "args": {"name": "HCCL"}}
        # hccl ops
        hccl_event1 = {
            "name": "hcom_broadcast__661_0_1", "pid": 5, "tid": 0, "ts": "1723545784535521.354",
            "dur": 40.3, "args": {"connection_id": 64349, "model id": 4294967295, "data_type": "INT64",
                                  "alg_type": "RING-RING", "count": 256}, "ph": "X"
        }
        # python ops
        mem_event1 = {
            "name": "Memcpy", "pid": 5, "tid": 1, "ts": "1723545784535549.654", "dur": 1.26,
            "args": {
                "notify_id": "18446744073709551615", "duration estimated(us)": 0.6530569948186529,
                "stream id": 5, "task id": 8342, "context id": 15, "task type": "Memcpy", "src rank": 0,
                "dst rank": 1, "transport type": "SDMA", "size(Byte)": 3024, "data type": "INVALID_TYPE",
                "link type": "HCCS", "bandwidth(GB/s)": 0.8126984126984127, "model id": 4294967295
            }, "ph": "X"
        }
        hccl_event2 = {
            "name": "hcom_broadcast__661_1_1", "pid": 5, "tid": 0, "ts": "1723545784535812.974",
            "dur": 38.18, "args": {
                "connection_id": 64366, "model id": 4294967295, "data_type": "INT64",
                "alg_type": "RING-RING", "count": 256}, "ph": "X"
        }
        reduce_event2 = {
            "name": "Reduce_inline", "pid": 5, "tid": 1, "ts": "1723545784535814.854", "dur": 0.6,
            "args": {
                "notify_id": "18446744073709551615", "duration estimated(us)": 0.7061139896373057,
                "stream id": 5, "task id": 8346, "context id": 1, "task type": "Reduce_inline",
                "src rank": 0, "dst rank": 0, "transport type": "SDMA", "size(Byte)": 3048,
                "data type": "INVALID_TYPE", "link type": "HCCS",
                "bandwidth(GB/s)": 3.4133333333333336, "model id": 4294967295
            }, "ph": "X"
        }
        hccl_event3 = {
            "name": "hcom_broadcast__661_2_1", "pid": 5, "tid": 0, "ts": "1723545784536062.654",
            "dur": 39.06, "args": {
                "connection_id": 64398, "model id": 4294967295, "data_type": "FP32", "alg_type": "RING-RING",
                "count": 256
            }, "ph": "X"
        }
        mem_event2 = {
            "name": "Memcpy", "pid": 5, "tid": 1, "ts": "1723545784536090.214", "dur": 1.26,
            "args": {
                "notify_id": "18446744073709551615", "duration estimated(us)": 0.6265284974093264,
                "stream id": 5, "task id": 8350, "context id": 15, "task type": "Memcpy", "src rank": 0,
                "dst rank": 1, "transport type": "SDMA", "size(Byte)": 512, "data type": "INVALID_TYPE",
                "link type": "PCIE", "bandwidth(GB/s)": 0.40634920634920635, "model id": 4294967295
            }, "ph": "X"
        }
        reduce_event3 = {
            "name": "Reduce_inline", "pid": 5, "tid": 1, "ts": "1723545784536309.474", "dur": 0.58,
            "args": {
                "notify_id": "18446744073709551615", "duration estimated(us)": 0.7061139896373057,
                "stream id": 5, "task id": 8354, "context id": 1, "task type": "Reduce_inline",
                "src rank": 0, "dst rank": 0, "transport type": "SDMA", "size(Byte)": 3048,
                "data type": "INVALID_TYPE", "link type": "HCCS",
                "bandwidth(GB/s)": 3.5310344827586206, "model id": 4294967295
            }, "ph": "X"
        }
        raw_data = [
            py_pid_data, ascend_pid_data, cann_pid_data, hccl_event1, mem_event1, hccl_event2, reduce_event2,
            hccl_event3, mem_event2, reduce_event3
        ]
        with os.fdopen(os.open(f"{TestByteAlignmentAnalyzer.OUTPUT_DIR}/trace_view.json",
                               os.O_WRONLY | os.O_CREAT, stat.S_IWUSR | stat.S_IRUSR), 'w') as fp:
            fp.write(json.dumps(raw_data))

    def setUp(self):
        if os.path.exists(TestByteAlignmentAnalyzer.TMP_DIR):
            shutil.rmtree(TestByteAlignmentAnalyzer.TMP_DIR)
        if not os.path.exists(TestByteAlignmentAnalyzer.TMP_DIR):
            os.makedirs(TestByteAlignmentAnalyzer.TMP_DIR)
        if not os.path.exists(TestByteAlignmentAnalyzer.OUTPUT_DIR):
            os.makedirs(TestByteAlignmentAnalyzer.OUTPUT_DIR)
        self.clear_htmls()

    def tearDown(self):
        if os.path.exists(TestByteAlignmentAnalyzer.TMP_DIR):
            shutil.rmtree(TestByteAlignmentAnalyzer.TMP_DIR)
        self.clear_htmls()

    def test_run_should_run_success_when_communication_ops_not_aligned(self):
        self.create_trace_view()
        interface = Interface(profiling_path=self.TMP_DIR)
        dimension = Interface.COMMUNICATION
        scope = SupportedScopes.BYTE_ALIGNMENT_DETECTION
        result = interface.get_result(dimension, scope, render_html=1, output_dict=False, profiling_path=self.TMP_DIR)
        self.assertEqual(2, len(result.data.get("字节对齐分析", [])))
        self.assertEqual(3, len(result.data.get("字节对齐分析", []).get('data')))
        result.clear()
