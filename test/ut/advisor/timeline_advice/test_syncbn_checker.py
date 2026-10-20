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

from msprof_analyze.advisor.analyzer.schedule.syncbn.syncbn_checker import SyncBNChecker
from msprof_analyze.advisor.common.timeline.event import TimelineEvent
from test.ut.advisor.advisor_backend.tools.tool import recover_env


class TestSyncBNChecker(unittest.TestCase):
    @classmethod
    def tearDownClass(cls) -> None:
        recover_env()

    def setUp(self) -> None:
        rule_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
            os.path.dirname(os.path.dirname(os.path.realpath(__file__)))))), "msprof_analyze",
            "advisor", "rules", "cn", "sync_batchnorm.yaml")

        with open(rule_path, "rb") as file:
            self.rule = yaml.safe_load(file)

    def test_no_syncbn(self):
        dataset = self._get_mock_dataset(1, is_empty_dataset=True)

        checker = SyncBNChecker()
        checker.check_syncbn(dataset)
        self.assertFalse(checker.syncbn_issues)

    def test_syncbn_not_reach_threshold(self):
        dataset = self._get_mock_dataset(self.rule.get("max_syncbn_num") - 1, is_empty_dataset=False)
        checker = SyncBNChecker()
        checker.check_syncbn(dataset)
        self.assertFalse(checker.syncbn_issues)

    def test_found_slow_dataloader(self):
        dataset = self._get_mock_dataset(self.rule.get("max_syncbn_num") + 1, is_empty_dataset=False)
        checker = SyncBNChecker()
        checker.check_syncbn(dataset)
        self.assertTrue(checker.syncbn_issues)

        desc = self.rule.get("problem").format(syncbn_num=self.rule.get("max_syncbn_num") + 1)

        self.assertEqual(desc, checker.desc)

    def _get_mock_dataset(self, syncbn_num, is_empty_dataset=False):
        dataset = TimelineEvent()
        if is_empty_dataset:
            return dataset

        dataset["sync_batchnorm"] = []
        for _ in range(syncbn_num):
            dataset["sync_batchnorm"].append(TimelineEvent({"name": "SyncBatchNorm"}))
        return dataset


if __name__ == '__main__':
    tester = TestSyncBNChecker()
    tester.test_no_syncbn()
    tester.test_syncbn_not_reach_threshold()
    tester.test_found_slow_dataloader()
