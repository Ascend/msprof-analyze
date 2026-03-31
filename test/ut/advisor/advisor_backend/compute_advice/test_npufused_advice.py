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

from msprof_analyze.advisor.advisor_backend.interface import Interface


class TestComputeAdvice(unittest.TestCase):
    TMP_DIR = "./ascend_pt"
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
        with os.fdopen(os.open(f"{TestComputeAdvice.TMP_DIR}/profiler_info_0.json",
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

        with os.fdopen(os.open(f"{TestComputeAdvice.OUTPUT_DIR}/trace_view.json",
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

        with os.fdopen(os.open(f"{TestComputeAdvice.OUTPUT_DIR}/trace_view.json",
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
                      'aic_total_cycles', 'aic_mac_fp16_ratio', 'aic_mac_int8_ratio', 'aic_cube_fops',
                      'aic_vector_fops',
                      'aiv_time(us)', 'aiv_total_cycles', 'aiv_vec_fp32_ratio', 'aiv_vec_fp16_ratio',
                      'aiv_vec_int32_ratio',
                      'aiv_vec_misc_ratio', 'aiv_cube_fops', 'aiv_vector_fops']
        csv_row1 = [1, 4294967295, 1265, 16, 'Slice1', 'Slice', 'AI_VECTOR_CORE', "1699529623106750\t", 3.14, 261.56, 9,
                    0,
                    '4,1025',
                    'INT64', 'FORMAT_ND', '4,1025', 'INT32', 'FORMAT_ND', 'N/A', 0, 0, 0, 0, 0, 0, 1.77, 29508, 0, 0,
                    0.0062,
                    0, 0, 5856]
        csv_row2 = [1, 4294967295, 1265, 16, 'Slice2', 'Slice', 'AI_VECTOR_CORE', "1699529623106751\t", 3.14, 261.56, 9,
                    0,
                    '4,1025',
                    'INT64', 'FORMAT_ND', '4,1025', 'INT32', 'FORMAT_ND', 'N/A', 0, 0, 0, 0, 0, 0, 1.77, 29508, 0, 0,
                    0.0062,
                    0, 0, 5856]
        csv_row3 = [1, 4294967295, 1265, 16, 'Swish1', 'Swish', 'AI_VECTOR_CORE', "1699529623106752\t", 3.14, 261.56, 9,
                    0,
                    '4,1025',
                    'INT64', 'FORMAT_ND', '4,1025', 'INT32', 'FORMAT_ND', 'N/A', 0, 0, 0, 0, 0, 0, 1.77, 29508, 0, 0,
                    0.0062,
                    0, 0, 5856]
        csv_row4 = [1, 4294967295, 1265, 16, 'Mul1', 'Mul', 'AI_VECTOR_CORE', "1699529623106753\t", 3.14, 261.56, 9, 0,
                    '4,1025',
                    'INT64', 'FORMAT_ND', '4,1025', 'INT32', 'FORMAT_ND', 'N/A', 0, 0, 0, 0, 0, 0, 1.77, 29508, 0, 0,
                    0.0062,
                    0, 0, 5856]
        csv_row5 = [1, 4294967295, 1265, 16, 'Add1', 'Add', 'AI_VECTOR_CORE', "1699529623106754\t", 3.14, 261.56, 9, 0,
                    '4,1025',
                    'INT64', 'FORMAT_ND', '4,1025', 'INT32', 'FORMAT_ND', 'N/A', 0, 0, 0, 0, 0, 0, 1.77, 29508, 0, 0,
                    0.0062,
                    0, 0, 5856]
        with os.fdopen(os.open(f"{TestComputeAdvice.OUTPUT_DIR}/kernel_details.csv",
                               os.O_WRONLY | os.O_CREAT, stat.S_IWUSR | stat.S_IRUSR), 'w') as fp:
            csv_writer = csv.writer(fp)
            csv_writer.writerow(csv_header)
            csv_writer.writerow(csv_row1)
            csv_writer.writerow(csv_row2)
            csv_writer.writerow(csv_row3)
            csv_writer.writerow(csv_row4)
            csv_writer.writerow(csv_row5)

    def setUp(self):
        if os.path.exists(TestComputeAdvice.TMP_DIR):
            shutil.rmtree(TestComputeAdvice.TMP_DIR)
        if not os.path.exists(TestComputeAdvice.TMP_DIR):
            os.makedirs(TestComputeAdvice.TMP_DIR)
        if not os.path.exists(TestComputeAdvice.OUTPUT_DIR):
            os.makedirs(TestComputeAdvice.OUTPUT_DIR)

    def tearDown(self):
        if os.path.exists(TestComputeAdvice.TMP_DIR):
            shutil.rmtree(TestComputeAdvice.TMP_DIR)

    def test_run_should_return_empty_when_ascend_pt_path_not_exist(self):
        interface = Interface("")
        data = interface.get_data('compute', 'npu_fused')
        self.assertEqual(0, len(data['advice']))
        self.assertEqual(0, len(data['data']))

    def test_run_should_return_empty_when_csv_and_json_not_exist(self):
        interface = Interface(self.TMP_DIR)
        data = interface.get_data('compute', 'npu_fused')
        self.assertEqual(0, len(data['advice']))
        self.assertEqual(0, len(data['data']))

    def test_run_should_return_advice_without_callstack_when_json_not_exist(self):
        self.create_kernel_details()
        interface = Interface(self.TMP_DIR)
        data = interface.get_data('compute', 'npu_fused')
        res = ".py" in data['advice']
        self.assertFalse(res)
        self.assertEqual(1, len(data['data']))

    def test_run_should_return_1_fused_op_and_its_callstack_when_json_is_in_old_version(self):
        self.create_profiler_info_json()
        self.create_kernel_details()
        self.create_old_version_trace_view()
        interface = Interface(self.TMP_DIR)
        data = interface.get_data('compute', 'npu_fused')
        res = ".py" in data['advice']
        self.assertTrue(res)
        self.assertEqual(1, len(data['data']))
        self.assertEqual(1, len(data['data']['custom code']))
        self.assertEqual(2, data['data']['custom code'].iloc[0].count("py"))

    def test_run_should_return_1_fused_op_and_its_callstack_when_json_is_in_new_version(self):
        self.create_profiler_info_json()
        self.create_kernel_details()
        self.create_new_version_trace_view()
        interface = Interface(self.TMP_DIR)
        data = interface.get_data('compute', 'npu_fused')
        res = ".py" in data['advice']
        self.assertTrue(res)
        self.assertEqual(1, len(data['data']))
        self.assertEqual(1, len(data['data']['custom code']))
        self.assertEqual(2, data['data']['custom code'].iloc[0].count("py"))
