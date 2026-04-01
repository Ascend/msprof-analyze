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
import json
import os
import shutil
import stat
import csv
import unittest
from unittest.mock import patch

from msprof_analyze.advisor.advisor_backend.interface import Interface
from msprof_analyze.advisor.advisor_backend.compute_advice.npu_slow_advice import NpuSlowAdvice


class TestNpuSlowAdvice(unittest.TestCase):
    ASCEND_PT_DIR = "./ascend_pt"
    OUTPUT_DIR = "./ascend_pt/ASCEND_PROFILER_OUTPUT"
    interface = None
    err_interface = None

    @classmethod
    def get_basic_trace_view(cls):
        # Python pid
        py_pid_data = {"ph": "M", "name": "process_name", "tid": 0, "pid": 1, "args": {"name": "Python"}}
        # ascend pid
        ascend_pid_data = {"ph": "M", "name": "process_name", "tid": 0, "pid": 4, "args": {"name": "Ascend Hardware"}}
        # ascend pid
        cann_pid_data = {"ph": "M", "name": "process_name", "tid": 0, "pid": 5, "args": {"name": "CANN"}}
        # ascend hardware ops
        ah_event1 = {"ph": "X", "name": "Slice1", "ts": "1699529623106750", "dur": 100, "tid": 3, "pid": 4, "args": {}}
        ah_event2 = {"ph": "X", "name": "Slice2", "ts": "1699529623106751", "dur": 80, "tid": 3, "pid": 4, "args": {}}
        # flow event
        flow_event_s = {"ph": "s", "name": "link1", "id": 1, "tid": 3, "pid": 1, "ts": "200", "args": {}}
        flow_event_e = {"ph": "f", "name": "link1", "id": 1, "tid": 3, "pid": 1, "ts": "1699529623106750", "args": {}}
        return [py_pid_data, ascend_pid_data, cann_pid_data, ah_event1, ah_event2, flow_event_s, flow_event_e]

    @classmethod
    def create_profiler_info_json(cls):
        info = {
            "config": {
                "common_config": {
                    "with_stack": True,
                    "activities": ["ProfilerActivity.CPU", "ProfilerActivity.NPU"]
                }
            }
        }
        with os.fdopen(os.open(f"{TestNpuSlowAdvice.ASCEND_PT_DIR}/profiler_info_0.json",
                               os.O_WRONLY | os.O_CREAT, stat.S_IWUSR | stat.S_IRUSR), 'w') as fp:
            fp.write(json.dumps(info))

    @classmethod
    def create_old_version_trace_view(cls):
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

        with os.fdopen(os.open(f"{TestNpuSlowAdvice.OUTPUT_DIR}/trace_view.json",
                               os.O_WRONLY | os.O_CREAT, stat.S_IWUSR | stat.S_IRUSR), 'w') as fp:
            fp.write(json.dumps(raw_data))

    @classmethod
    def create_new_version_trace_view(cls):
        basic_info = cls.get_basic_trace_view()
        # python ops
        py_event1 = {"ph": "X", "name": "aten::slice", "ts": "200", "dur": 100, "tid": 2, "pid": 1, "args": {}}
        py_event2 = {"ph": "X", "name": "slice", "ts": "199", "dur": 105, "tid": 2, "pid": 1, "args": {}}
        py_event3 = {"ph": "X", "cat": "python_function", "name": "/root/test/slice.py(116)", "ts": "198", "dur": 120,
                     "tid": 2, "pid": 1,
                     "args": {}}
        py_event4 = {"ph": "X", "cat": "python_function", "name": "/root/torch/module.py", "ts": "197", "dur": 150,
                     "tid": 2, "pid": 1, "args": {}}

        raw_data = [
            *basic_info, py_event1, py_event2, py_event3, py_event4
        ]

        with os.fdopen(os.open(f"{TestNpuSlowAdvice.OUTPUT_DIR}/trace_view.json",
                               os.O_WRONLY | os.O_CREAT, stat.S_IWUSR | stat.S_IRUSR), 'w') as fp:
            fp.write(json.dumps(raw_data))

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
        # RED: size is 0.0492 MB, throughput is 2.32 GB/s, task_duration is 21.2us
        csv_row1 = [1, 4294967295, 1265, 16, 'Slice1', 'Slice', 'AI_VECTOR_CORE', "1699529623106750\t", 21.2, 261.56, 9,
                    0,
                    '4,1025', 'INT64', 'FORMAT_ND', '4,1025', 'INT32', 'FORMAT_ND', 'N/A',
                    0, 0, 0, 0, 0, 0,
                    1.77, 29508, 0, 0, 0.0062, 0, 0, 5856]
        # YELLOW, size is 0.0492 MB, throughput is 984 GB/s, task_duration is 0.05us
        csv_row2 = [1, 4294967295, 1265, 16, 'Slice2', 'Slice', 'AI_VECTOR_CORE', "1699529623106751\t", 0.05, 261.56, 9,
                    0,
                    '4,1025', 'INT64', 'FORMAT_ND', '4,1025', 'INT32', 'FORMAT_ND', 'N/A',
                    0, 0, 0, 0, 0, 0,
                    1.77, 29508, 0, 0, 0.0062, 0, 0, 5856]
        # WHITE, AI_CPU
        csv_row3 = [1, 4294967295, 1265, 16, 'Swish1', 'Swish', 'AI_CPU', "1699529623106752\t", 3.14, 261.56, 9,
                    0,
                    '4,1025', 'INT64', 'FORMAT_ND', '4,1025', 'INT32', 'FORMAT_ND', 'N/A',
                    'N/A', 'N/A', 'N/A', 'N/A', 'N/A', 'N/A',
                    'N/A', 'N/A', 'N/A', 'N/A', 'N/A', 'N/A', 'N/A', 'N/A']
        # GREEN, size is 0.0492 MB, throughput is 15.67 GB/s, task_duration  is  3.14us
        csv_row4 = [1, 4294967295, 1265, 16, 'Mul1', 'Mul', 'AI_VECTOR_CORE', "1699529623106753\t", 3.14, 261.56, 9, 0,
                    '4,1025', 'INT64', 'FORMAT_ND', '4,1025', 'INT32', 'FORMAT_ND', 'N/A',
                    0, 0, 0, 0, 0, 0,
                    1.77, 29508, 0, 0, 0.0062, 0, 0, 5856]
        # RED, aic_mac_ratio is 0.2
        csv_row5 = [1, 4294967295, 1265, 16, 'Add1', 'Add', 'AI_CORE', "1699529623106754\t", 3.14, 261.56, 9, 0,
                    '4,1025', 'INT64', 'FORMAT_ND', '4,1025', 'INT32', 'FORMAT_ND', 'N/A',
                    2.3, 28888, 0.2, 0.1, 0.1, 0.7,
                    0, 0, 0, 0, 0, 0, 0, 0]
        # GREEN, aic_mac_ratio is 0.85
        csv_row6 = [1, 4294967295, 1265, 16, 'Add1', 'Add', 'AI_CORE', "1699529623106754\t", 3.14, 261.56, 9, 0,
                    '4,1025', 'INT64', 'FORMAT_ND', '4,1025', 'INT32', 'FORMAT_ND', 'N/A',
                    2.3, 38888, 0.85, 0.1, 0.1, 0.7,
                    0, 0, 0, 0, 0, 0, 0, 0]
        # YELLOW, aic_mac_ratio is 0.64
        csv_row7 = [1, 4294967295, 1265, 16, 'Add1', 'Add', 'AI_CORE', "1699529623106754\t", 3.14, 261.56, 9, 0,
                    '4,1025', 'INT64', 'FORMAT_ND', '4,1025', 'INT32', 'FORMAT_ND', 'N/A',
                    2.3, 48888, 0.64, 0.1, 0.1, 0.7,
                    0, 0, 0, 0, 0, 0, 0, 0]
        # WHITE, MIX_AIC
        csv_row8 = [1, 4294967295, 1265, 16, 'Slice2', 'Slice', 'MIX_AIC', "1699529623106751\t", 0.05, 261.56, 9,
                    0,
                    '4,1025', 'INT64', 'FORMAT_ND', '4,1025', 'INT32', 'FORMAT_ND', 'N/A',
                    2.3, 28888, 0.4, 0.1, 0.1, 0.7,
                    1.77, 29508, 0, 0, 0.0062, 0, 0, 5856]
        # WHITE, MIX_AIV
        csv_row9 = [1, 4294967295, 1265, 16, 'Slice2', 'Slice', 'MIX_AIV', "1699529623106751\t", 0.05, 261.56, 9,
                    0,
                    '4,1025', 'INT64', 'FORMAT_ND', '4,1025', 'INT32', 'FORMAT_ND', 'N/A',
                    2.3, 28888, 0.4, 0.1, 0.1, 0.7,
                    1.77, 29508, 0, 0, 0.0062, 0, 0, 5856]
        with os.fdopen(os.open(f"{TestNpuSlowAdvice.OUTPUT_DIR}/kernel_details.csv",
                               os.O_WRONLY | os.O_CREAT, stat.S_IWUSR | stat.S_IRUSR), 'w') as fp:
            csv_writer = csv.writer(fp)
            csv_writer.writerow(csv_header)
            csv_writer.writerow(csv_row1)
            csv_writer.writerow(csv_row2)
            csv_writer.writerow(csv_row3)
            csv_writer.writerow(csv_row4)
            csv_writer.writerow(csv_row5)
            csv_writer.writerow(csv_row6)
            csv_writer.writerow(csv_row7)
            csv_writer.writerow(csv_row8)
            csv_writer.writerow(csv_row9)

    def setUp(self):
        if os.path.exists(TestNpuSlowAdvice.ASCEND_PT_DIR):
            shutil.rmtree(TestNpuSlowAdvice.ASCEND_PT_DIR)
        if not os.path.exists(TestNpuSlowAdvice.ASCEND_PT_DIR):
            os.makedirs(TestNpuSlowAdvice.ASCEND_PT_DIR)
        if not os.path.exists(TestNpuSlowAdvice.OUTPUT_DIR):
            os.makedirs(TestNpuSlowAdvice.OUTPUT_DIR)

    def tearDown(self):
        if os.path.exists(TestNpuSlowAdvice.ASCEND_PT_DIR):
            shutil.rmtree(TestNpuSlowAdvice.ASCEND_PT_DIR)

    def test_run_should_return_empty_when_ascend_pt_path_not_exist(self):
        interface = Interface("")
        data = interface.get_data('compute', 'npu_slow')
        self.assertEqual(0, len(data))

    def test_run_should_return_empty_when_there_is_no_kernel_details(self):
        interface = Interface(self.ASCEND_PT_DIR)
        data = interface.get_data('compute', 'npu_slow')
        self.assertEqual(0, len(data))

    def test_run_should_return_7_data_without_call_stack_when_json_not_exist(self):
        self.create_kernel_details()
        interface = Interface(self.ASCEND_PT_DIR)
        data = interface.get_data('compute', 'npu_slow')
        call_stack = NpuSlowAdvice(self.ASCEND_PT_DIR).get_call_stack(data, index_id=0, ts_col="Start Time(us)")
        self.assertEqual(9, len(data))
        self.assertEqual("", call_stack)

    @patch('msprof_analyze.prof_common.path_manager.PathManager.check_output_directory_path')
    @patch('msprof_analyze.prof_common.path_manager.PathManager.check_input_file_path')
    def test_run_should_return_7_data_with_call_stack_when_new_trace_view_exists(self, mock_check_input_file_path,
                                                                                 mock_check_output_directory_path):
        self.create_profiler_info_json()
        self.create_kernel_details()
        self.create_new_version_trace_view()
        interface = Interface(self.ASCEND_PT_DIR)
        data = interface.get_data('compute', 'npu_slow')
        slow_op_data = data[data["color"] == "RED"]
        NpuSlowAdvice.save_to_excel(data, file_path=os.path.join(self.ASCEND_PT_DIR, "slow_op.xlsx"))
        call_stack = NpuSlowAdvice(self.ASCEND_PT_DIR).get_call_stack(data, index_id=0, ts_col="Start Time(us)")
        self.assertEqual(9, len(data))
        self.assertEqual(2, len(slow_op_data))
        call_stack_res = "/root/torch/module.py\n" \
                         "/root/test/slice.py(116)"
        self.assertEqual(call_stack_res, call_stack)

    @patch('msprof_analyze.prof_common.path_manager.PathManager.check_output_directory_path')
    @patch('msprof_analyze.prof_common.path_manager.PathManager.check_input_file_path')
    def test_run_should_return_7_data_with_call_stack_when_old_trace_view_exists(self, mock_check_input_file_path,
                                                                                 mock_check_output_directory_path):
        self.create_profiler_info_json()
        self.create_kernel_details()
        self.create_old_version_trace_view()
        interface = Interface(self.ASCEND_PT_DIR)
        data = interface.get_data('compute', 'npu_slow')
        slow_op_data = data[data["color"] == "RED"]
        NpuSlowAdvice.save_to_excel(data, file_path=os.path.join(self.ASCEND_PT_DIR, "slow_op.xlsx"))
        call_stack = NpuSlowAdvice(self.ASCEND_PT_DIR).get_call_stack(data, index_id=0, ts_col="Start Time(us)")
        self.assertEqual(9, len(data))
        self.assertEqual(2, len(slow_op_data))
        call_stack_res = "/root/test/slice.py(116)\n\r\n" \
                         "/root/torch/module.py"
        self.assertEqual(call_stack_res, call_stack)
