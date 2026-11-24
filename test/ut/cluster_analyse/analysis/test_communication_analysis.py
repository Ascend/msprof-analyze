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
from unittest.mock import patch, MagicMock
import copy
import os
from collections import defaultdict
import shutil
from msprof_analyze.cluster_analyse.analysis.communication_analysis import CommunicationAnalysis
from msprof_analyze.prof_common.constant import Constant


class TestCommunicationAnalysis(unittest.TestCase):
    test_dir = os.path.join(os.path.dirname(__file__), 'DT_CLUSTER_PREPROCESS')

    def setUp(self):
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)
        self.output_path = os.path.join(self.test_dir, "cluster_analysis_output")
        os.makedirs(self.output_path, exist_ok=True)

        self.param = {
            Constant.COMM_DATA_DICT: {
                Constant.COMMUNICATION_OPS: {
                    'op1': {
                        '0': {
                            Constant.COMMUNICATION_TIME_INFO: {
                                Constant.WAIT_TIME_MS: 10,
                                Constant.TRANSIT_TIME_MS: 20,
                                Constant.SYNCHRONIZATION_TIME_MS: 5
                            },
                            Constant.COMMUNICATION_BANDWIDTH_INFO: {
                                'nccl': {
                                    Constant.TRANSIT_TIME_MS: 15,
                                    Constant.TRANSIT_SIZE_MB: 8,
                                    Constant.SIZE_DISTRIBUTION: {'1KB': [5, 10], '10KB': [3, 6]}
                                }
                            }
                        }
                    }
                }
            },
            'cluster_analysis_output_path': self.output_path
        }
        self.analysis = CommunicationAnalysis(self.param)

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_combine_size_distribution_when_data_contains_various_value(self):
        op_dict = {'1KB': [5, 10], '10KB': [3, 6]}
        total_dict = defaultdict(lambda: [0, 0])
        total_dict['1KB'] = [2, 4]
        total_dict['10KB'] = [1, 2]

        CommunicationAnalysis.combine_size_distribution(op_dict, total_dict)

        self.assertEqual(total_dict['1KB'], [7, 14])
        self.assertEqual(total_dict['10KB'], [4, 8])

    @patch('msprof_analyze.cluster_analyse.analysis.communication_analysis.increase_shared_value')
    @patch('msprof_analyze.cluster_analyse.analysis.communication_analysis.logger')
    def test_run_when_no_comm_ops(self, mock_logger, mock_increase):
        param_no_ops = copy.deepcopy(self.param)
        param_no_ops[Constant.COMM_DATA_DICT][Constant.COMMUNICATION_OPS] = None
        analysis = CommunicationAnalysis(param_no_ops)
        completed_processes = MagicMock()
        lock = MagicMock()
        analysis.run(completed_processes, lock)
        mock_increase.assert_called_once_with(completed_processes, lock)
        mock_logger.info.assert_called_with("CommunicationAnalysis completed")

    @patch.object(CommunicationAnalysis, 'split_op_by_group')
    @patch.object(CommunicationAnalysis, 'combine_ops_total_info')
    @patch.object(CommunicationAnalysis, 'dump_data')
    @patch('msprof_analyze.cluster_analyse.analysis.communication_analysis.increase_shared_value')
    @patch('msprof_analyze.cluster_analyse.analysis.communication_analysis.logger')
    def test_run_when_has_comm_ops(self, mock_logger, mock_increase, mock_dump, mock_combine, mock_split):
        completed_processes = MagicMock()
        lock = MagicMock()
        self.analysis.run(completed_processes, lock)
        mock_split.assert_called_once()
        mock_combine.assert_called_once()
        mock_dump.assert_called_once()
        mock_increase.assert_called_with(completed_processes, lock)
        mock_logger.info.assert_called_with("CommunicationAnalysis completed")

    def test_combine_time_info_when_contains_wait_transit_sync_time(self):
        com_info_dict = {
            Constant.WAIT_TIME_MS: 10,
            Constant.TRANSIT_TIME_MS: 20,
            Constant.SYNCHRONIZATION_TIME_MS: 5,
            Constant.START_TIMESTAMP: 1000
        }
        total_time_info_dict = {
            Constant.WAIT_TIME_MS: 15,
            Constant.TRANSIT_TIME_MS: 25,
            Constant.SYNCHRONIZATION_TIME_MS: 8
        }

        self.analysis.combine_time_info(com_info_dict, total_time_info_dict)
        self.assertEqual(total_time_info_dict[Constant.WAIT_TIME_MS], 25)
        self.assertEqual(total_time_info_dict[Constant.SYNCHRONIZATION_TIME_MS], 13)
        self.assertNotIn(Constant.START_TIMESTAMP, total_time_info_dict)

    def test_combine_bandwidth_info_when_contains_nccl_with_size_distribution(self):
        com_info_dict = {
            'nccl': {
                Constant.TRANSIT_TIME_MS: 15,
                Constant.TRANSIT_SIZE_MB: 8,
                Constant.SIZE_DISTRIBUTION: {'1KB': [5, 10], '10KB': [3, 6]}
            }
        }
        total_bandwidth_info_dict = {
            'nccl': {
                Constant.TRANSIT_TIME_MS: 10,
                Constant.TRANSIT_SIZE_MB: 5,
                Constant.SIZE_DISTRIBUTION: {'1KB': [2, 4], '10KB': [1, 2]}
            }
        }
        self.analysis.combine_bandwidth_info(com_info_dict, total_bandwidth_info_dict)
        self.assertEqual(total_bandwidth_info_dict['nccl'][Constant.SIZE_DISTRIBUTION]['10KB'], [4, 8])

    def test_combine_bandwidth_info_when_has_new_transport(self):
        com_info_dict = {
            'hccs': {
                Constant.TRANSIT_TIME_MS: 15,
                Constant.TRANSIT_SIZE_MB: 8,
                Constant.SIZE_DISTRIBUTION: {'1KB': [5, 10]}
            }
        }
        total_bandwidth_info_dict = {}
        self.analysis.combine_bandwidth_info(com_info_dict, total_bandwidth_info_dict)
        hccs_info = total_bandwidth_info_dict.get('hccs')
        self.assertIsNotNone(hccs_info)
        self.assertEqual(hccs_info.get(Constant.TRANSIT_TIME_MS), 15)
        self.assertEqual(hccs_info.get(Constant.TRANSIT_SIZE_MB), 8)

    @patch.object(CommunicationAnalysis, 'compute_ratio')
    def test_compute_time_ratio_when_contains_wait_transit_sync_time(self, mock_compute_ratio):
        mock_compute_ratio.side_effect = [0.333, 0.2]

        total_time_info_dict = {
            Constant.WAIT_TIME_MS: 10,
            Constant.TRANSIT_TIME_MS: 20,
            Constant.SYNCHRONIZATION_TIME_MS: 5
        }
        self.analysis.compute_time_ratio(total_time_info_dict)
        self.assertEqual(total_time_info_dict.get(Constant.WAIT_TIME_RATIO), 0.333)
        self.assertEqual(total_time_info_dict.get(Constant.SYNCHRONIZATION_TIME_RATIO), 0.2)
        self.assertEqual(mock_compute_ratio.call_count, 2)
        mock_compute_ratio.assert_any_call(10, 30)
        mock_compute_ratio.assert_any_call(5, 25)

    @patch.object(CommunicationAnalysis, 'compute_ratio')
    def test_compute_bandwidth_ratio_when_contains_nccl_transit_data(self, mock_compute_ratio):
        mock_compute_ratio.return_value = 0.533
        total_bandwidth_info_dict = {
            'nccl': {
                Constant.TRANSIT_TIME_MS: 15,
                Constant.TRANSIT_SIZE_MB: 8,
                Constant.BANDWIDTH_GB_S: 0.533,
                Constant.SIZE_DISTRIBUTION: {'1KB': [5, 10]}
            }
        }

        self.analysis.compute_bandwidth_ratio(total_bandwidth_info_dict)
        self.assertEqual(total_bandwidth_info_dict['nccl'][Constant.BANDWIDTH_GB_S], 0.533)
        mock_compute_ratio.assert_called_with(8, 15)

    def test_compute_total_info_when_contains_communication_time_and_bandwidth(self):
        comm_ops = {
            'hcom_broadcast__035_0_1@6960437680420871035': {
                '0': {
                    Constant.COMMUNICATION_TIME_INFO: {
                        Constant.WAIT_TIME_MS: 10,
                        Constant.TRANSIT_TIME_MS: 20,
                        Constant.SYNCHRONIZATION_TIME_MS: 5
                    },
                    Constant.COMMUNICATION_BANDWIDTH_INFO: {
                        'nccl': {
                            Constant.TRANSIT_TIME_MS: 15,
                            Constant.TRANSIT_SIZE_MB: 8,
                            Constant.SIZE_DISTRIBUTION: {'1KB': [5, 10]}
                        }
                    }
                }
            }
        }

        with patch.object(self.analysis, 'compute_time_ratio') as mock_time_ratio, \
             patch.object(self.analysis, 'compute_bandwidth_ratio') as mock_bandwidth_ratio:
            self.analysis.compute_total_info(comm_ops)
            total_info = comm_ops.get('Total Op Info@6960437680420871035')
            self.assertIsNotNone(total_info)
            rank_info = total_info.get('0')
            self.assertIsNotNone(rank_info)
            mock_time_ratio.assert_called_once()
            mock_bandwidth_ratio.assert_called_once()

    def test_dump_db_when_called_then_raise_runtime_error(self):
        with self.assertRaises(RuntimeError):
            self.analysis.dump_db()

    def test_level0_total_and_details_keep_unavailable_values(self):
        fields = self.analysis.TIME_BREAKDOWN_FIELDS
        calls = {
            f"hcom_allReduce__0_{i}_1@group": {
                "0": {
                    Constant.COMMUNICATION_TIME_INFO: {
                        Constant.START_TIMESTAMP: 1000 + i * 100,
                        Constant.ELAPSE_TIME_MS: duration,
                        **dict.fromkeys(fields, -1),
                        Constant.WAIT_TIME_RATIO: -1,
                        Constant.SYNCHRONIZATION_TIME_RATIO: -1,
                    },
                    Constant.COMMUNICATION_BANDWIDTH_INFO: {},
                }
            }
            for i, duration in enumerate((2.0, 3.0))
        }
        self.analysis.compute_total_info(calls)
        total = calls["Total Op Info@group"]["0"]
        self.assertEqual(total[Constant.COMMUNICATION_BANDWIDTH_INFO], {})
        time = total[Constant.COMMUNICATION_TIME_INFO]
        self.assertEqual(time[Constant.ELAPSE_TIME_MS], 5.0)
        self.assertEqual(time[Constant.START_TIMESTAMP], 0)
        for call in calls.values():
            for field in fields + (Constant.WAIT_TIME_RATIO, Constant.SYNCHRONIZATION_TIME_RATIO):
                self.assertEqual(call["0"][Constant.COMMUNICATION_TIME_INFO][field], -1)
        self.analysis.compute_total_info(calls)
        self.assertEqual(calls["Total Op Info@group"]["0"][Constant.COMMUNICATION_TIME_INFO][
            Constant.ELAPSE_TIME_MS], 5.0)

    def test_partial_breakdown_sums_valid_values_regardless_of_call_order(self):
        for values in ((-1, 2.0), (2.0, -1), (None, 2.0), (2.0, None)):
            with self.subTest(values=values):
                calls = {
                    f"op{i}@group": {"0": {
                        Constant.COMMUNICATION_TIME_INFO: {
                            Constant.ELAPSE_TIME_MS: 3.0,
                            Constant.TRANSIT_TIME_MS: value,
                            Constant.WAIT_TIME_MS: 1.0,
                            Constant.SYNCHRONIZATION_TIME_MS: 0.0,
                        },
                        Constant.COMMUNICATION_BANDWIDTH_INFO: {},
                    }} for i, value in enumerate(values)
                }
                self.analysis.compute_total_info(calls)
                time = calls["Total Op Info@group"]["0"][Constant.COMMUNICATION_TIME_INFO]
                self.assertEqual(time[Constant.ELAPSE_TIME_MS], 6.0)
                self.assertEqual(time[Constant.TRANSIT_TIME_MS], 2.0)
                self.assertEqual(time[Constant.IDLE_TIME_MS], -1)
                self.assertEqual(time[Constant.WAIT_TIME_MS], 2.0)
                self.assertEqual(time[Constant.SYNCHRONIZATION_TIME_MS], 0.0)
                self.assertEqual(time[Constant.WAIT_TIME_RATIO], 0.3333)
                self.assertEqual(time[Constant.SYNCHRONIZATION_TIME_RATIO], 0.0)

    def test_real_zero_breakdown_keeps_zero_ratios(self):
        time = dict.fromkeys(self.analysis.TIME_BREAKDOWN_FIELDS, 0)
        self.analysis.compute_time_ratio(time)
        self.assertEqual(time[Constant.WAIT_TIME_RATIO], 0)
        self.assertEqual(time[Constant.SYNCHRONIZATION_TIME_RATIO], 0)

    def test_detailed_total_preserves_legacy_time_fields(self):
        time = {
            Constant.START_TIMESTAMP: 1000,
            Constant.ELAPSE_TIME_MS: 5,
            Constant.TRANSIT_TIME_MS: 2,
            Constant.WAIT_TIME_MS: 1,
            Constant.SYNCHRONIZATION_TIME_MS: 0,
            Constant.IDLE_TIME_MS: 2,
            Constant.WAIT_TIME_RATIO: 0.3333,
            Constant.SYNCHRONIZATION_TIME_RATIO: 0,
        }
        calls = {"hcom_allReduce__0_0_1@group": {"0": {
            Constant.COMMUNICATION_TIME_INFO: copy.deepcopy(time),
            Constant.COMMUNICATION_BANDWIDTH_INFO: {},
        }}}
        self.analysis.compute_total_info(calls)
        total = calls["Total Op Info@group"]["0"][Constant.COMMUNICATION_TIME_INFO]
        expected = {k: v for k, v in time.items() if k != Constant.START_TIMESTAMP}
        self.assertEqual(dict(total), expected)
        self.assertEqual(calls["hcom_allReduce__0_0_1@group"]["0"][Constant.COMMUNICATION_TIME_INFO], time)

    def test_ratio_requires_paired_valid_calls_even_when_both_totals_exist(self):
        calls = {
            f"op{i}@group": {"0": {
                Constant.COMMUNICATION_TIME_INFO: {
                    Constant.ELAPSE_TIME_MS: 2,
                    Constant.TRANSIT_TIME_MS: transit,
                    Constant.WAIT_TIME_MS: wait,
                },
                Constant.COMMUNICATION_BANDWIDTH_INFO: {},
            }} for i, (transit, wait) in enumerate(((1, -1), (-1, 3)))
        }
        self.analysis.compute_total_info(calls)
        total = calls["Total Op Info@group"]["0"][Constant.COMMUNICATION_TIME_INFO]
        self.assertEqual(total[Constant.ELAPSE_TIME_MS], 4)
        self.assertEqual(total[Constant.TRANSIT_TIME_MS], 1)
        self.assertEqual(total[Constant.WAIT_TIME_MS], 3)
        self.assertEqual(total[Constant.WAIT_TIME_RATIO], -1)
