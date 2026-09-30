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
from unittest.mock import patch
from decimal import Decimal

from msprof_analyze.prof_common.analyze_dict import AnalyzeDict
from msprof_analyze.prof_common.constant import Constant
from msprof_analyze.compare_tools.compare_backend.compare_bean.origin_data_bean.trace_event_bean import TraceEventBean
from msprof_analyze.compare_tools.compare_backend.compare_bean.origin_data_bean.kernel_details_bean \
    import KernelDetailsBean
from msprof_analyze.compare_tools.compare_backend.profiling_parser.base_profiling_parser import (
    BaseProfilingParser,
    ProfilingResult
)


class ProfilingParser(BaseProfilingParser):
    def __init__(self, args: any, path_dict: dict):
        super().__init__(args, path_dict)

    def init(self, flow_dict, all_kernels):
        self._profiling_type = "GPU"
        self._trace_events = []
        self._profiling_path = ""
        self._json_path = ""
        self._result_data = ProfilingResult("GPU")
        self._flow_dict = flow_dict
        self._all_kernels = all_kernels
        self._comm_list = []
        self._comm_task_list = []
        self._dispatch_func = []
        self._enable_profiling_compare = True
        self._enable_operator_compare = True
        self._enable_memory_compare = True
        self._enable_communication_compare = True
        self._enable_kernel_compare = True
        self._enable_api_compare = True
        self._bwd_tid = 1
        self._step_id = -1
        self._step_range = []

    def _update_kernel_details(self):
        pass

    def _update_memory_list(self):
        pass

    def _update_overall_metrics(self):
        pass

    def _picking_communication_event(self):
        pass

    def _is_kernel_event(self, event):
        return True

    def _is_flow_event(self, event):
        return True

    def _is_torch_op_event(self, event):
        return True

    def _get_dispatch_func(self):
        pass

    def _calculate_mc2_communication_time(self, kernel: KernelDetailsBean):
        return 1.25


class MockEvent:
    def __init__(self, pid, tid, ts, ph="M"):
        self.pid = pid
        self.tid = tid
        self.ts = ts
        self.ph = ph
        self.id = 1
        self.event = None

    @property
    def name(self):
        return "wait"

    @property
    def dur(self):
        return 7

    @property
    def start_time(self):
        return self.ts

    @staticmethod
    def is_nccl_name():
        return False

    def is_flow_start(self):
        return self.ph == "s"

    def is_flow_end(self):
        return self.ph == "f"


class TestBaseProfilingParser(unittest.TestCase):
    flow_dict = {1: {"start": MockEvent(1, 2, 12), "end": MockEvent(2, 3, 21)},
                 2: {"start": MockEvent(1, 2, 12), "end": MockEvent(2, 3, 22)},
                 3: {}}
    all_kernels = {"2-3-23": MockEvent(2, 3, 23), "2-3-21": MockEvent(2, 3, 21), "2-3-22": MockEvent(2, 3, 22)}
    comm_events = [{"ph": "X", "name": "hcom_allreduce", "pid": 7, "tid": 3, "ts": 1, "dur": 2}]
    task_events = [{"ph": "X", "name": "notify_wait", "pid": 7, "tid": 1, "ts": 2, "dur": 1},
                   {"ph": "X", "name": "notify_wait", "pid": 7, "tid": 1, "ts": 5, "dur": 1}]
    args = AnalyzeDict({
        "base_profiling_path": "",
        "comparison_profiling_path": "",
        "enable_profiling_compare": True,
        "enable_operator_compare": True,
        "enable_memory_compare": True,
        "enable_communication_compare": True,
        "enable_api_compare": True,
        "enable_kernel_compare": True,
        "disable_details": False,
        "disable_module": False,
        "output_path": "",
        "max_kernel_num": None,
        "op_name_map": AnalyzeDict(),
        "use_input_shape": False,
        "gpu_flow_cat": "",
        "base_step": "",
        "comparison_step": "",
        "force": False,
        "use_kernel_type": False
    })
    path_dict = {
        "info_path": "",
        "profiling_type": "",
        "profiling_path": "",
        "trace_path": "",
        "ascend_output": "",
    }


    def test_picking_torch_op_event(self):
        event = MockEvent(1, 2, 3)
        parser = ProfilingParser(self.args, self.path_dict)
        parser.init({}, {})
        self.assertTrue(parser._picking_torch_op_event(event))

    def test_picking_kernel_event(self):
        event = MockEvent(1, 2, 3)
        with patch("msprof_analyze.compare_tools.compare_backend.profiling_parser."
                   "base_profiling_parser.BaseProfilingParser.__init__"):
            parser = ProfilingParser(self.args, self.path_dict)
            parser.init({}, {})
            self.assertTrue(parser._picking_kernel_event(event))

    def test_picking_flow_event(self):
        events = [MockEvent(1, 2, 3, "s"), MockEvent(1, 2, 3, "f")]
        with patch("msprof_analyze.compare_tools.compare_backend.profiling_parser."
                   "base_profiling_parser.BaseProfilingParser.__init__"):
            parser = ProfilingParser(self.args, self.path_dict)
            parser.init({}, {})
            for event in events:
                self.assertTrue(parser._picking_flow_event(event))

    def test_update_kernel_dict_when_valid_input(self):
        with patch("msprof_analyze.compare_tools.compare_backend.profiling_parser."
                   "base_profiling_parser.BaseProfilingParser.__init__"):
            parser = ProfilingParser(self.args, self.path_dict)
            parser.init(self.flow_dict, self.all_kernels)
            parser._update_kernel_dict()
            self.assertEqual(len(parser._result_data.kernel_dict.get(12)), 2)

    def test_update_kernel_dict_when_without_kernels_return_null(self):
        with patch("msprof_analyze.compare_tools.compare_backend.profiling_parser."
                   "base_profiling_parser.BaseProfilingParser.__init__"):
            parser = ProfilingParser(self.args, self.path_dict)
            parser.init(self.flow_dict, {})
            parser._update_kernel_dict()
            self.assertEqual(len(parser._result_data.kernel_dict), 0)

    def test_update_kernel_dict_when_without_flow_return_null(self):
        with patch("msprof_analyze.compare_tools.compare_backend.profiling_parser."
                   "base_profiling_parser.BaseProfilingParser.__init__"):
            parser = ProfilingParser(self.args, self.path_dict)
            parser.init({}, self.all_kernels)
            parser._update_kernel_dict()
            self.assertEqual(len(parser._result_data.kernel_dict), 0)

    def test_check_result_data(self):
        parser = ProfilingParser(self.args, self.path_dict)
        parser.init(self.flow_dict, self.all_kernels)
        parser._check_result_data()
        parser._profiling_path = "./"
        parser._check_result_data()

    def test_load_data_when_valid_input(self):
        parser = ProfilingParser(self.args, self.path_dict)
        parser.init(self.flow_dict, self.all_kernels)
        result_data = parser.load_data()
        self.assertEqual(len(result_data.kernel_dict.get(12)), 2)

    def test_update_communication_dict(self):
        result = {'allreduce': {'comm_list': [2.0], 'comm_task': {'notify_wait': [1.0]}}}
        parser = ProfilingParser(self.args, self.path_dict)
        parser.init({}, {})
        parser._comm_task_list = [TraceEventBean(event) for event in self.task_events]
        parser._comm_list = [TraceEventBean(event) for event in self.comm_events]
        parser._profiling_type = "NPU"
        parser._result_data = ProfilingResult("NPU")
        parser._update_communication_dict()
        self.assertEqual(parser._result_data.communication_dict, result)

    def test_cpu_cube_op_when_cpu_cube_op_is_not_none(self):
        event = MockEvent(1, 2, 3)
        parser = ProfilingParser(self.args, self.path_dict)
        parser._cpu_cube_op = [event]
        self.assertEqual(parser.cpu_cube_op, [event])

    def test_cpu_cube_op_when_cpu_cube_op_is_none(self):
        parser = ProfilingParser(self.args, self.path_dict)
        parser._result_data.torch_op_data = []
        self.assertEqual(parser.cpu_cube_op, [])

    def test_step_range_when_step_range_is_not_none(self):
        parser = ProfilingParser(self.args, self.path_dict)
        parser._step_range = [1, 2]
        self.assertEqual(parser.step_range, [1, 2])

    def test_step_range_should_return_empty_list_when_step_range_is_none_and_step_id_is_void_step(self):
        parser = ProfilingParser(self.args, self.path_dict)
        parser.init({}, {})
        self.assertEqual(parser.step_range, [])

    def test_step_range_should_return_empty_list_when_step_range_is_none_and_step_id_is_not_void_step(self):
        parser = ProfilingParser(self.args, self.path_dict)
        parser._step_id = 1
        event = TraceEventBean({})
        event._name = "ProfilerStep#1"
        parser._result_data.torch_op_data = [event]
        self.assertEqual(parser.step_range, [Decimal('0'), Decimal('0')])

    def test_categorize_computing_performance_data_when_tk_is_different_types(self):
        parser = ProfilingParser(self.args, self.path_dict)
        parser._step_id = 1
        event = KernelDetailsBean({})
        event._op_type = "PagedAttention"
        event._duration = 1.2
        parser.categorize_computing_performance_data(event, 1)
        self.assertAlmostEqual(parser._result_data.overall_metrics.page_attention_time, 1.2)
        self.assertEqual(parser._result_data.overall_metrics.page_attention_num, 1)
        event._op_type = ""
        event._name = "aclnnInplaceCopy_TensorMove"
        parser.categorize_computing_performance_data(event, 1)
        self.assertAlmostEqual(parser._result_data.overall_metrics.sdma_time_tensor_move, 1.2)
        self.assertEqual(parser._result_data.overall_metrics.sdma_num_tensor_move, 1)
        event._name = "allgathermatmul"
        parser.categorize_computing_performance_data(event, 1)
        mc2_time_dict = parser._result_data.overall_metrics.mc2_time_dict
        self.assertAlmostEqual(mc2_time_dict.get("allgathermatmul").get(Constant.MC2_TIME), 1.2)
        self.assertAlmostEqual(mc2_time_dict.get("allgathermatmul").get(Constant.MC2_COMPUTING), 0)
        self.assertAlmostEqual(mc2_time_dict.get("allgathermatmul").get(Constant.MC2_COMMUNICATION), 1.25)
        self.assertEqual(mc2_time_dict.get("allgathermatmul").get(Constant.MC2_NUMBER), 1)
        event = KernelDetailsBean({})
        event._start_time = Decimal("1.2")
        event._duration = 1.1
        event._op_type = "Flashattention"
        parser._cpu_cube_op = [event]
        parser._profiling_type = "NPU"
        parser.categorize_computing_performance_data(event, 1)
        self.assertAlmostEqual(parser._result_data.overall_metrics.fa_time_fwd_cube, 1.1)
        self.assertEqual(parser._result_data.overall_metrics.fa_num_fwd_cube, 1)
        event._op_type = "conv"
        parser.categorize_computing_performance_data(event, 1)
        self.assertAlmostEqual(parser._result_data.overall_metrics.conv_time_fwd_cube, 1.1)
        self.assertEqual(parser._result_data.overall_metrics.conv_num_fwd_cube, 1)
        event._op_type = "add_custom"
        event._mac_time = 1.1
        parser.categorize_computing_performance_data(event, 1)
        self.assertAlmostEqual(parser._result_data.overall_metrics.other_cube_time, 1.1)
        self.assertEqual(parser._result_data.overall_metrics.other_cube_num, 1)
        event._op_type = "transpose"
        event._name = "transpose"
        event._mac_time = 0
        parser.categorize_computing_performance_data(event, 1)
        self.assertAlmostEqual(parser._result_data.overall_metrics.vector_time_trans, 1.1)
        self.assertEqual(parser._result_data.overall_metrics.vector_num_trans, 1)
        event._name = "RmsNorm"
        event._op_type = "RmsNorm"
        parser.categorize_computing_performance_data(event, 1)
        self.assertAlmostEqual(parser._result_data.overall_metrics.vector_time_notrans, 1.1)
        self.assertEqual(parser._result_data.overall_metrics.vector_num_notrans, 1)

    def test_categorize_cube_performance_data_given_cpu_op_and_tk_when_all_scenarios_then_update_record(self):
        parser = ProfilingParser(self.args, self.path_dict)
        event = TraceEventBean({})
        event._name = "Flash_Attention_Backward"
        tk = KernelDetailsBean({})
        tk._mac_time = 1.1
        tk._duration = 2.1
        parser._categorize_cube_performance_data(event, tk)
        self.assertAlmostEqual(parser._result_data.overall_metrics.fa_time_bwd_cube, 2.1)
        self.assertEqual(parser._result_data.overall_metrics.fa_num_bwd_cube, 1)
        tk._mac_time = 0
        parser._categorize_cube_performance_data(event, tk)
        self.assertAlmostEqual(parser._result_data.overall_metrics.fa_time_bwd_vector, 2.1)
        self.assertEqual(parser._result_data.overall_metrics.fa_num_bwd_vector, 1)
        event._name = "Flash_Attention"
        parser._categorize_cube_performance_data(event, tk)
        self.assertAlmostEqual(parser._result_data.overall_metrics.fa_time_fwd_vector, 2.1)
        self.assertEqual(parser._result_data.overall_metrics.fa_num_fwd_vector, 1)
        tk._mac_time = 1.1
        parser._categorize_cube_performance_data(event, tk)
        self.assertAlmostEqual(parser._result_data.overall_metrics.fa_time_fwd_cube, 2.1)
        self.assertEqual(parser._result_data.overall_metrics.fa_num_fwd_cube, 1)
        event._name = "aten::conv"
        parser._categorize_cube_performance_data(event, tk)
        self.assertAlmostEqual(parser._result_data.overall_metrics.conv_time_fwd_cube, 2.1)
        self.assertEqual(parser._result_data.overall_metrics.conv_num_fwd_cube, 1)
        tk._mac_time = 0
        parser._categorize_cube_performance_data(event, tk)
        self.assertAlmostEqual(parser._result_data.overall_metrics.conv_time_fwd_vector, 2.1)
        self.assertEqual(parser._result_data.overall_metrics.conv_num_fwd_vector, 1)
        event._name = "aten::conv_backward"
        parser._categorize_cube_performance_data(event, tk)
        self.assertAlmostEqual(parser._result_data.overall_metrics.conv_time_bwd_vector, 2.1)
        self.assertEqual(parser._result_data.overall_metrics.conv_num_bwd_vector, 1)
        tk._mac_time = 1.1
        parser._categorize_cube_performance_data(event, tk)
        self.assertAlmostEqual(parser._result_data.overall_metrics.conv_time_bwd_cube, 2.1)
        self.assertEqual(parser._result_data.overall_metrics.conv_num_bwd_cube, 1)
        event._name = "aten::addmm"
        parser._categorize_cube_performance_data(event, tk)
        self.assertAlmostEqual(parser._result_data.overall_metrics.matmul_time_cube, 2.1)
        self.assertEqual(parser._result_data.overall_metrics.matmul_num_cube, 1)
        tk._mac_time = 0
        parser._categorize_cube_performance_data(event, tk)
        self.assertAlmostEqual(parser._result_data.overall_metrics.matmul_time_vector, 2.1)
        self.assertEqual(parser._result_data.overall_metrics.matmul_num_vector, 1)

    @patch("msprof_analyze.prof_common.file_manager.FileManager.read_json_file")
    @patch("os.path.exists")
    def test_update_pg_name_map(self, mock_exists, mock_read_json_file):
        meta_data = {
            Constant.PARALLEL_GROUP_INFO:
                {"group_name_51": {"group_name": "tp", "group_rank": 0, "global_ranks": [0, 1]}}
        }
        mock_read_json_file.side_effect = [{}, meta_data]
        parser = ProfilingParser(self.args, self.path_dict)
        parser._update_pg_name_map()
        parser._update_pg_name_map()
        self.assertEqual(parser._result_data.overall_metrics.pg_name_dict, {'Group group_name_51 Communication': 'tp'})


class TestProfilingResult(unittest.TestCase):
    def test_update_torch_op_data_when_valid_input(self):
        res = ProfilingResult("GPU")
        res.update_torch_op_data(MockEvent(1, 2, 3))
        self.assertEqual(len(res.torch_op_data), 1)

    def test_update_kernel_dict_when_valid_input(self):
        res = ProfilingResult("GPU")
        res.update_kernel_dict(2, MockEvent(1, 2, 3))
        self.assertEqual(len(res.kernel_dict.get(2)), 1)

    def test_update_memory_list_when_valid_input(self):
        res = ProfilingResult("GPU")
        res.update_memory_list({})
        self.assertEqual(len(res.memory_list), 1)

    def test_update_communication_dict_when_valid_input(self):
        res = ProfilingResult("GPU")
        res.update_communication_dict("reduce", 9)
        self.assertEqual(sum(res.communication_dict.get("reduce", {}).get("comm_list")), 9)

    def test_update_comm_task_data_when_valid_input(self):
        res = ProfilingResult("GPU")
        res.update_comm_task_data("reduce", MockEvent(1, 1, 1))
        self.assertEqual(sum(res.communication_dict.get("reduce", {}).get("comm_task", {}).get("wait")), 7)
