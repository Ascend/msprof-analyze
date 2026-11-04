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
import json
import os
import shutil
from msprof_analyze.cluster_analyse.analysis.comm_matrix_analysis import CommMatrixAnalysis
from msprof_analyze.prof_common.constant import Constant


class TestCommMatrixAnalysis(unittest.TestCase):
    test_dir = os.path.join(os.path.dirname(__file__), 'DT_CLUSTER_PREPROCESS')

    def setUp(self):
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)
        self.output_path = os.path.join(self.test_dir, "cluster_analysis_output")
        os.makedirs(self.output_path, exist_ok=True)

        self.param = {
            Constant.COMM_DATA_DICT: {
                Constant.MATRIX_OPS: {
                    'op1@group1': {
                        '0': {'0-1': {'transport_type': 'nccl', 'transit_time_ms': 10, 'transit_size_mb': 5}},
                        '1': {'0-1': {'transport_type': 'nccl', 'transit_time_ms': 15, 'transit_size_mb': 8}}
                    }
                }
            },
            'cluster_analysis_output_path': self.output_path
        }
        self.analysis = CommMatrixAnalysis(self.param)

    def tearDown(self):
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_combine_link_when_same_transport_type_and_op_name(self):
        link_info = {
            Constant.TRANSPORT_TYPE: 'nccl',
            Constant.TRANSIT_TIME_MS: 10,
            Constant.TRANSIT_SIZE_MB: 5,
            Constant.OP_NAME: 'op1'
        }
        single_link = {
            Constant.TRANSPORT_TYPE: 'nccl',
            Constant.TRANSIT_TIME_MS: 15,
            Constant.TRANSIT_SIZE_MB: 8,
            Constant.OP_NAME: 'op1'
        }

        CommMatrixAnalysis.combine_link(link_info, single_link)

        self.assertEqual(link_info[Constant.TRANSPORT_TYPE], 'nccl')
        self.assertEqual(link_info[Constant.TRANSIT_TIME_MS], 25)
        self.assertEqual(link_info[Constant.TRANSIT_SIZE_MB], 13)
        self.assertEqual(link_info[Constant.OP_NAME], 'op1')

    @patch('msprof_analyze.cluster_analyse.analysis.comm_matrix_analysis.increase_shared_value')
    @patch('msprof_analyze.cluster_analyse.analysis.comm_matrix_analysis.logger')
    def test_run_when_no_comm_ops(self, mock_logger, mock_increase):
        param_no_ops = copy.deepcopy(self.param)
        param_no_ops[Constant.COMM_DATA_DICT][Constant.MATRIX_OPS] = None
        analysis = CommMatrixAnalysis(param_no_ops)

        completed_processes = MagicMock()
        lock = MagicMock()

        analysis.run(completed_processes, lock)

        mock_increase.assert_called_once_with(completed_processes, lock)
        mock_logger.info.assert_called_with("CommMatrixAnalysis completed")

    @patch.object(CommMatrixAnalysis, 'split_op_by_group')
    @patch.object(CommMatrixAnalysis, 'combine_ops_total_info')
    @patch.object(CommMatrixAnalysis, 'dump_data')
    @patch('msprof_analyze.cluster_analyse.analysis.comm_matrix_analysis.increase_shared_value')
    @patch('msprof_analyze.cluster_analyse.analysis.comm_matrix_analysis.logger')
    def test_run_with_comm_ops(self, mock_logger, mock_increase, mock_dump, mock_combine, mock_split):
        completed_processes = MagicMock()
        lock = MagicMock()

        self.analysis.run(completed_processes, lock)

        mock_split.assert_called_once()
        mock_combine.assert_called_once()
        mock_dump.assert_called_once()
        mock_increase.assert_called_with(completed_processes, lock)
        mock_logger.info.assert_called_with("CommMatrixAnalysis completed")

    @patch.object(CommMatrixAnalysis, 'compute_ratio')
    def test_merge_same_links_when_same_op_group_and_link(self, mock_compute_ratio):
        mock_compute_ratio.return_value = 4.16

        step_dict = {
            'op1@group1': {
                '0': {'0-1': {
                    Constant.TRANSPORT_TYPE: 'nccl',
                    Constant.TRANSIT_TIME_MS: 10,
                    Constant.TRANSIT_SIZE_MB: 5,
                    Constant.OP_NAME: 'op1'
                }},
                '1': {'0-1': {
                    Constant.TRANSPORT_TYPE: 'nccl',
                    Constant.TRANSIT_TIME_MS: 15,
                    Constant.TRANSIT_SIZE_MB: 8,
                    Constant.OP_NAME: 'op1'
                }}
            }
        }
        with patch.object(self.analysis, 'get_parallel_group_info') as mock_group_info:
            mock_group_info.return_value = {'group1': {'0': 0, '1': 1}}

            self.analysis.merge_same_links(step_dict)
            self.assertIn('op1@group1', step_dict)
            self.assertIn('0-1', step_dict['op1@group1'])
            link_info = step_dict['op1@group1']['0-1']
            self.assertEqual(link_info[Constant.TRANSIT_TIME_MS], 25)
            self.assertEqual(link_info[Constant.TRANSIT_SIZE_MB], 13)
            self.assertEqual(link_info[Constant.BANDWIDTH_GB_S], 4.16)
            mock_compute_ratio.assert_called_with(13, 25)

    @patch.object(CommMatrixAnalysis, 'compute_ratio')
    def test_combine_link_info_when_multiple_ops_share_same_link_and_group(self, mock_compute_ratio):
        mock_compute_ratio.return_value = 4.0888888888888895
        step_dict = {
            'allgather-top1@6960437680420871035': {
                '0-1': {
                    Constant.TRANSPORT_TYPE: 'nccl',
                    Constant.TRANSIT_TIME_MS: 25,
                    Constant.TRANSIT_SIZE_MB: 13,
                    Constant.OP_NAME: 'op1'
                }
            },
            'allreduce-top1@6960437680420871035': {
                '0-1': {
                    Constant.TRANSPORT_TYPE: 'nccl',
                    Constant.TRANSIT_TIME_MS: 20,
                    Constant.TRANSIT_SIZE_MB: 10,
                    Constant.OP_NAME: 'op2'
                }
            }
        }
        with patch.object(self.analysis, 'check_add_op') as mock_check:
            mock_check.return_value = True
            self.analysis.combine_link_info(step_dict)
            total_op_info_key = 'Total Op Info@6960437680420871035'
            self.assertIn(total_op_info_key, step_dict)
            total_info = step_dict.get(total_op_info_key)
            self.assertIsNotNone(total_info)
            self.assertIn('0-1', total_info)
            link_info = total_info.get('0-1')
            self.assertIsNotNone(link_info)
            self.assertEqual(link_info.get(Constant.BANDWIDTH_GB_S), 4.0888888888888895)
            mock_compute_ratio.assert_called_with(23, 45)

    @patch.object(CommMatrixAnalysis, 'compute_ratio')
    def test_compute_ratio_when_input_int(self, mock_compute_ratio):
        mock_compute_ratio.return_value = 4.0
        result = self.analysis.compute_ratio(100, 200)
        self.assertEqual(result, 4.0)
        mock_compute_ratio.assert_called_with(100, 200)

    def test_compute_ratio_when_input_zero_time(self):
        result = self.analysis.compute_ratio(100, 0)
        self.assertEqual(result, 0)

    def test_dump_db_when_called_then_raise_runtime_error(self):
        with self.assertRaises(RuntimeError):
            self.analysis.dump_db()

    @patch('msprof_analyze.cluster_analyse.analysis.comm_matrix_analysis.increase_shared_value')
    def test_empty_matrix_ops_generate_no_json(self, mock_increase):
        analysis = CommMatrixAnalysis(
            {
                Constant.DATA_TYPE: Constant.TEXT,
                Constant.CLUSTER_ANALYSIS_OUTPUT_PATH: self.test_dir,
                Constant.COMM_DATA_DICT: {Constant.MATRIX_OPS: []},
            }
        )
        self.assertEqual(analysis.communication_ops, [])
        analysis.run(MagicMock(), MagicMock())
        self.assertFalse(os.path.exists(os.path.join(self.output_path, 'cluster_communication_matrix.json')))
        mock_increase.assert_called_once()

    @patch('msprof_analyze.cluster_analyse.analysis.comm_matrix_analysis.increase_shared_value')
    def test_matrix_ops_generate_json_with_operator_and_group_totals(self, mock_increase):
        group = 'group'
        operations = [
            {
                Constant.COMM_OP_TYPE: Constant.COLLECTIVE,
                Constant.GROUP_NAME: group,
                Constant.RANK_ID: 4,
                Constant.STEP_ID: 'step1',
                Constant.COMM_OP_NAME: f'hcom_allReduce__0_{index}_1@{group}',
                Constant.COMM_OP_INFO: {
                    '0-0': {
                        Constant.TRANSPORT_TYPE: 'LOCAL',
                        Constant.TRANSIT_TIME_MS: duration,
                        Constant.TRANSIT_SIZE_MB: size,
                    }
                },
            }
            for index, (duration, size) in enumerate(((2.0, 8.0), (1.0, 4.0)))
        ]
        analysis = CommMatrixAnalysis(
            {
                Constant.DATA_TYPE: Constant.TEXT,
                Constant.CLUSTER_ANALYSIS_OUTPUT_PATH: self.test_dir,
                Constant.DATA_MAP: {},
                Constant.COMM_DATA_DICT: {
                    Constant.MATRIX_OPS: operations,
                    Constant.COLLECTIVE_GROUP: {group: [4]},
                    Constant.P2P_GROUP: {},
                },
            }
        )
        self.assertEqual(len(analysis.communication_ops), 2)
        analysis.run(MagicMock(), MagicMock())
        with open(os.path.join(self.output_path, 'cluster_communication_matrix.json'), encoding='utf-8') as stream:
            data = json.load(stream)
        operators = data['(4,)']['step1']
        self.assertEqual(len(operators), 3)
        for index, (duration, size) in enumerate(((2.0, 8.0), (1.0, 4.0))):
            link = operators[f'hcom_allReduce__0_{index}_1@group']['4-4']
            self.assertEqual(link[Constant.TRANSIT_TIME_MS], duration)
            self.assertEqual(link[Constant.TRANSIT_SIZE_MB], size)
            self.assertEqual(link[Constant.BANDWIDTH_GB_S], 4.0)
        total = operators['Total Op Info@group']['4-4']
        self.assertEqual(total[Constant.TRANSIT_TIME_MS], 3.0)
        self.assertEqual(total[Constant.TRANSIT_SIZE_MB], 12.0)
        self.assertEqual(total[Constant.BANDWIDTH_GB_S], 4.0)
        mock_increase.assert_called_once()
