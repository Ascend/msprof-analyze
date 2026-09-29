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

from msprof_analyze.compare_tools.compare_backend.compare_bean.origin_data_bean.trace_event_bean import TraceEventBean


class TestTraceEventBean(unittest.TestCase):

    def test_property(self):
        data = {"pid": 1, "tid": 1, "ts": 1, "dur": 2, "ph": "X", "cat": "CPU_OP", "name": "Add", "args": {}}
        event = TraceEventBean(data)
        check_value = f"{event.pid}-{event.tid}-{event.dur}-{event.start_time}-{event.end_time}-{event.name}-" \
                      f"{event.lower_name}-{event.lower_cat}-{event.id}-{event.args}-{event.process_name}"
        self.assertEqual(check_value, "1-1-2.0-1-3-Add-add-cpu_op-None-{}-")
        none_property_list = [event.stream_id, event.stream, event.task_type, event.task_id, event.corr_id, event.addr]
        for property_value in none_property_list:
            self.assertEqual(property_value, None)
        self.assertEqual(event.device_id, -1)
        self.assertEqual(event.total_reserved, 0)
        self.assertEqual(event.bytes_kb, 0)

    def test_is_m_mode(self) -> bool:
        self.assertTrue(TraceEventBean({"ph": "M"}).is_m_mode())
        self.assertFalse(TraceEventBean({"ph": "X"}).is_m_mode())

    def test_is_x_mode(self) -> bool:
        self.assertTrue(TraceEventBean({"ph": "X"}).is_x_mode())
        self.assertFalse(TraceEventBean({"ph": "M"}).is_x_mode())

    def test_is_flow_start(self) -> bool:
        self.assertTrue(TraceEventBean({"ph": "s"}).is_flow_start())
        self.assertFalse(TraceEventBean({"ph": "f"}).is_flow_start())

    def test_is_flow_end(self) -> bool:
        self.assertTrue(TraceEventBean({"ph": "f"}).is_flow_end())
        self.assertFalse(TraceEventBean({"ph": "s"}).is_flow_end())

    def test_is_enqueue(self) -> bool:
        self.assertTrue(TraceEventBean({"cat": "Enqueue"}).is_enqueue())
        self.assertFalse(TraceEventBean({"cat": "cpu_op"}).is_enqueue())

    def test_is_dequeue(self) -> bool:
        self.assertTrue(TraceEventBean({"cat": "Dequeue"}).is_dequeue())
        self.assertFalse(TraceEventBean({"cat": "cpu_op"}).is_dequeue())

    def test_is_process_meta(self) -> bool:
        self.assertTrue(TraceEventBean({"ph": "M", "name": "process_name"}).is_process_meta())
        self.assertFalse(TraceEventBean({"cat": "cpu_op"}).is_process_meta())

    def test_is_thread_meta(self) -> bool:
        self.assertTrue(TraceEventBean({"ph": "M", "name": "thread_name"}).is_thread_meta())
        self.assertFalse(TraceEventBean({"cat": "cpu_op"}).is_thread_meta())

    def test_is_communication_op_thread(self) -> bool:
        self.assertTrue(TraceEventBean({"args": {"name": "Communication1"}}).is_communication_op_thread())
        self.assertFalse(TraceEventBean({"args": {"name": "add"}}).is_communication_op_thread())

    def test_is_hccl_process_name(self) -> bool:
        self.assertTrue(TraceEventBean({"args": {"name": "HCCL"}}).is_hccl_process_name())
        self.assertFalse(TraceEventBean({"args": {"name": "Ascend Hardware"}}).is_hccl_process_name())

    def test_is_overlap_process_name(self) -> bool:
        self.assertTrue(TraceEventBean({"args": {"name": "Overlap Analysis"}}).is_overlap_process_name())
        self.assertFalse(TraceEventBean({"args": {"name": "Ascend Hardware"}}).is_overlap_process_name())

    def test_is_npu_process_name(self) -> bool:
        self.assertTrue(TraceEventBean({"args": {"name": "Ascend Hardware"}}).is_npu_process_name())
        self.assertFalse(TraceEventBean({"args": {"name": "Ascend"}}).is_npu_process_name())

    def test_is_computing_event(self):
        self.assertTrue(TraceEventBean({"name": "Computing"}).is_computing_event())
        self.assertFalse(TraceEventBean({"name": "add"}).is_computing_event())

    def test_is_comm_not_overlap(self):
        self.assertTrue(TraceEventBean({"name": "Communication(Not Overlapped)"}).is_comm_not_overlap())
        self.assertFalse(TraceEventBean({"name": "add"}).is_comm_not_overlap())

    def test_is_kernel_cat(self):
        self.assertTrue(TraceEventBean({"cat": "Kernel"}).is_kernel_cat())
        self.assertFalse(TraceEventBean({"cat": "cpu_op"}).is_kernel_cat())

    def test_is_nccl_name(self):
        self.assertTrue(TraceEventBean({"name": "ncclkernel"}).is_nccl_name())
        self.assertFalse(TraceEventBean({"name": "add"}).is_nccl_name())

    def test_is_kernel_except_nccl(self):
        self.assertTrue(TraceEventBean({"cat": "Kernel", "name": "add"}).is_kernel_except_nccl())
        self.assertFalse(TraceEventBean({"cat": "Kernel", "name": "ncclkernel"}).is_kernel_except_nccl())

    def test_is_memory_event(self):
        self.assertTrue(TraceEventBean({"name": "[memory]", "args": {"Device Id": 1}}).is_memory_event())
        self.assertFalse(TraceEventBean({"name": "[memory]"}).is_memory_event())

    def test_is_compute_event(self):
        for task_type in ('AI_CORE', 'MIX_AIC', 'MIX_AIV', 'AI_CPU', 'AI_VECTOR_CORE', 'FFTS_PLUS'):
            self.assertTrue(TraceEventBean({"name": "add", "args": {"Task Type": task_type}}).is_compute_event())
        self.assertFalse(TraceEventBean({"name": "[memory]"}).is_compute_event())

    def test_is_sdma_event(self):
        for task_type in ('SDMA_SQE', 'PCIE_DMA_SQE'):
            self.assertTrue(TraceEventBean({"name": "add", "args": {"Task Type": task_type}}).is_sdma_event())
        self.assertFalse(TraceEventBean({"name": "[memory]"}).is_sdma_event())

    def test_is_event_wait(self):
        self.assertTrue(TraceEventBean({"name": "add", "args": {"Task Type": 'EVENT_WAIT_SQE'}}).is_event_wait())
        self.assertFalse(TraceEventBean({"name": "[memory]"}).is_event_wait())

    def is_backward(self):
        self.assertTrue(TraceEventBean({"name": "add_bwd"}).is_event_wait())
        self.assertTrue(TraceEventBean({"name": "add_backward"}).is_event_wait())
        self.assertFalse(TraceEventBean({"name": "[memory]"}).is_event_wait())
