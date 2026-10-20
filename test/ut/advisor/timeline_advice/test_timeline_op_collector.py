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

from msprof_analyze.advisor.dataset.timeline_op_collector.timeline_op_collector import (
    OpCompileCollector,
    SynchronizeStreamCollector,
    MemCollector,
    DataloaderCollector,
    SyncBNCollector,
    AtenCollector,
    OptimizerCollector,
    SpecificTaskTypeOpCollector,
    TorchToNpuCollector,
    AclToNpuCollector,
    OpStackCollector,
    StepCollector
)
from msprof_analyze.advisor.common.timeline.event import TimelineEvent
from test.ut.advisor.advisor_backend.tools.tool import recover_env


class TestTimelineOpCollector(unittest.TestCase):
    @classmethod
    def tearDownClass(cls) -> None:
        recover_env()

    def setUp(self) -> None:
        self.mock_step_event = TimelineEvent(dict(name="ProfilerStep#1", ts=1, dur=1000))
        self.mock_op_compile_event = TimelineEvent(dict(name="AscendCL@aclopCompileAndExecute", ts=2, dur=1))
        self.mock_sync_stream_event = TimelineEvent(dict(name="AscendCL@aclrtSynchronizeStream", dur=1000000000))
        self.mock_mem_op_event = TimelineEvent(dict(name="AscendCL@aclMallocMemInner", dur=10))
        self.mock_dataloader_event = TimelineEvent(dict(name="dataloader"))
        self.mock_sync_bn_event = TimelineEvent(dict(name="syncbatchnorm"))
        self.mock_aten_event = TimelineEvent(dict(name="aten::conv3d"))
        self.mock_optimizer_event = TimelineEvent(dict(name="Optimizer.step#"))
        self.mock_ai_cpu_event = TimelineEvent(
            {"name": "index", "args": TimelineEvent({"Task Type": "AI_CPU"}), "ts": 1})
        self.mock_torch_to_npu_event = TimelineEvent(dict(name="torch_to_npu", tid=1, ts=1, ph=1, id=1))
        self.mock_acl_to_npu_event = TimelineEvent(dict(name="acl_to_npu", ts=1))
        self.mock_op_stack_event = TimelineEvent(
            {"name": "aten::conv3d", "dataset_index": 1, "ts": 1, "args": TimelineEvent({"Call stack": "mock_stack"})})

    def test_step_collector(self):
        step_collector = StepCollector()
        step_collector.add_op(self.mock_step_event)
        step_collector.post_process()
        self.assertEqual(step_collector.attribute_to_dataset.get("profiler_step"), [self.mock_step_event])

    def test_op_compile_collector(self):
        op_compile_collector = OpCompileCollector()
        op_compile_collector.add_op(self.mock_op_compile_event)
        op_compile_collector.post_process(op_compile_collector.op_list)
        self.assertEqual(op_compile_collector.attribute_to_dataset.get("ops_compile"), op_compile_collector)
        self.assertEqual(op_compile_collector.total_time, 1)
        self.assertEqual(op_compile_collector.total_count, 1)

    def test_sync_stream_collector(self):
        sync_stream_collector = SynchronizeStreamCollector()
        sync_stream_collector.post_process()
        self.assertEqual(sync_stream_collector.attribute_to_dataset.get("synchronize_stream"), [])

    def test_mem_op_collector(self):
        mem_op_collector = MemCollector()
        mem_op_collector.add_op(self.mock_mem_op_event)
        mem_op_collector.post_process(mem_op_collector.op_list)
        self.assertEqual(mem_op_collector.attribute_to_dataset.get("memory_ops"), mem_op_collector)
        self.assertEqual(mem_op_collector.mem_op_info.get("AscendCL@aclMallocMemInner"), {"count": 1, "total_dur": 10})

    def test_dataloader_collector(self):
        dataloader_collector = DataloaderCollector()
        dataloader_collector.add_op(self.mock_dataloader_event)
        dataloader_collector.post_process()
        self.assertEqual(len(dataloader_collector.attribute_to_dataset.get("dataloader")), 1)

    def test_sync_bn_collector(self):
        sync_bn_collector = SyncBNCollector()
        sync_bn_collector.add_op(self.mock_sync_bn_event)
        sync_bn_collector.post_process(sync_bn_collector.op_list)
        self.assertEqual(len(sync_bn_collector.attribute_to_dataset.get("sync_batchnorm")), 1)

    def test_aten_collector(self):
        aten_collector = AtenCollector()
        aten_collector.add_op(self.mock_aten_event)
        aten_collector.add_op(self.mock_sync_stream_event)
        aten_collector.post_process(aten_collector.op_list)
        self.assertEqual(len(aten_collector.attribute_to_dataset.get("aten")), 2)

    def test_optimizer_collector(self):
        optimizer_collector = OptimizerCollector()
        optimizer_collector.add_op(self.mock_optimizer_event)
        optimizer_collector.post_process(optimizer_collector.op_list)
        self.assertEqual(len(optimizer_collector.attribute_to_dataset.get("optimizer")), 1)

    def test_specific_task_type_op_collector(self):
        specific_task_type_op_collector = SpecificTaskTypeOpCollector()
        specific_task_type_op_collector.add_op(self.mock_ai_cpu_event)
        specific_task_type_op_collector.post_process(specific_task_type_op_collector.op_list)
        key = f"{self.mock_ai_cpu_event.name}-{self.mock_ai_cpu_event.ts}"
        self.assertTrue(
            specific_task_type_op_collector.attribute_to_dataset.get("ops_with_task_type", {}).get(key))
        self.assertTrue(specific_task_type_op_collector.attribute_to_dataset.get("task_op_names"), [key])

    def test_torch_to_npu_collector(self):
        torch_to_npu_collector = TorchToNpuCollector()
        torch_to_npu_collector.add_op(self.mock_torch_to_npu_event)
        torch_to_npu_collector.post_process(torch_to_npu_collector.op_list)
        key = f"{self.mock_torch_to_npu_event.ph}-{self.mock_torch_to_npu_event.id}"
        self.assertIn(key, torch_to_npu_collector.attribute_to_dataset.get("torch_to_npu"))

    def test_acl_to_npu_collector(self):
        acl_to_npu_collector = AclToNpuCollector()
        acl_to_npu_collector.add_op(self.mock_acl_to_npu_event)
        acl_to_npu_collector.post_process(acl_to_npu_collector.op_list)
        self.assertEqual(acl_to_npu_collector.attribute_to_dataset.get("acl_to_npu"),
                         set([str(self.mock_acl_to_npu_event.ts)]))

    def test_op_stack_collector(self):
        op_stack_collector = OpStackCollector()
        op_stack_collector.add_op(self.mock_op_stack_event)
        op_stack_collector.post_process(op_stack_collector.op_list)
        self.assertIn(
            str(self.mock_op_stack_event.ts), op_stack_collector.attribute_to_dataset.get("ops_with_stack"))


if __name__ == '__main__':
    tester = TestTimelineOpCollector()
    tester.test_step_collector()
    tester.test_op_compile_collector()
    tester.test_sync_stream_collector()
    tester.test_mem_op_collector()
    tester.test_dataloader_collector()
    tester.test_sync_bn_collector()
    tester.test_aten_collector()
    tester.test_optimizer_collector()
    tester.test_specific_task_type_op_collector()
    tester.test_torch_to_npu_collector()
    tester.test_acl_to_npu_collector()
    tester.test_op_stack_collector()
