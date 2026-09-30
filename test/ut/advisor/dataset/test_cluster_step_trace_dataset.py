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
import pandas as pd

from msprof_analyze.advisor.dataset.cluster.cluster_dataset import ClusterStepTraceTimeDataset
from msprof_analyze.advisor.dataset.cluster.cluster_step_trace_time_bean import ClusterStepTraceTimeBean


class TestClusterStepTraceTimeDataset(unittest.TestCase):
    @patch('msprof_analyze.advisor.dataset.cluster.cluster_dataset.ClusterDataset._parse')
    def setUp(self, mock_parse):
        mock_parse.return_value = True
        self.test_collection_path = "./ascend_pt"
        self.test_data = {}
        self.dataset = ClusterStepTraceTimeDataset(self.test_collection_path, self.test_data)
        self.dataset._step_dict = defaultdict()
        self.dataset._stages = []

        # Test data for text format
        self.test_text_data = [
            ClusterStepTraceTimeBean({
                'Type': 'rank',
                'Step': '1',
                'Index': '0',
                'Computing': '14462809.01400388',
                'Communication(Not Overlapped)': '51556067.159996',
                'Free': '377397.078000026'
            }),
            ClusterStepTraceTimeBean({
                'Type': 'rank',
                'Step': '1',
                'Index': '1',
                'Computing': '14242056.739999993',
                'Communication(Not Overlapped)': '50741670.91999595',
                'Free': '645123.7600000406'
            }),
            ClusterStepTraceTimeBean({
                'Type': 'stage',
                'Step': '1',
                'Index': '(0, 1)',
                'Computing': '14462809.01400388',
                'Communication(Not Overlapped)': '51556067.159996',
                'Free': '645123.7600000406'
            })
        ]

        # Test data for DB format
        self.test_db_data = pd.DataFrame({
            'type': ['rank', 'rank', 'stage'],
            'step': ['1', '1', '1'],
            'index': ['0', '1', '(0, 1)'],
            'computing': [14462809.01400388, 14242056.739999993, 14462809.01400388],
            'communication_not_overlapped': [51556067.159996, 50741670.91999595, 51556067.159996],
            'free': [377397.078000026, 645123.7600000406, 645123.7600000406]
        })

        # Expected step dictionary
        self.expected_step_dict = {
            "1_0": [14462809.01400388, 51556067.159996, 377397.078000026],
            "1_1": [14242056.739999993, 50741670.91999595, 645123.7600000406]
        }

    def test_format_text_data(self):
        result = self.dataset.format_text_data(self.test_text_data)

        self.assertIn("1_0", result)
        self.assertIn("1_1", result)
        self.assertEqual(result["1_0"], self.expected_step_dict["1_0"])
        self.assertEqual(result["1_1"], self.expected_step_dict["1_1"])
        self.assertEqual(self.dataset._stages, [[0, 1]])

    def test_format_db_data(self):
        result = self.dataset.format_db_data(self.test_db_data)

        self.assertIn("1_0", result)
        self.assertIn("1_1", result)
        self.assertEqual(result["1_0"], self.expected_step_dict["1_0"])
        self.assertEqual(result["1_1"], self.expected_step_dict["1_1"])
        self.assertEqual(self.dataset._stages, [[0, 1]])

    def test_get_data(self):
        self.dataset._step_dict = self.expected_step_dict
        result = self.dataset.get_data()
        self.assertEqual(result, self.expected_step_dict)

    def test_get_stages(self):
        self.dataset._stages = [[0, 1], [2, 3]]
        result = self.dataset.get_stages()
        self.assertEqual(result, [[0, 1], [2, 3]])

    @patch('msprof_analyze.advisor.dataset.cluster.cluster_dataset.ClusterDataset.load_csv_data')
    def test_parse_from_text(self, mock_load_csv):
        mock_load_csv.return_value = self.test_text_data

        result = self.dataset.parse_from_text()
        self.assertTrue(result)
        self.assertIn("1_0", self.dataset._step_dict)
        self.assertIn("1_1", self.dataset._step_dict)
        self.assertEqual(self.dataset._step_dict["1_0"], self.expected_step_dict["1_0"])
        self.assertEqual(self.dataset._step_dict["1_1"], self.expected_step_dict["1_1"])

    @patch('msprof_analyze.prof_exports.communicaion_info_export.ClusterStepTraceTimeExport.read_export_db')
    def test_parse_from_db(self, mock_read_export_db):
        mock_read_export_db.return_value = self.test_db_data

        result = self.dataset.parse_from_db()
        self.assertTrue(result)
        self.assertIn("1_0", self.dataset._step_dict)
        self.assertIn("1_1", self.dataset._step_dict)
        self.assertEqual(self.dataset._step_dict["1_0"], self.expected_step_dict["1_0"])
        self.assertEqual(self.dataset._step_dict["1_1"], self.expected_step_dict["1_1"])
        self.assertEqual(self.dataset._stages, [[0, 1]])
