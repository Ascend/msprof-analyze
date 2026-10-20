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
from msprof_analyze.advisor.dataset.timeline_event_dataset import ComputationAnalysisDataset


class TestFrequencyAdvice(unittest.TestCase):
    TMP_DIR = "./ascend_pt"
    OUTPUT_DIR = "./ascend_pt/ASCEND_PROFILER_OUTPUT"
    DEVICE_DIR = "./ascend_pt/PROF_000001_20240415174447255_OAANHDOMMJMHGIFC/device_0"
    interface = None
    err_interface = None

    @classmethod
    def clear_htmls(cls):
        current_path = os.path.dirname(os.path.abspath(__file__))
        for filename in os.listdir(current_path):
            # 检查文件是否以“att”开头
            if filename.startswith("att"):
                # 构建文件的完整路径
                file_path = os.path.join(current_path, filename)
                # 删除文件
                os.remove(file_path)

    @classmethod
    def get_basic_trace_view(cls):
        # Python pid
        py_pid_data = {"ph": "M", "name": "process_name", "tid": 0, "pid": 1, "args": {"name": "Python"}}
        # ascend pid
        ascend_pid_data = {"ph": "M", "name": "process_name", "tid": 0, "pid": 4, "args": {"name": "Ascend Hardware"}}
        # ascend pid
        cann_pid_data = {"ph": "M", "name": "process_name", "tid": 0, "pid": 5, "args": {"name": "CANN"}}
        # ascend hardware ops
        ah_event1 = {"ph": "X", "name": "Slice1", "ts": "1699529623106750", "dur": 100, "tid": 3, "pid": 4,
                     "args": {"Task Type": "AI_CORE"}}
        ah_event2 = {"ph": "X", "name": "Slice2", "ts": "1699529623106888", "dur": 80, "tid": 3, "pid": 4,
                     "args": {"Task Type": "AI_CORE"}}
        # flow event
        flow_event_s = {"ph": "s", "name": "link1", "id": 1, "tid": 3, "pid": 1, "ts": "200", "args": {}}
        flow_event_e = {"ph": "f", "name": "link1", "id": 1, "tid": 3, "pid": 1, "ts": "1699529623106750", "args": {}}
        return [py_pid_data, ascend_pid_data, cann_pid_data, ah_event1, ah_event2, flow_event_s, flow_event_e]

    @classmethod
    def create_info_json(cls):
        info = {
            "DeviceInfo": [
                {
                    "id": 7,
                    "env_type": 3,
                    "ctrl_cpu_id": "ARMv8_Cortex_A55",
                    "ctrl_cpu_core_num": 1,
                    "ctrl_cpu_endian_little": 1,
                    "ts_cpu_core_num": 0,
                    "ai_cpu_core_num": 6,
                    "ai_core_num": 25,
                    "ai_cpu_core_id": 2,
                    "ai_core_id": 0,
                    "aicpu_occupy_bitmap": 252,
                    "ctrl_cpu": "0",
                    "ai_cpu": "2,3,4,5,6",
                    "aiv_num": 50,
                    "hwts_frequency": "49.999001",
                    "aic_frequency": "1850",
                    "aiv_frequency": "1850"
                }
            ]
        }
        with os.fdopen(os.open(f"{TestFrequencyAdvice.DEVICE_DIR}/info.json.0",
                               os.O_WRONLY | os.O_CREAT, stat.S_IWUSR | stat.S_IRUSR), 'w') as fp:
            fp.write(json.dumps(info))

    @classmethod
    def create_non_a2_trace_view(cls):
        basic_info = cls.get_basic_trace_view()

        # python ops
        py_event1 = {"ph": "X", "cat": "python_function", "name": "aten::slice", "ts": "200", "dur": 100, "tid": 2,
                     "pid": 1,
                     "args": {"Call stack": "/root/test/slice.py(116);\r\n/root/torch/module.py"}}
        py_event2 = {"ph": "X", "cat": "python_function", "name": "slice", "ts": "199", "dur": 200, "tid": 2, "pid": 1,
                     "args": {"Call stack": "/root/test/slice.py(116);\r\n/root/torch/module.py"}}
        raw_data = [
            *basic_info, py_event1, py_event2
        ]
        with os.fdopen(os.open(f"{TestFrequencyAdvice.OUTPUT_DIR}/trace_view.json",
                               os.O_WRONLY | os.O_CREAT, stat.S_IWUSR | stat.S_IRUSR), 'w') as fp:
            fp.write(json.dumps(raw_data))

    @classmethod
    def create_a2_trace_view(cls):
        basic_info = cls.get_basic_trace_view()

        # python ops
        py_event1 = {"name": "AI Core Freq", "ts": "1699529623106000.061", "pid": 682820896, "tid": 0,
                     "args": {"MHz": 1850}, "ph": "C"}
        py_event2 = {"name": "AI Core Freq", "ts": "1699529623106770.541", "pid": 682820896, "tid": 0,
                     "args": {"MHz": 800}, "ph": "C"}
        raw_data = [
            *basic_info, py_event1, py_event2
        ]

        with os.fdopen(os.open(f"{TestFrequencyAdvice.OUTPUT_DIR}/trace_view.json",
                               os.O_WRONLY | os.O_CREAT, stat.S_IWUSR | stat.S_IRUSR), 'w') as fp:
            fp.write(json.dumps(raw_data))

    def setUp(self):
        if os.path.exists(TestFrequencyAdvice.TMP_DIR):
            shutil.rmtree(TestFrequencyAdvice.TMP_DIR)
        if not os.path.exists(TestFrequencyAdvice.TMP_DIR):
            os.makedirs(TestFrequencyAdvice.TMP_DIR)
        if not os.path.exists(TestFrequencyAdvice.OUTPUT_DIR):
            os.makedirs(TestFrequencyAdvice.OUTPUT_DIR)
        if not os.path.exists(TestFrequencyAdvice.DEVICE_DIR):
            os.makedirs(TestFrequencyAdvice.DEVICE_DIR)
        self.clear_htmls()

    def tearDown(self):
        if os.path.exists(TestFrequencyAdvice.TMP_DIR):
            shutil.rmtree(TestFrequencyAdvice.TMP_DIR)
        self.clear_htmls()

    def test_run_should_run_success_when_msprof_not_contain_frequency_data(self):
        self.create_info_json()
        self.create_non_a2_trace_view()
        interface = Interface(profiling_path=self.TMP_DIR)
        dimension = "computation"
        scope = SupportedScopes.FREQ_ANALYSIS
        result = interface.get_result(dimension, scope, render_html=1, output_dict=False, profiling_path=self.TMP_DIR)
        self.assertEqual(0, len(result.data.get("AI Core Frequency", [])))
        result.clear()
        ComputationAnalysisDataset.reset_all_instances()

    def test_run_should_run_success_when_trace_view_contain_frequency_data(self):
        self.create_info_json()
        self.create_a2_trace_view()
        interface = Interface(profiling_path=self.TMP_DIR)
        dimension = "computation"
        scope = SupportedScopes.FREQ_ANALYSIS
        result = interface.get_result(dimension, scope, render_html=1, output_dict=False, profiling_path=self.TMP_DIR)
        self.assertEqual(2, len(result.data.get("AIcore频率", dict()).get("data", [])))
        result.clear()
        ComputationAnalysisDataset.reset_all_instances()
