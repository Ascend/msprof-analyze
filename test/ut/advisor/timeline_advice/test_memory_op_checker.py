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
import os
import yaml

from msprof_analyze.advisor.analyzer.memory.memory_checker import MemoryOpsChecker
from msprof_analyze.advisor.common.timeline.event import TimelineEvent
from test.ut.advisor.advisor_backend.tools.tool import recover_env


class TestMemOpChecker(unittest.TestCase):
    @classmethod
    def tearDownClass(cls) -> None:
        recover_env()

    def setUp(self) -> None:
        rule_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
            os.path.dirname(os.path.dirname(os.path.realpath(__file__)))))), "msprof_analyze",
            "advisor", "rules", "cn", "memory.yaml")

        with open(rule_path, "rb") as file:
            self.rule = yaml.safe_load(file)

    def test_no_mem_op(self):
        dataset = self._get_mock_dataset(1, is_empty_dataset=True)

        checker = MemoryOpsChecker()
        checker.check_memory_ops(dataset)
        self.assertFalse(checker.memory_issues)

    def test_mem_op_not_reach_threshold(self):
        dataset = self._get_mock_dataset(1, is_empty_dataset=False)

        checker = MemoryOpsChecker()
        checker.check_memory_ops(dataset)
        self.assertFalse(checker.memory_issues)

    def test_mem_op_reach_threshold(self):
        dataset = self._get_mock_dataset(1, 1000000, is_empty_dataset=False)

        checker = MemoryOpsChecker()
        checker.check_memory_ops(dataset)
        self.assertTrue(checker.memory_issues)

    def _get_mock_dataset(self, mem_op_num, mem_op_total_dur=1000, is_empty_dataset=False):
        dataset = TimelineEvent()
        if is_empty_dataset:
            return dataset

        mem_op_info = TimelineEvent()
        for i in range(mem_op_num):
            mem_op_info[f"mock_mem_op_{i}"] = TimelineEvent({"total_dur": mem_op_total_dur, "count": 10})

        dataset["memory_ops"] = TimelineEvent({"mem_op_info": mem_op_info, "rule": TimelineEvent(self.rule)})
        return dataset


if __name__ == '__main__':
    tester = TestMemOpChecker()
    tester.test_no_mem_op()
    tester.test_mem_op_not_reach_threshold()
    tester.test_mem_op_reach_threshold()
