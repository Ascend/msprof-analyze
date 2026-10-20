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
import unittest
from collections import defaultdict
from unittest.mock import patch

from msprof_analyze.compare_tools.compare_backend.compare_bean.origin_data_bean.trace_event_bean import TraceEventBean
from msprof_analyze.compare_tools.compare_backend.profiling_parser.base_profiling_parser import ProfilingResult
from msprof_analyze.compare_tools.compare_backend.profiling_parser.gpu_profiling_parser import GPUProfilingParser
from .test_base_profiling_parser import TestBaseProfilingParser


class TestGpuProfilingParser(unittest.TestCase):
    memory_events = [{"ph": "i", "name": "[memory]", "pid": 1, "tid": 1, "ts": 0,
                      "args": {"Addr": 3, "Bytes": 512, "Total Allocated": 1024}},
                     {"ph": "i", "name": "[memory]", "pid": 1, "tid": 1, "ts": 1,
                      "args": {"Addr": 1, "Bytes": 512, "Total Allocated": 1024}},
                     {"ph": "i", "name": "[memory]", "pid": 1, "tid": 1, "ts": 2,
                      "args": {"Addr": 1, "Bytes": -512, "Total Allocated": 1024}},
                     {"ph": "i", "name": "[memory]", "pid": 1, "tid": 1, "ts": 3,
                      "args": {"Addr": 1, "Bytes": -512, "Total Allocated": 1024}},
                     {"ph": "i", "name": "[memory]", "pid": 1, "tid": 1, "ts": 4,
                      "args": {"Addr": 2, "Bytes": 512, "Total Allocated": 1024}},
                     {"ph": "i", "name": "[memory]", "pid": 1, "tid": 1, "ts": 5,
                      "args": {"Addr": 2, "Bytes": -512, "Total Allocated": 1024}}]
    trace_events = [
        {"ph": "X", "name": "test1", "pid": 1, "tid": 1, "ts": 100, "dur": 1, "cat": "kernel"},
        {"ph": "X", "name": "test2", "pid": 1, "tid": 1, "ts": 97, "dur": 1, "args": {"stream": 3}},
        {"ph": "X", "name": "1htod1", "pid": 1, "tid": 1, "ts": 0, "dur": 1, "cat": "kernel", "args": {"stream": 3}},
        {"ph": "X", "name": "1dtod1", "pid": 1, "tid": 1, "ts": 1, "dur": 1, "cat": "kernel", "args": {"stream": 3}},
        {"ph": "X", "name": "1dtoh1", "pid": 1, "tid": 1, "ts": 2, "dur": 1, "cat": "kernel", "args": {"stream": 3}},
        {"ph": "X", "name": "1memset (device)1", "pid": 1, "tid": 1, "ts": 3, "dur": 1, "cat": "kernel",
         "args": {"stream": 3}},
        {"ph": "X", "name": "ncclkernel1", "pid": 1, "tid": 1, "ts": 4, "dur": 1, "cat": "kernel",
         "args": {"stream": 3}},
        {"ph": "X", "name": "ncclkernel2", "pid": 1, "tid": 1, "ts": 5, "dur": 1, "cat": "kernel",
         "args": {"stream": 3}},
        {"ph": "X", "name": "gemm", "pid": 1, "tid": 1, "ts": 6, "dur": 1, "cat": "kernel", "args": {"stream": 3}},
        {"ph": "X", "name": "fmha_kernel_bwd", "pid": 1, "tid": 1, "ts": 7, "dur": 1, "cat": "kernel",
         "args": {"stream": 3}},
        {"ph": "X", "name": "fmha_kernel_fwd", "pid": 1, "tid": 1, "ts": 8, "dur": 1, "cat": "kernel",
         "args": {"stream": 3}},
        {"ph": "X", "name": "flash_kernel_bwd", "pid": 1, "tid": 1, "ts": 9, "dur": 1, "cat": "kernel",
         "args": {"stream": 3}},
        {"ph": "X", "name": "flash_kernel_fwd", "pid": 1, "tid": 1, "ts": 10, "dur": 1, "cat": "kernel",
         "args": {"stream": 3}},
        {"ph": "X", "name": "other", "pid": 1, "tid": 1, "ts": 11, "dur": 1, "cat": "kernel", "args": {"stream": 3}},
    ]
    memory_event = {"ph": "i", "name": "[memory]", "pid": 1, "tid": 1, "ts": 0,
                    "args": {"Addr": 3, "Bytes": 512, "Total Allocated": 1024, 'Device Id': 1}}
    nccl_event = {"ph": "X", "name": "nccl_reduce", "pid": 1, "tid": 1, "ts": 4, "dur": 1, "cat": "kernel",
                  "args": {"stream": 3}}
    cube_event = {"ph": "X", "name": "gemm", "pid": 1, "tid": 1, "ts": 6, "dur": 1, "cat": "kernel",
                  "args": {"stream": 3}}
    other_event = {"ph": "X", "name": "other", "pid": 1, "tid": 1, "ts": 6, "dur": 1}
    args = TestBaseProfilingParser.args
    path_dict = TestBaseProfilingParser.path_dict

    def test_update_memory_list_when_valid_input(self):
        with patch("msprof_analyze.compare_tools.compare_backend.profiling_parser."
                   "base_profiling_parser.BaseProfilingParser.__init__"), \
                patch("msprof_analyze.compare_tools.compare_backend.profiling_parser."
                      "gpu_profiling_parser.GPUProfilingParser.__init__",
                      return_value=None):
            res = GPUProfilingParser({}, {})
            res._enable_memory_compare = True
            res._memory_events = [TraceEventBean(event) for event in self.memory_events]
            res._result_data = ProfilingResult("GPU")
            res._update_memory_list()
            self.assertEqual(len(res._result_data.memory_list), 3)
            self.assertEqual(res._result_data.memory_list[0].memory_details, ", (1, 2), [duration: 1.0], [size: 0.5]\n")

    def test_calculate_performance_time_when_valid_input(self):
        with patch("msprof_analyze.compare_tools.compare_backend.profiling_parser."
                   "base_profiling_parser.BaseProfilingParser.__init__"), \
                patch("msprof_analyze.compare_tools.compare_backend.profiling_parser."
                      "gpu_profiling_parser.GPUProfilingParser.__init__",
                      return_value=None):
            res = GPUProfilingParser({}, {})
            res._profiling_type = "GPU"
            res._all_kernels = {}
            for event in self.trace_events:
                event_name = event.get("name")
                event_ts = str(event.get("ts"))
                res._all_kernels[event_name + event_ts] = TraceEventBean(event)
            res._result_data = ProfilingResult("GPU")
            res._compute_stream_id = 3
            res._flow_dict = {}
            res._marks = defaultdict(int)
            res._calculate_performance_time()
            self.assertEqual(res._result_data.overall_metrics.e2e_time, 98)
            self.assertEqual(res._result_data.overall_metrics.sdma_time, 0.004)
            self.assertEqual(res._result_data.overall_metrics.sdma_num, 4)
            self.assertEqual(res._result_data.overall_metrics.cube_time, 0.001)
            self.assertEqual(res._result_data.overall_metrics.cube_num, 1)
            self.assertEqual(res._result_data.overall_metrics.vec_time, 0.006)
            self.assertEqual(res._result_data.overall_metrics.vec_num, 6)  # cun yi
            self.assertEqual(res._result_data.overall_metrics.communication_not_overlapped, 2)
            self.assertEqual(res._result_data.overall_metrics.compute_time, 7)

    def test_picking_memory_event_when_valid_input(self):
        with patch("msprof_analyze.compare_tools.compare_backend.profiling_parser."
                   "base_profiling_parser.BaseProfilingParser.__init__"), \
                patch("msprof_analyze.compare_tools.compare_backend.profiling_parser."
                      "gpu_profiling_parser.GPUProfilingParser.__init__",
                      return_value=None):
            res = GPUProfilingParser({}, {})
            res._memory_events = []
            result = res._picking_memory_event(TraceEventBean(self.memory_event))
            self.assertTrue(result)
            result = res._picking_memory_event(TraceEventBean(self.nccl_event))
            self.assertFalse(result)

    def test_is_torch_op_event_when_valid_input(self):
        event_list = [{"cat": "cpu_op"}, {"cat": "user_annotation"}, {"cat": "cuda_runtime"}, {"cat": "operator"}]
        with patch("msprof_analyze.compare_tools.compare_backend.profiling_parser."
                   "base_profiling_parser.BaseProfilingParser.__init__"), \
                patch("msprof_analyze.compare_tools.compare_backend.profiling_parser."
                      "gpu_profiling_parser.GPUProfilingParser.__init__",
                      return_value=None):
            res = GPUProfilingParser({}, {})
            for event in event_list:
                result = res._is_torch_op_event(TraceEventBean(event))
                self.assertTrue(result)
        result = res._is_torch_op_event(TraceEventBean({"cat": "python_function"}))
        self.assertFalse(result)

    def test_is_kernel_event_when_valid_input(self):
        event_list1 = [{"cat": "kernel", "name": "matmul"}, {"cat": "kernel", "name": "nccl_reduce"}]
        event_list2 = [{"cat": "async", "name": "nccl_reduce"}, {"cat": "cpu_op", "name": "aten::to"}]
        with patch("msprof_analyze.compare_tools.compare_backend.profiling_parser."
                   "base_profiling_parser.BaseProfilingParser.__init__"), \
                patch("msprof_analyze.compare_tools.compare_backend.profiling_parser."
                      "gpu_profiling_parser.GPUProfilingParser.__init__",
                      return_value=None):
            res = GPUProfilingParser({}, {})
            for event in event_list1:
                result = res._is_kernel_event(TraceEventBean(event))
                self.assertTrue(result)
            for event in event_list2:
                result = res._is_kernel_event(TraceEventBean(event))
                self.assertFalse(result)

    def test_is_flow_event_when_valid_input(self):
        with patch("msprof_analyze.compare_tools.compare_backend.profiling_parser."
                   "base_profiling_parser.BaseProfilingParser.__init__"), \
                patch("msprof_analyze.compare_tools.compare_backend.profiling_parser."
                      "gpu_profiling_parser.GPUProfilingParser.__init__",
                      return_value=None):
            res = GPUProfilingParser({}, {})
            res._flow_cat = ("async_gpu",)
            result = res._is_flow_event(TraceEventBean({"cat": "async_gpu"}))
            self.assertTrue(result)

    @patch("msprof_analyze.compare_tools.compare_backend.profiling_parser."
           "gpu_profiling_parser.GPUProfilingParser._trace_event_generator")
    def test_infer_compute_stream_id_should_return_compute_stream_id(self, mock_trace_event_generator):
        event = TraceEventBean({})
        event._cat = "kernel"
        event._args = {"stream": 3}
        mock_trace_event_generator.return_value = [event]
        parser = GPUProfilingParser(self.args, self.path_dict)
        self.assertEqual(parser._compute_stream_id, 3)

    @patch("msprof_analyze.compare_tools.compare_backend.profiling_parser."
           "gpu_profiling_parser.GPUProfilingParser._find_bwd_tid")
    @patch("msprof_analyze.compare_tools.compare_backend.profiling_parser."
           "gpu_profiling_parser.GPUProfilingParser._infer_compute_stream_id")
    def test_get_dispatch_func_when_given_different_switches_then_return_func_list(self,
        mock_infer_compute_stream_id, mock_find_bwd_tid):
        mock_infer_compute_stream_id.return_value = 0
        parser = GPUProfilingParser(self.args, self.path_dict)
        self.assertEqual(len(parser._get_dispatch_func()), 6)
