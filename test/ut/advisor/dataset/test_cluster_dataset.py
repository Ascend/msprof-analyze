# Copyright (c) 2025, Huawei Technologies Co., Ltd.
# All rights reserved.
#
# Licensed under the Apache License, Version 2.0  (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
import os
import shutil
import unittest
from unittest.mock import patch

from msprof_analyze.prof_common.constant import Constant
from msprof_analyze.advisor.dataset.cluster.cluster_dataset import ClusterDataset


class MockClusterDataset(ClusterDataset):
    def parse_from_text(self):
        return True

    def parse_from_db(self):
        return True


class TestClusterDataset(unittest.TestCase):
    @patch('msprof_analyze.advisor.dataset.cluster.cluster_dataset.ClusterDataset._parse')
    def setUp(self, mock_parse):
        mock_parse.return_value = True
        self.test_collection_path = "./ascend_pt"
        self.output_path = "./ascend_pt/output"
        self.test_data = {}
        # Create necessary directories
        os.makedirs(self.test_collection_path, exist_ok=True)
        os.makedirs(self.output_path, exist_ok=True)
        self.dataset = MockClusterDataset(collection_path=self.test_collection_path, data=self.test_data)

    def tearDown(self):
        # Clean up test directories
        if os.path.exists(self.test_collection_path):
            shutil.rmtree(self.test_collection_path)

    @patch('os.path.isdir')
    @patch('os.path.isfile')
    def test_is_cluster_analysis_result_exist_for_text(self, mock_isfile, mock_isdir):
        self.dataset.data_type = Constant.TEXT
        mock_isdir.return_value = True

        self.assertTrue(self.dataset.is_cluster_analysis_result_exist())
        expected_path = os.path.join(
            self.dataset.output_path,
            Constant.CLUSTER_ANALYSIS_OUTPUT,
        )
        mock_isdir.assert_called_once_with(expected_path)
        mock_isfile.assert_not_called()

        mock_isdir.return_value = False
        self.assertFalse(self.dataset.is_cluster_analysis_result_exist())

    @patch('os.path.isfile')
    def test_is_cluster_analysis_result_exist_for_db(self, mock_isfile):
        self.dataset.data_type = Constant.DB
        mock_isfile.return_value = True

        self.assertTrue(self.dataset.is_cluster_analysis_result_exist())
        expected_path = os.path.join(
            self.dataset.output_path,
            Constant.CLUSTER_ANALYSIS_OUTPUT,
            Constant.DB_CLUSTER_COMMUNICATION_ANALYZER,
        )
        mock_isfile.assert_called_once_with(expected_path)

        mock_isfile.return_value = False
        self.assertFalse(self.dataset.is_cluster_analysis_result_exist())

    @patch('msprof_analyze.advisor.dataset.cluster.cluster_dataset.Interface')
    @patch('msprof_analyze.advisor.dataset.cluster.cluster_dataset.ClusterDataset.is_cluster_analysis_result_exist')
    def test_cluster_analyze_skips_when_result_exists(self, mock_result_exist, mock_interface):
        mock_result_exist.return_value = True

        self.dataset.cluster_analyze()

        mock_interface.assert_not_called()

    @patch('msprof_analyze.advisor.dataset.cluster.cluster_dataset.Interface')
    @patch('msprof_analyze.advisor.dataset.cluster.cluster_dataset.ClusterDataset.is_cluster_analysis_result_exist')
    def test_cluster_analyze_runs_when_result_missing(self, mock_result_exist, mock_interface):
        self.dataset.data_type = Constant.DB
        mock_result_exist.return_value = False

        self.dataset.cluster_analyze()

        mock_interface.assert_called_once_with({
            Constant.PROFILING_PATH: self.dataset.collection_path,
            Constant.MODE: 'all',
            Constant.CLUSTER_ANALYSIS_OUTPUT_PATH: self.dataset.output_path,
            Constant.PARALLEL_MODE: Constant.CONCURRENT_MODE,
            Constant.EXPORT_TYPE: Constant.DB,
        })
        mock_interface.return_value.run.assert_called_once_with()
