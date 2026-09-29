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

from msprof_analyze.prof_common.constant import Constant
from msprof_analyze.advisor.dataset.stack.timeline_stack_finder import TimelineOpStackFinder
from msprof_analyze.advisor.result.result import OptimizeResult


class _FakeEvent:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)

    def get(self, key, default=None):
        return getattr(self, key, default)


class _FakeDataset:
    def __init__(self):
        self.ops_with_task_type = {}
        self.torch_to_npu = {}
        self.acl_to_npu = set()
        self.ops_with_stack = {}
        self._events = []
        self.dataset_len = 0

    def add_ops_with_task_type(self, name, task_type, tid, ts, task_id):
        key = f'{name}_{tid}'
        self.ops_with_task_type[key] = _FakeEvent(name=name, **{Constant.TASK_TYPE: task_type}, tid=tid, ts=ts,
                                                  task_id=task_id)

    def add_torch_to_npu(self, key, ts):
        self.torch_to_npu[key] = _FakeEvent(ts=ts)

    def add_acl_to_npu(self, ts):
        self.acl_to_npu.add(ts)

    def add_ops_with_stack(self, ts, name, dataset_index):
        self.ops_with_stack[ts] = {"name": name, "dataset_index": dataset_index, "ts": ts}

    def add_iter_event(self, args=None):
        args = args or {}
        self._events.append({"args": args})
        self.dataset_len = len(self._events)

    def parse_data_with_generator(self, callback):
        for idx, ev in enumerate(self._events):
            callback(idx, ev)
        return True


class TestTimelineOpStackFinder(unittest.TestCase):
    """Test class for TimelineOpStackFinder"""

    def setUp(self):
        """Set up for each test method"""
        self.finder = TimelineOpStackFinder()

    def create_basic_dataset(self):
        """Helper method to create a basic dataset"""
        return _FakeDataset()

    def test_when_no_matching_ops_then_no_records(self):
        """Test when no matching operators are found, no records should be returned"""
        # Setup
        dataset = self.create_basic_dataset()
        dataset.add_iter_event()

        # Execute
        self.finder.get_api_stack_by_op_name(
            dataset,
            op_name=["IndexPutV2"],
            task_type=Constant.AI_CORE,
            disable_multiprocess=True
        )

        # Verify
        self.assertEqual(self.finder.get_stack_record(), [])

    def test_when_torch_to_npu_link_exists_then_stack_record_collected(self):
        """Test when torch_to_npu link exists, stack records should be collected"""
        ds = self.create_basic_dataset()
        # Add kernel info to ops_with_task_type
        task_name = "aclnnAddmm_MatMulComnmon_MatMulV2"
        task_type = Constant.AI_CORE
        task_tid = 2
        task_ts = "789.012"
        task_id = 10000
        ds.add_ops_with_task_type(task_name, task_type, task_tid, task_ts, task_id)

        # Add torch_to_npu link and ops_with_stack
        torch_op_name = "aclnnAddmm"
        torch_op_ts = "123.456"
        ds.add_torch_to_npu(f"s-{task_ts}", torch_op_ts)
        ds.add_ops_with_stack(torch_op_ts, torch_op_name, dataset_index=1)

        # Add iterator events with stack information
        ds.add_iter_event()  # index 0 - unrelated
        ds.add_iter_event(args={Constant.CALL_STACKS: "stack_line_1\nstack_line_2"})  # index 1 - has stack

        # Execute
        self.finder.get_api_stack_by_op_name(
            ds,
            op_name=[task_name],
            task_type=task_type,
            disable_multiprocess=True
        )

        # Verify stack records
        records = self.finder.get_stack_record()
        expected_record = [task_id, task_name, task_type, "stack_line_1\nstack_line_2"]
        self.assertEqual(records, [expected_record])

        # Verify OptimizeResult is populated correctly
        result = OptimizeResult()
        result.clear()
        self.finder.make_record(result)

        self.assertIn("operator stacks", result.data)
        self.assertEqual(result.data["operator stacks"]["headers"], ["Task ID", "op name", "op type", "code stacks"])
        self.assertIn(expected_record, result.data["operator stacks"]["data"])

    def test_when_only_acl_to_npu_link_exists_then_no_stack(self):
        """Test when only acl_to_npu exists, then no stack record"""
        ds = self.create_basic_dataset()
        # Add kernel info to ops_with_task_type
        task_name = "aclnnAddmm_MatMulComnmon_MatMulV2"
        task_type = Constant.AI_CORE
        task_tid = 2
        task_ts = "789.012"
        task_id = 10000
        ds.add_ops_with_task_type(task_name, task_type, task_tid, task_ts, task_id)

        # Add acl_to_npu link
        ds.add_acl_to_npu(task_ts)  # Only acl_to_npu, no torch_to_npu
        ds.add_iter_event()  # No stacks present

        # Execute
        self.finder.get_api_stack_by_op_name(
            ds,
            op_name=[task_name],
            task_type=task_type,
            disable_multiprocess=True
        )

        # Verify
        records = self.finder.get_stack_record()
        self.assertEqual(records, [])
        expected_matched_index = Constant.TIMELINE_ACL_TO_NPU_NO_STACK_CODE
        self.assertIn(expected_matched_index, self.finder.matched_index)


if __name__ == '__main__':
    unittest.main()
