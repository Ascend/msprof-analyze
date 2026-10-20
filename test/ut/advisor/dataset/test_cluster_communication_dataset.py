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
import shutil
import unittest
from unittest.mock import patch
from collections import defaultdict

import pandas as pd

from msprof_analyze.advisor.dataset.cluster.cluster_dataset import ClusterCommunicationDataset


class TestClusterCommunicationDataset(unittest.TestCase):

    def tearDown(self):
        if os.path.exists(self.tmp_dir):
            shutil.rmtree(self.tmp_dir)

    @patch('msprof_analyze.advisor.dataset.cluster.cluster_dataset.ClusterDataset._parse')
    def setUp(self, mock_parse):
        mock_parse.return_value = True
        self.tmp_dir = "./ascend_pt"
        self.test_data = {}
        self.dataset = ClusterCommunicationDataset(self.tmp_dir, self.test_data)
        self.dataset.rank_bw_dict = defaultdict(self.dataset.create_rank_bw_dict)
        self.dataset.hccl_dict = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))

        # Test data for process_hccl_info
        self.test_communication_json = {
            "(4, 5, 6, 7)": {
                "step": {
                    "hcom_allGather__114_4_1@1046397798680881114": {
                        "0": {
                            "Communication Time Info": {
                                "Start Timestamp(us)": 1726054679972284.8,
                                "Elapse Time(ms)": 15.409448,
                                "Transit Time(ms)": 9.251282,
                                "Wait Time(ms)": 0.7250960000000003,
                                "Synchronization Time(ms)": 0.48189,
                                "Idle Time(ms)": 5.433069999999999,
                                "Wait Time Ratio": 0.0727,
                                "Synchronization Time Ratio": 0.0495
                            },
                            "Communication Bandwidth Info": {
                                "RDMA": {
                                    "Transit Size(MB)": 20.31616000000001,
                                    "Transit Time(ms)": 9.251282,
                                    "Bandwidth(GB/s)": 2.196,
                                    "Large Packet Ratio": 1.0,
                                    "Size Distribution": {
                                        "0.65536": [31, 9.251282]
                                    }
                                },
                                "SDMA": {
                                    "Transit Size(MB)": 20.971520000000012,
                                    "Transit Time(ms)": 1.887276,
                                    "Bandwidth(GB/s)": 11.1121,
                                    "Large Packet Ratio": 0.0,
                                    "Size Distribution": {}
                                }
                            }
                        },
                        "4": {
                            "Communication Time Info": {
                                "Start Timestamp(us)": 1726054679972376.8,
                                "Elapse Time(ms)": 15.489652,
                                "Transit Time(ms)": 9.968556000000003,
                                "Wait Time(ms)": 0.47790800000000044,
                                "Synchronization Time(ms)": 0.465048,
                                "Idle Time(ms)": 5.043187999999996,
                                "Wait Time Ratio": 0.0457,
                                "Synchronization Time Ratio": 0.0446
                            },
                            "Communication Bandwidth Info": {
                                "RDMA": {
                                    "Transit Size(MB)": 20.31616000000001,
                                    "Transit Time(ms)": 9.968556000000003,
                                    "Bandwidth(GB/s)": 2.038,
                                    "Large Packet Ratio": 1.0,
                                    "Size Distribution": {
                                        "0.65536": [31, 9.968556000000003]
                                    }
                                },
                                "SDMA": {
                                    "Transit Size(MB)": 20.971520000000012,
                                    "Transit Time(ms)": 4.160496,
                                    "Bandwidth(GB/s)": 5.0406,
                                    "Large Packet Ratio": 0.0,
                                    "Size Distribution": {}
                                }
                            }
                        }
                    }
                }
            }
        }

        self.test_hccl_df = pd.DataFrame([
            {
                "rank_set": "(0, 4, 8, 12)",
                "hccl_op_name": "hcom_allGather__114_4_1",
                "group_name": "1046397798680881114",
                "start_timestamp": 1.72605467997292e+15,
                "elapsed_time": 14.370828,
                "step": "step",
                "rank_id": "12",
                "sdma_dict": '{"Transport Type":"SDMA","Transit Time(ms)":1.1302,"Transit Size(MB)":20.97152,'
                             '"Bandwidth(GB/s)":18.5556,"Large Packet Ratio":0}',
                "rdma_dict": '{"Transport Type":"RDMA","Transit Time(ms)":9.251294,"Transit Size(MB)":20.31616,'
                             '"Bandwidth(GB/s)":2.196,"Large Packet Ratio":1}'
            }
        ])
        self.test_bandwidth_df = pd.DataFrame([
            {
                "band_type": "SDMA",
                "step": "step",
                "rank_id": 12,
                "transit_time": 2.0,
                "transit_size": 20.0
            },
            {
                "band_type": "RDMA",
                "step": "step",
                "rank_id": 12,
                "transit_time": 2.5,
                "transit_size": 50.0
            },
            {
                "band_type": "SDMA",
                "step": "step",
                "rank_id": 12,
                "transit_time": 2.0,
                "transit_size": 20.0
            },
            {
                "band_type": "RDMA",
                "step": "step",
                "rank_id": 12,
                "transit_time": 2.5,
                "transit_size": 50.0
            }
        ])

    def test_compute_ratio(self):
        self.assertEqual(self.dataset.compute_ratio(10.0, 2.0), 5.0)
        self.assertEqual(self.dataset.compute_ratio(10.0, 0.0), 0)
        self.assertEqual(self.dataset.compute_ratio(0.0, 2.0), 0)

    def test_process_hccl_info(self):
        self.dataset.process(self.test_communication_json)

        # Verify the HCCL info is properly stored
        self.assertIn('(4, 5, 6, 7)', self.dataset.hccl_dict)
        self.assertIn('hcom_allGather__114_4_1', self.dataset.hccl_dict['(4, 5, 6, 7)'])
        self.assertEqual(len(self.dataset.hccl_dict['(4, 5, 6, 7)']['hcom_allGather__114_4_1']['step']), 2)

        # Verify HCCL info content for rank 0
        hccl_info_0 = self.dataset.hccl_dict['(4, 5, 6, 7)']['hcom_allGather__114_4_1']['step'][0]
        self.assertEqual(hccl_info_0.group, '(4, 5, 6, 7)')
        self.assertEqual(hccl_info_0.step, 'step')
        self.assertEqual(hccl_info_0.rank, '0')
        self.assertEqual(hccl_info_0.name, 'hcom_allGather__114_4_1')
        self.assertEqual(hccl_info_0.ts, 1726054679972284.8)
        self.assertEqual(hccl_info_0.elapse_time, 15.409448)
        self.assertEqual(hccl_info_0.sdma_info, {
            "Transit Size(MB)": 20.971520000000012,
            "Transit Time(ms)": 1.887276,
            "Bandwidth(GB/s)": 11.1121,
            "Large Packet Ratio": 0.0,
            "Size Distribution": {}
        })
        self.assertEqual(hccl_info_0.rdma_info, {
            "Transit Size(MB)": 20.31616000000001,
            "Transit Time(ms)": 9.251282,
            "Bandwidth(GB/s)": 2.196,
            "Large Packet Ratio": 1.0,
            "Size Distribution": {
                "0.65536": [31, 9.251282]
            }
        })

        # Verify HCCL info content for rank 4
        hccl_info_4 = self.dataset.hccl_dict['(4, 5, 6, 7)']['hcom_allGather__114_4_1']['step'][1]
        self.assertEqual(hccl_info_4.group, '(4, 5, 6, 7)')
        self.assertEqual(hccl_info_4.step, 'step')
        self.assertEqual(hccl_info_4.rank, '4')
        self.assertEqual(hccl_info_4.name, 'hcom_allGather__114_4_1')
        self.assertEqual(hccl_info_4.ts, 1726054679972376.8)
        self.assertEqual(hccl_info_4.elapse_time, 15.489652)
        self.assertEqual(hccl_info_4.sdma_info, {
            "Transit Size(MB)": 20.971520000000012,
            "Transit Time(ms)": 4.160496,
            "Bandwidth(GB/s)": 5.0406,
            "Large Packet Ratio": 0.0,
            "Size Distribution": {}
        })
        self.assertEqual(hccl_info_4.rdma_info, {
            "Transit Size(MB)": 20.31616000000001,
            "Transit Time(ms)": 9.968556000000003,
            "Bandwidth(GB/s)": 2.038,
            "Large Packet Ratio": 1.0,
            "Size Distribution": {
                "0.65536": [31, 9.968556000000003]
            }
        })

        # Test RDMA related methods
        self.assertEqual(hccl_info_0.get_rdma_transmit_time(), 9.251282)
        self.assertEqual(hccl_info_0.get_rdma_transit_size(), 20.31616000000001)
        self.assertEqual(hccl_info_0.get_rdma_bandwidth(), 2.196)

        self.assertEqual(hccl_info_4.get_rdma_transmit_time(), 9.968556000000003)
        self.assertEqual(hccl_info_4.get_rdma_transit_size(), 20.31616000000001)
        self.assertEqual(hccl_info_4.get_rdma_bandwidth(), 2.038)

    def test_compute_bandwidth(self):
        # Test with valid data
        step = "step"
        op_dict_1 = {
            '0': {
                'Communication Bandwidth Info': {
                    'SDMA': {
                        'Transit Time(ms)': 2.0,
                        'Transit Size(MB)': 20.0
                    },
                    'RDMA': {
                        'Transit Time(ms)': 2.5,
                        'Transit Size(MB)': 50.0
                    }
                }
            }
        }
        op_dict_2 = {
            '0': {
                'Communication Bandwidth Info': {
                    'SDMA': {
                        'Transit Time(ms)': 2.0,
                        'Transit Size(MB)': 20.0
                    },
                    'RDMA': {
                        'Transit Time(ms)': 2.5,
                        'Transit Size(MB)': 50.0
                    }
                }
            }
        }

        self.dataset.compute_bandwidth(step, op_dict_1)
        self.dataset.compute_bandwidth(step, op_dict_2)

        # Verify bandwidth calculations for rank 0
        self.assertEqual(self.dataset.rank_bw_dict["step_0"]["SDMA time(ms)"], 4.0)  # 2.0 + 2.0
        self.assertEqual(self.dataset.rank_bw_dict["step_0"]["SDMA size(mb)"], 40.0)  # 20.0 + 20.0
        self.assertEqual(self.dataset.rank_bw_dict["step_0"]["RDMA time(ms)"], 5.0)  # 2.5 + 2.5
        self.assertEqual(self.dataset.rank_bw_dict["step_0"]["RDMA size(mb)"], 100.0)  # 50.0 + 50.0
        self.assertEqual(self.dataset.rank_bw_dict["step_0"]["SDMA bandwidth(GB/s)"], 10.0)  # 40.0 / 4.0
        self.assertEqual(self.dataset.rank_bw_dict["step_0"]["RDMA bandwidth(GB/s)"], 20.0)  # 100.0 / 5.0

        # Test with invalid rank
        with self.assertRaises(ValueError):
            self.dataset.compute_bandwidth(step, {'invalid': {}})

    def test_process_hccl_info_with_invalid_data(self):
        # Test with invalid communication data structure
        invalid_json = {
            'group1': {
                'step1': {
                    'op1@0': {
                        '0': {}  # Missing Communication Bandwidth Info
                    }
                }
            }
        }
        self.dataset.process(invalid_json)
        # Should not raise exception but should not add any bandwidth info
        self.assertEqual(len(self.dataset.rank_bw_dict), 0)

    @patch('msprof_analyze.prof_exports.communicaion_info_export.ClusterBandwidthInfoExport.read_export_db')
    def test_process_bandwidth_db(self, mock_read_export_db):
        # Mock the read_export_db method to return our test DataFrame
        mock_read_export_db.return_value = self.test_bandwidth_df

        # Call the method under test
        self.dataset.process_bandwidth_db(None)

        # Verify the bandwidth calculations
        self.assertIn("-1_12", self.dataset.rank_bw_dict)

        # Check SDMA values
        self.assertEqual(self.dataset.rank_bw_dict["-1_12"]["SDMA size(mb)"], 40.0)  # 20.0 + 20.0
        self.assertEqual(self.dataset.rank_bw_dict["-1_12"]["SDMA time(ms)"], 4.0)  # 2.0 + 2.0
        self.assertEqual(self.dataset.rank_bw_dict["-1_12"]["SDMA bandwidth(GB/s)"], 10.0)  # 40.0 / 4.0

        # Check RDMA values
        self.assertEqual(self.dataset.rank_bw_dict["-1_12"]["RDMA size(mb)"], 100.0)  # 50.0 + 50.0
        self.assertEqual(self.dataset.rank_bw_dict["-1_12"]["RDMA time(ms)"], 5.0)  # 2.5 + 2.5
        self.assertEqual(self.dataset.rank_bw_dict["-1_12"]["RDMA bandwidth(GB/s)"], 20.0)  # 100.0 / 5.0

    @patch('msprof_analyze.prof_exports.communicaion_info_export.ClusterCommunicationInfoExport.read_export_db')
    def test_process_hccl_info_db(self, mock_read_export_db):
        # Mock the read_export_db to return test data
        mock_read_export_db.return_value = self.test_hccl_df

        # Call the method under test
        self.dataset.process_hccl_info_db(None)

        # Verify the HCCL info is properly stored
        self.assertIn('(0, 4, 8, 12)', self.dataset.hccl_dict)
        self.assertIn('hcom_allGather__114_4_1', self.dataset.hccl_dict['(0, 4, 8, 12)'])
        self.assertEqual(len(self.dataset.hccl_dict['(0, 4, 8, 12)']['hcom_allGather__114_4_1']['step']), 1)

        # Verify HCCL info content for rank 0
        hccl_info_0 = self.dataset.hccl_dict['(0, 4, 8, 12)']['hcom_allGather__114_4_1']['step'][0]
        self.assertEqual(hccl_info_0.group, '(0, 4, 8, 12)')
        self.assertEqual(hccl_info_0.step, 'step')
        self.assertEqual(hccl_info_0.rank, '12')
        self.assertEqual(hccl_info_0.name, 'hcom_allGather__114_4_1')
        self.assertEqual(hccl_info_0.elapse_time, 14.370828)

        # Test RDMA related methods for rank 0
        self.assertEqual(hccl_info_0.get_rdma_transmit_time(), 9.251294)
        self.assertEqual(hccl_info_0.get_rdma_transit_size(), 20.31616)
        self.assertEqual(hccl_info_0.get_rdma_bandwidth(), 2.196)
