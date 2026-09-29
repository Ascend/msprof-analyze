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

import os
import unittest
import shutil

from unittest.mock import MagicMock, patch
from collections import defaultdict
from msprof_analyze.advisor.analyzer.cluster.communication_retransmission_checker import (
    CommunicationRetransmissionChecker, GroupStatistic
)

NAMESPACE = 'msprof_analyze.advisor.analyzer.cluster.communication_retransmission_checker'


class TestGroupStatistic(unittest.TestCase):
    """
    Test the GroupStatistic helper class.
    """

    def setUp(self):
        """
        Set up test fixtures.
        """
        self.min_transmission_time = 100.0
        self.group_statistic = GroupStatistic(self.min_transmission_time)

    def test_init_should_set_default_values(self):
        """
        Test GroupStatistic initialization.
        """
        self.assertFalse(self.group_statistic.retransmission_issue)
        self.assertIsInstance(self.group_statistic.abnormal_op_dict, dict)
        self.assertEqual(len(self.group_statistic.abnormal_op_dict), 0)

    def test_add_op_should_append_to_existing_op(self):
        """
        Test adding operation to existing op entry.
        """
        op_name = "test_op"

        # Add first operation
        hccl_info1 = MagicMock()
        hccl_info1.group = "group1"
        hccl_info1.step = "1"
        hccl_info1.rank = "0"
        hccl_info1.get_rdma_transit_size.return_value = 1024
        hccl_info1.get_rdma_transmit_time.return_value = 50.0
        hccl_info1.get_rdma_bandwidth.return_value = 20.5

        self.group_statistic.add_op(op_name, hccl_info1)

        # Add second operation
        hccl_info2 = MagicMock()
        hccl_info2.group = "group1"
        hccl_info2.step = "2"
        hccl_info2.rank = "1"
        hccl_info2.get_rdma_transit_size.return_value = 2048
        hccl_info2.get_rdma_transmit_time.return_value = 75.0
        hccl_info2.get_rdma_bandwidth.return_value = 30.0

        self.group_statistic.add_op(op_name, hccl_info2)

        self.assertEqual(len(self.group_statistic.abnormal_op_dict[op_name]), 2)


class TestCommunicationRetransmissionChecker(unittest.TestCase):
    """
    Test the CommunicationRetransmissionChecker class.
    """

    def setUp(self):
        self.test_dir = os.path.join(os.path.dirname(__file__), 'UT_DIR')
        self.mock_yaml_content = {
            "problem": "RDMA Retransmission Issue",
            "description": "Found {group_count} groups with retransmission issues",
            "min_retransmission_time": 100.0,
            "solutions": [
                {"solution1": {"desc": "Check network configuration"}},
                {"solution2": {"desc": "Optimize buffer sizes"}}
            ]
        }

        with patch(NAMESPACE + '.FileManager.read_yaml_file') as mock_read_yaml, \
             patch(NAMESPACE + '.AdditionalArgsManager') as mock_args_manager:

            mock_read_yaml.return_value = self.mock_yaml_content
            mock_args_manager.return_value.language = "en"

            self.checker = CommunicationRetransmissionChecker(step="1")

    def tearDown(self):
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)

    def test_init_should_set_default_values_will_set_correct_value_when_init_success(self):
        """
        Test CommunicationRetransmissionChecker init
        """
        self.assertFalse(self.checker.rdma_issues)
        self.assertEqual(self.checker.step_id, "1")
        self.assertEqual(self.checker.abnormal_group_count, 0)
        self.assertEqual(len(self.checker.abnormal_rdma_list), 0)

        self.assertIsInstance(self.checker.group_statistics, defaultdict)
        self.assertIsInstance(self.checker.suggestions, list)

        expected_headers = [
            "Communication group", "Op name", "Step id", "Rank id",
            "RDMA transmit size(MB)", "RDMA transmit time(ms)", "RDMA bandwidth"
        ]
        self.assertEqual(self.checker.headers, expected_headers)

    def test_multiple_groups_with_retransmission_should_return_correct_ans(self):
        """
        Test multiple groups with retransmission issues.
        """
        hccl_info1 = MagicMock()
        hccl_info1.elapse_time = 150.0
        hccl_info1.rdma_info = {'Transit Time(ms)': 120.0, 'Transit Size(MB)': 1024}
        hccl_info1.group = "group1"
        hccl_info1.step = "1"
        hccl_info1.rank = "0"
        hccl_info1.get_rdma_transit_size.return_value = 1024
        hccl_info1.get_rdma_transmit_time.return_value = 120.0
        hccl_info1.get_rdma_bandwidth.return_value = 8.5

        hccl_info2 = MagicMock()
        hccl_info2.elapse_time = 160.0
        hccl_info2.rdma_info = {'Transit Time(ms)': 130.0, 'Transit Size(MB)': 2048}
        hccl_info2.group = "group2"  # Different group
        hccl_info2.step = "1"
        hccl_info2.rank = "0"
        hccl_info2.get_rdma_transit_size.return_value = 2048
        hccl_info2.get_rdma_transmit_time.return_value = 130.0
        hccl_info2.get_rdma_bandwidth.return_value = 15.8

        hccl_dataset = MagicMock()
        hccl_dataset.hccl_dict = {
            "group1": {
                "op1": {
                    "1": [hccl_info1]
                }
            },
            "group2": {
                "op1": {
                    "1": [hccl_info2]
                }
            }
        }

        self.checker.check_retransmission(hccl_dataset)

        self.assertTrue(self.checker.rdma_issues)
        self.assertEqual(self.checker.abnormal_group_count, 2)
        self.assertEqual(len(self.checker.abnormal_rdma_list), 2)


if __name__ == '__main__':
    unittest.main()
