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
from unittest.mock import patch, MagicMock

from msprof_analyze.compare_tools.compare_backend.compare_bean.origin_data_bean.operator_memory_bean \
    import OperatorMemoryBean
from msprof_analyze.compare_tools.compare_backend.compare_bean.origin_data_bean.trace_event_bean import TraceEventBean
from msprof_analyze.compare_tools.compare_backend.compare_bean.origin_data_bean.kernel_details_bean \
    import KernelDetailsBean
from msprof_analyze.compare_tools.compare_backend.compare_bean.origin_data_bean.memory_record_bean \
    import MemoryRecordBean
from msprof_analyze.compare_tools.compare_backend.compare_bean.origin_data_bean.op_stastic_bean \
    import OpStatisticBean
from msprof_analyze.compare_tools.compare_backend.profiling_parser.base_profiling_parser import ProfilingResult
from msprof_analyze.compare_tools.compare_backend.profiling_parser.npu_profiling_parser import NPUProfilingParser
from msprof_analyze.prof_common.constant import Constant


class TestNPUProfilingParser(unittest.TestCase):
    comm_events = [{"ph": "X", "name": "hccl_allreduce", "pid": 7, "tid": 3, "ts": 1, "dur": 2}]
    task_events = [{"ph": "X", "name": "notify_wait", "pid": 7, "tid": 1, "ts": 2, "dur": 1},
                   {"ph": "X", "name": "notify_wait", "pid": 7, "tid": 1, "ts": 5, "dur": 1}]
    dequeue_events = [{"ph": "X", "name": "test1", "pid": 1, "tid": 1, "ts": 1, "dur": 5, "cat": "dequeue"}]
    enqueue_events = [{"ph": "X", "name": "test1", "pid": 1, "tid": 1, "ts": 1, "dur": 5, "cat": "enqueue"}]
    overlap_events = [{"ph": "X", "name": "computing", "pid": 9, "tid": 3, "ts": 1, "dur": 2}]
    meta_events = [{"ph": "M", "name": "process_name", "pid": 7, "tid": 3, "args": {"name": "HCCL"}},
                   {"ph": "M", "name": "process_name", "pid": 9, "tid": 3, "args": {"name": "Overlap Analysis"}},
                   {"ph": "M", "name": "process_name", "pid": 5, "tid": 3, "args": {"name": "Ascend Hardware"}},
                   {"ph": "M", "name": "thread_name", "pid": 7, "tid": 3, "args": {"name": "Communication"}},
                   {"ph": "M", "name": "thread_sort_index", "pid": 7, "tid": 3, "args": {"sort_index": 0}}]

    @staticmethod
    def _create_mock_parser():
        """Helper method to create a mock NPUProfilingParser instance"""
        with patch("msprof_analyze.compare_tools.compare_backend.profiling_parser."
                   "base_profiling_parser.BaseProfilingParser.__init__"), \
                patch("msprof_analyze.compare_tools.compare_backend.profiling_parser."
                      "npu_profiling_parser.NPUProfilingParser.__init__",
                      return_value=None):
            return NPUProfilingParser({}, {})

    def test_update_memory_list_when_invalid_path(self):
        res = self._create_mock_parser()
        res._operator_memory_path = ""
        res._path_level = ''
        res._update_memory_list()

    def test_update_memory_list_when_valid_data(self):
        memory_data = [
            OperatorMemoryBean({"Name": "aten::add", "Size(KB)": 512, "Allocation Time(us)": 1, "Release Time(us)": 3}),
            OperatorMemoryBean({"Name": "aten::add", "Size(KB)": 512, "Allocation Time(us)": 0, "Release Time(us)": 3}),
            OperatorMemoryBean({"Name": "cann::add", "Size(KB)": 512, "Allocation Time(us)": 2, "Release Time(us)": 4}),
            OperatorMemoryBean(
                {"Name": "aten::add", "Size(KB)": 512, "Allocation Time(us)": 7, "Release Time(us)": 10})]
        with patch("msprof_analyze.prof_common.file_manager.FileManager.read_csv_file",
                  return_value=memory_data):
            res = self._create_mock_parser()
            res._path_level = ''
            res._operator_memory_path = ""
            res._enqueue_dict = {}
            res._dequeue_data = [TraceEventBean(event) for event in self.dequeue_events]
            res._result_data = ProfilingResult("NPU")
            res._update_memory_list()

            self.assertEqual(len(res._result_data.memory_list), 3)
            self.assertEqual(res._result_data.memory_list[0].duration, 2)

    def test_picking_hccl_event(self):
        res = self._create_mock_parser()
        res._hccl_pid = 7
        res._hccl_op_tid_list = [3, 4]
        res._comm_list = []
        res._comm_task_list = []
        res._result_data = ProfilingResult("NPU")
        for event in self.comm_events + self.task_events + self.dequeue_events:
            res._picking_hccl_event(TraceEventBean(event))
        self.assertEqual(len(res._comm_task_list), 2)
        self.assertEqual(len(res._comm_list), 1)

    def test_picking_task_queue_data(self):
        res = self._create_mock_parser()
        res._enqueue_dict = {}
        res._dequeue_data = []
        for event in self.enqueue_events + self.dequeue_events:
            result = res._picking_task_queue_data(TraceEventBean(event))
            self.assertTrue(result)
        for event in self.task_events:
            result = res._picking_task_queue_data(TraceEventBean(event))
            self.assertFalse(result)
        self.assertEqual(len(res._enqueue_dict), 1)
        self.assertEqual(len(res._dequeue_data), 1)

    def test_picking_overlap_analysis_data(self):
        res = self._create_mock_parser()
        res._overlap_analysis = []
        res._overlap_pid = 9
        for event in self.overlap_events:
            result = res._picking_overlap_analysis_data(TraceEventBean(event))
            self.assertTrue(result)
        for event in self.meta_events + self.dequeue_events:
            result = res._picking_overlap_analysis_data(TraceEventBean(event))
            self.assertFalse(result)

    def test_is_kernel_event(self):
        res = self._create_mock_parser()
        res._kernel_pid = 5
        self.assertTrue(res._is_kernel_event(TraceEventBean({"pid": 5, "ph": "X"})))
        self.assertFalse(res._is_kernel_event(TraceEventBean({"pid": 5, "ph": "M"})))
        self.assertFalse(res._is_kernel_event(TraceEventBean({"pid": 1, "ph": "x"})))

    def test_is_flow_event(self):
        res = self._create_mock_parser()
        self.assertTrue(res._is_flow_event(TraceEventBean({"cat": "async_npu"})))
        self.assertFalse(res._is_flow_event(TraceEventBean({"cat": "async"})))

    def test_is_torch_op_event(self):
        res = self._create_mock_parser()
        self.assertTrue(res._is_torch_op_event(TraceEventBean({"cat": "cpu_op"})))
        self.assertFalse(res._is_torch_op_event(TraceEventBean({"cat": "async"})))

    def test_filter_meta_id(self):
        with patch("msprof_analyze.compare_tools.compare_backend.profiling_parser.npu_profiling_parser."
                      "BaseProfilingParser._trace_event_generator",
                   return_value=(TraceEventBean(event) for event in self.meta_events)):
            res = self._create_mock_parser()
            res._hccl_op_tid_list = []
            res._hccl_tid_name_dict = {}
            res._group_comm_tid_dict = {}
            res._enable_communication_compare = True
            res._filter_meta_id()
            self.assertEqual(res._hccl_pid, 7)
            self.assertEqual(res._kernel_pid, 5)
            self.assertEqual(res._overlap_pid, 9)
            self.assertEqual(res._hccl_op_tid_list, [3])

    def test_get_path_level(self):
        # test profiling_path equals trace path
        path_dict = {Constant.PROFILING_PATH: "./trace_view.json", Constant.TRACE_PATH: "./trace_view.json"}
        self.assertEqual(NPUProfilingParser._get_path_level(path_dict), Constant.TRACE_PATH)
        # test profiling_path equals ascend output path
        path_dict = {Constant.PROFILING_PATH: "./ASCEND_PROFILER_OUTPUT", Constant.ASCEND_OUTPUT_PATH: "./ASCEND_PROFILER_OUTPUT"}
        self.assertEqual(NPUProfilingParser._get_path_level(path_dict), Constant.ASCEND_OUTPUT_PATH)
        # test profiling_path empty
        self.assertEqual(NPUProfilingParser._get_path_level({}), Constant.PROFILING_PATH)

    def test_calculate_uncovered_comm_range(self):
        # Test with overlapping events
        comm_events = [MagicMock(start_time=0, end_time=10), MagicMock(start_time=20, end_time=30)]
        uncovered_comm_events = [MagicMock(start_time=5, end_time=15), MagicMock(start_time=25, end_time=35)]

        result = NPUProfilingParser._NPUProfilingParser__calculate_uncovered_comm_range(comm_events,
                                                                                        uncovered_comm_events)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0].start_time, 5)
        self.assertEqual(result[0].end_time, 10)
        self.assertEqual(result[1].start_time, 25)
        self.assertEqual(result[1].end_time, 30)

    def test_calculate_overlap_time_with_uncovered_communication(self):
        # Test with overlapping events
        uncovered_communication_events = [MagicMock(start_time=0, end_time=10), MagicMock(start_time=20, end_time=30)]
        events = [MagicMock(start_time=5, end_time=15), MagicMock(start_time=25, end_time=35)]

        result = NPUProfilingParser._NPUProfilingParser__calculate_overlap_time_with_uncovered_communication(
            uncovered_communication_events, events)
        self.assertEqual(result, 10.0)  # 5 + 5 = 10

    def test_read_csv_data_success(self):
        with patch("msprof_analyze.prof_common.file_manager.FileManager.read_csv_file") as mock_read:
            mock_data = [{"test": "data"}]
            mock_read.return_value = mock_data
            result = NPUProfilingParser._read_csv_data("test.csv", OperatorMemoryBean)
            self.assertEqual(result, mock_data)

    def test_read_csv_data_file_not_found(self):
        with patch("msprof_analyze.prof_common.file_manager.FileManager.read_csv_file") as mock_read:
            mock_read.side_effect = FileNotFoundError()
            result = NPUProfilingParser._read_csv_data("nonexistent.csv", OperatorMemoryBean)
            self.assertEqual(result, [])

    def test_read_csv_data_exception(self):
        with patch("msprof_analyze.prof_common.file_manager.FileManager.read_csv_file") as mock_read:
            mock_read.side_effect = Exception("Test error")
            result = NPUProfilingParser._read_csv_data("error.csv", OperatorMemoryBean)
            self.assertEqual(result, [])

    def test_update_kernel_details_with_kernel_type(self):
        with patch("msprof_analyze.compare_tools.compare_backend.profiling_parser."
                   "npu_profiling_parser.NPUProfilingParser._read_csv_data") as mock_read:
            mock_kernel = OpStatisticBean({"OP Type": "MatMul", "Core Type": "AICore"})
            mock_read.return_value = [mock_kernel]

            res = self._create_mock_parser()
            res._path_level = "test"
            res._args = MagicMock()
            res._args.use_kernel_type = True
            res._op_statistic_path = "test.csv"
            res._result_data = ProfilingResult("NPU")

            res._update_kernel_details()
            self.assertIn("MatMul-AICore", res._result_data.kernel_details)

    def test_update_kernel_details_with_step_id(self):
        with patch("msprof_analyze.compare_tools.compare_backend.profiling_parser."
                   "npu_profiling_parser.NPUProfilingParser._read_csv_data") as mock_read:
            mock_kernel = KernelDetailsBean({"Name": "MatuMul", "Type": "MatMul", "Duration(us)": 100,
                                             "Start Time(us)": 0, "Step ID": 1})
            mock_read.return_value = [mock_kernel]

            res = self._create_mock_parser()
            res._path_level = "test"
            res._args = MagicMock()
            res._args.use_kernel_type = False
            res._kernel_detail_path = "test.csv"
            res._step_id = 1
            res._result_data = ProfilingResult("NPU")
            res._update_kernel_details()
            self.assertIn("MatMul", res._result_data.kernel_details)

    def test_update_kernel_details_no_data_for_step(self):
        with patch("msprof_analyze.compare_tools.compare_backend.profiling_parser."
                   "npu_profiling_parser.NPUProfilingParser._read_csv_data") as mock_read:
            mock_kernel = KernelDetailsBean({"Name": "MatuMul", "Type": "MatMul", "Duration(us)": 100,
                                             "Start Time(us)": 0, "Step ID": 1})
            mock_read.return_value = [mock_kernel]
            res = self._create_mock_parser()
            res._path_level = "test"
            res._args = MagicMock()
            res._args.use_kernel_type = False
            res._kernel_detail_path = "test.csv"
            res._step_id = 2
            res._result_data = ProfilingResult("NPU")

            with self.assertRaises(RuntimeError):
                res._update_kernel_details()

    def test_match_dequeue_data(self):
        res = self._create_mock_parser()
        res._dequeue_data = [
            MagicMock(start_time=0, end_time=10, corr_id=1),
            MagicMock(start_time=10, end_time=20, corr_id=2),
            MagicMock(start_time=20, end_time=30, corr_id=3)
        ]

        # Test exact match
        result = res._NPUProfilingParser__match_dequeue_data(5)
        self.assertEqual(result, 1)

        # Test no match
        result = res._NPUProfilingParser__match_dequeue_data(35)
        self.assertEqual(result, Constant.INVALID_VALUE)

        # Test empty dequeue data
        res._dequeue_data = []
        result = res._NPUProfilingParser__match_dequeue_data(5)
        self.assertEqual(result, Constant.INVALID_VALUE)

    def test_update_bandwidth_success(self):  # 感觉函数写的不太对
        with patch("msprof_analyze.prof_common.file_manager.FileManager.read_json_file") as mock_read:
            mock_data = {
                "group1": {
                    "collective": {
                        "Total Op Info": {
                            "Communication Bandwidth Info": {
                                "RDMA": {"Transit Size(MB)": 100, "Transit Time(ms)": 10},
                                "SDMA": {"Transit Size(MB)": 200, "Transit Time(ms)": 20}
                            }
                        }
                    }
                }
            }
            mock_read.return_value = mock_data

            res = self._create_mock_parser()
            res._path_level = "test"
            res._communication_path = "test.json"
            res._result_data = ProfilingResult("NPU")

            res._update_bandwidth()
            self.assertEqual(res._result_data.overall_metrics.rdma_bandwidth, 10.0)
            self.assertEqual(res._result_data.overall_metrics.sdma_bandwidth, 10.0)

    def test_update_bandwidth_file_failed(self):
        with patch("msprof_analyze.prof_common.file_manager.FileManager.read_json_file") as mock_read, \
                patch("msprof_analyze.compare_tools.compare_backend.profiling_parser.npu_profiling_parser.logger") \
                        as mock_logger:
            res = self._create_mock_parser()
            res._path_level = "test"
            res._communication_path = "nonexistent.json"
            res._result_data = ProfilingResult("NPU")

            mock_read.side_effect = FileNotFoundError()
            res._update_bandwidth()
            mock_logger.warning.assert_called_with("The file communication.json does not exist.")

    def test_calculate_mc2_communication_time(self):
        res = self._create_mock_parser()
        res._c_core_sqe_list = [
            MagicMock(end_time=5),
            MagicMock(end_time=10),
            MagicMock(end_time=15),
            MagicMock(end_time=20)
        ]
        res._c_core_sqe_index = 0

        kernel = MagicMock(start_time=0, end_time=25)
        result = res._calculate_mc2_communication_time(kernel)
        self.assertEqual(result, 10.0)  # (10-5) + (20-15) = 10

    def test_parse_mem_csv_success(self):
        with patch("msprof_analyze.compare_tools.compare_backend.profiling_parser."
                   "npu_profiling_parser.NPUProfilingParser._read_csv_data") as mock_read:
            mock_read.return_value = [MemoryRecordBean({"Total Reserved(MB)": 1024}),
                                      MemoryRecordBean({"Total Reserved(MB)": 2048})]

            res = self._create_mock_parser()
            res._path_level = "test"
            res._memory_record_path = "test.csv"
            res._result_data = ProfilingResult("NPU")

            res._NPUProfilingParser__parse_mem_csv()
            self.assertEqual(res._result_data.overall_metrics.memory_used, 2.0)

    def test_parse_mem_csv_file_not_found(self):
        with patch("msprof_analyze.compare_tools.compare_backend.profiling_parser."
                   "npu_profiling_parser.NPUProfilingParser._read_csv_data") as mock_read, \
                patch("msprof_analyze.compare_tools.compare_backend.profiling_parser.npu_profiling_parser.logger") \
                as mock_logger:
            mock_read.side_effect = FileNotFoundError()

            res = self._create_mock_parser()
            res._path_level = "test"
            res._memory_record_path = "nonexistent.csv"
            res._result_data = ProfilingResult("NPU")

            res._NPUProfilingParser__parse_mem_csv()
            mock_logger.warning.assert_called_with('Npu memory record csv file is not available.')

    def test_add_lccl_time(self):
        res = self._create_mock_parser()
        res._all_kernels = {
            "kernel1": TraceEventBean({"name": "KERNEL_AIVEC", "ts": 0, "dur": 100}),
            "kernel2": TraceEventBean({"name": "KERNEL_AICORE", "ts": 20, "dur": 30}),
            "kernel3": TraceEventBean({"name": "KERNEL_AIVEC", "ts": 50, "dur": 50})
        }
        res._result_data = ProfilingResult("NPU")

        res._NPUProfilingParser__add_lccl_time()
        self.assertEqual(res._result_data.overall_metrics.lccl_time, 150)  # 100 + 50

    def test_add_sdma_time(self):
        res = self._create_mock_parser()
        res._all_kernels = {
            "kernel1": TraceEventBean({"name": "kernel1", "ts": 0, "dur": 50,
                                       "args": {"Task Type": 'EVENT_WAIT_SQE', "Stream Id": 1}}),
            "kernel2": TraceEventBean({"name": "kernel2", "ts": 50, "dur": 30,
                                       "args": {"Task Type": 'SDMA_SQE', "Stream Id": 1}}),
            "kernel3": TraceEventBean({"name": "kernel3", "ts": 80, "dur": 20,
                                       "args": {"Task Type": 'AI_CORE', "Stream Id": 1}}),
            "kernel4": TraceEventBean({"name": "kernel4", "ts": 0, "dur": 75,
                                       "args": {"Task Type": 'AI_CORE', "Stream Id": 2}}),
        }
        res._result_data = ProfilingResult("NPU")

        res._NPUProfilingParser__add_sdma_time()
        self.assertEqual(res._result_data.overall_metrics.sdma_time_stream, 30.0)
        self.assertEqual(res._result_data.overall_metrics.sdma_num_stream, 1)


    def test_add_overlap_analysis_time_when_valid_data_then_update_overall_metrics(self):
        res = self._create_mock_parser()
        res._overlap_analysis = [
            TraceEventBean({"name": "Computing", "ts": 0, "dur": 100}),
            TraceEventBean({"name": "Communication(Not Overlapped)", "ts": 120, "dur": 50}),
            TraceEventBean({"name": "Free", "ts": 100, "dur": 20}),
            TraceEventBean({"name": "Computing", "ts": 170, "dur": 30})
        ]
        res._result_data = ProfilingResult("NPU")

        res._NPUProfilingParser__add_overlap_analysis_time()
        self.assertEqual(res._result_data.overall_metrics.compute_time, 130.0)
        self.assertEqual(res._result_data.overall_metrics.communication_not_overlapped, 50.0)
        self.assertEqual(res._result_data.overall_metrics.e2e_time, 200.0)  # max_ts - min_ts



    def test_add_overlap_analysis_time_when_no_data_then_logger_warning(self):
        with (patch("msprof_analyze.compare_tools.compare_backend.profiling_parser.npu_profiling_parser.logger")
                as mock_logger):
            res = self._create_mock_parser()
            res._overlap_analysis = []
            res._result_data = ProfilingResult("NPU")

            res._NPUProfilingParser__add_overlap_analysis_time()
            mock_logger.warning.assert_called_once_with('Failed to get overlap analysis data.')

    def test_parse_info_json_when_invalid_data_then_logger_warning(self):
        with (patch("msprof_analyze.prof_common.file_manager.FileManager.read_json_file") as mock_read, \
                patch("msprof_analyze.compare_tools.compare_backend.profiling_parser.npu_profiling_parser.logger")
                as mock_logger):
            mock_read.return_value = None

            res = self._create_mock_parser()
            res._info_json_path = "test.json"

            res._NPUProfilingParser__parse_info_json()
            mock_logger.warning.assert_called_once_with('Invalid profiler info.')

    def test_parse_kernel_csv_when_hide_op_pmu(self):
        with patch("msprof_analyze.compare_tools.compare_backend.profiling_parser."
                   "npu_profiling_parser.NPUProfilingParser._read_csv_data") as mock_read:
            mock_kernel = MagicMock()
            mock_kernel.is_hide_op_pmu.return_value = True
            mock_read.return_value = [mock_kernel]

            res = self._create_mock_parser()
            res._path_level = "test"
            res._kernel_detail_path = "test.csv"
            res._result_data = ProfilingResult("NPU")

            res._NPUProfilingParser__parse_kernel_csv()
            self.assertTrue(res._result_data.overall_metrics.hide_op_details)

    def test_get_dispatch_func(self):
        res = self._create_mock_parser()
        res._enable_profiling_compare = True
        res._enable_operator_compare = True
        res._enable_memory_compare = True
        res._enable_communication_compare = True
        res._enable_api_compare = True
        res._args = MagicMock()
        res._args.max_kernel_num = 100
        res._step_id = Constant.VOID_STEP

        func_list = res._get_dispatch_func()
        self.assertEqual(len(func_list), 8)
        self.assertIn(res._picking_torch_op_event, func_list)
        self.assertIn(res._picking_kernel_event, func_list)
        self.assertIn(res._picking_flow_event, func_list)
        self.assertIn(res._picking_hccl_event, func_list)

    def test_add_uncovered_communication_overlap_time(self):
        res = self._create_mock_parser()
        res._group_comm_tid_dict = {'123': [10], '456': [20]}
        res._hccl_tid_name_dict = {'123': 'tp', '456': 'pp'}
        # Communication op events
        res._comm_list = [
            TraceEventBean({"ph": "X", "name": "hccl_allreduce", "tid": '123', "ts": 1000, "dur": 1000}),  # [1000,2000]
            TraceEventBean({"ph": "X", "name": "hccl_allreduce", "tid": '456', "ts": 1500, "dur": 1000}),  # [1500,2500]
        ]
        # Uncovered communication window: [1200,2300]
        res._overlap_analysis = [
            TraceEventBean({"ph": "X", "name": "Communication(Not Overlapped)", "ts": 1200, "dur": 1100})
        ]
        res._result_data = ProfilingResult("NPU")

        res._NPUProfilingParser__add_uncovered_communication_overlap_time()

        # Overlap of uncovered ranges: [1500,2000] => 500 us, stored as 0.5 ms
        expected = {('tp', 'pp'): 0.5}
        self.assertEqual(res._result_data.overall_metrics.communication_overlap_time, expected)

    def test_add_communication_wait_time(self):
        res = self._create_mock_parser()
        res._group_comm_tid_dict = {'12345': [10]}
        res._hccl_tid_name_dict = {'12345': 'tp'}
        res._overlap_analysis = [
            TraceEventBean({"ph": "X", "name": "Communication(Not Overlapped)", "ts": 300, "dur": 200}),
            TraceEventBean({"ph": "X", "name": "Communication(Not Overlapped)", "ts": 1200, "dur": 2500})
        ]
        res._comm_list = [
            TraceEventBean({"ph": "X", "name": "hccl_allreduce_0", "tid": '12345', "ts": 100, "dur": 500}),
            TraceEventBean({"ph": "X", "name": "hccl_allreduce_1", "tid": '12345', "ts": 1000, "dur": 1700}),
            TraceEventBean({"ph": "X", "name": "hccl_allreduce_2", "tid": '12345', "ts": 2000, "dur": 500})
        ]
        res._comm_task_list = [
            TraceEventBean({"ph": "X", "name": "Notify_Wait", "tid": 10, "ts": 100, "dur": 200}),
            TraceEventBean({"ph": "X", "name": "Notify_Wait", "tid": 10, "ts": 300, "dur": 100}),
            TraceEventBean({"ph": "X", "name": "Reduce_Inline", "tid": 10, "ts": 400, "dur": 200}),
            # RDMA 5 tasks:
            TraceEventBean({"ph": "X", "name": "RDMASend", "tid": 10, "ts": 1000, "dur": 100}),
            TraceEventBean({"ph": "X", "name": "RDMASend", "tid": 10, "ts": 1200, "dur": 100}),
            TraceEventBean({"ph": "X", "name": "Notify_Wait", "tid": 10, "ts": 1300, "dur": 200}),
            TraceEventBean({"ph": "X", "name": "RDMASend", "tid": 10, "ts": 1500, "dur": 100}),
            TraceEventBean({"ph": "X", "name": "Notify_Wait", "tid": 10, "ts": 1600, "dur": 100}),
            # RDMA3 tasks:
            TraceEventBean({"ph": "X", "name": "RDMASend", "tid": 10, "ts": 2000, "dur": 100}),
            TraceEventBean({"ph": "X", "name": "RDMASend", "tid": 10, "ts": 2100, "dur": 100}),
            TraceEventBean({"ph": "X", "name": "Notify_Wait", "tid": 10, "ts": 2200, "dur": 300}),
        ]
        res._result_data = ProfilingResult("NPU")

        res._NPUProfilingParser__add_communication_wait_time()

        comm_time = res._result_data.overall_metrics.communication_group_time
        self.assertIn('tp', comm_time)
        self.assertEqual(comm_time['tp'][Constant.WAIT_TIME], 100.0)
        self.assertEqual(comm_time['tp'][Constant.TRANSMIT_TIME], 2100.0)
