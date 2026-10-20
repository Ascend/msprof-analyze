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

from msprof_analyze.advisor.analyzer.schedule.synchronize_stream.synchronize_stream_checker import \
    SynchronizeStreamChecker
from msprof_analyze.advisor.common.timeline.event import TimelineEvent
from msprof_analyze.prof_common.constant import Constant
from msprof_analyze.advisor.utils.utils import safe_division
from test.ut.advisor.advisor_backend.tools.tool import recover_env


class TestSynchronizeChecker(unittest.TestCase):
    @classmethod
    def tearDownClass(cls) -> None:
        recover_env()

    def setUp(self) -> None:
        rule_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
            os.path.dirname(os.path.dirname(os.path.realpath(__file__)))))), "msprof_analyze",
            "advisor", "rules", "cn", "synchronize.yaml")

        with open(rule_path, "rb") as file:
            self.rule = yaml.safe_load(file)

    def test_check_synchronize_stream(self):
        checker = SynchronizeStreamChecker()
        ratio = self.rule.get("min_co_occurrence_ratio")
        co_occurrence_num = 10
        total_synchronize_stream_num = 10
        total_node_launch_num = int(safe_division(co_occurrence_num, float(ratio)))

        dataset = self._get_mock_dataset(co_occurrence_num, total_node_launch_num, total_synchronize_stream_num,
                                         is_empty_dataset=True)
        checker.check_synchronize(dataset)
        self.assertFalse(checker.synchronize_issues)

        dataset = self._get_mock_dataset(co_occurrence_num, total_node_launch_num, total_synchronize_stream_num)
        checker.check_synchronize(dataset)
        self.assertFalse(checker.synchronize_issues)

        dataset = self._get_mock_dataset(co_occurrence_num, total_node_launch_num - 1, total_synchronize_stream_num)
        checker.check_synchronize(dataset)
        self.assertTrue(checker.synchronize_issues)

    def _get_mock_dataset(self, co_occurrence_num, total_node_launch_num, total_synchronize_stream_num,
                          is_empty_dataset=False):
        dataset = TimelineEvent()
        if is_empty_dataset:
            return dataset

        co_occurrence_event_list = [TimelineEvent(dict(name=Constant.NODE_LAUNCH)),
                                    TimelineEvent(dict(name=Constant.SYNC_STREAM))] * co_occurrence_num

        synchronize_stream_event_list = [TimelineEvent(dict(name=Constant.SYNC_STREAM))] * (
                total_synchronize_stream_num - co_occurrence_num)

        node_launch_event_list = [TimelineEvent(dict(name=Constant.NODE_LAUNCH))] * (
                total_node_launch_num - co_occurrence_num)

        dataset[
            "synchronize_stream"] = co_occurrence_event_list + synchronize_stream_event_list + node_launch_event_list
        return dataset
