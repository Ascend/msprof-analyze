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
from unittest.mock import patch
import pandas as pd

from msprof_analyze.prof_common.constant import Constant
from msprof_analyze.cluster_analyse.communication_group.base_communication_group import BaseCommunicationGroup


class TestBaseCommunicationGroup(unittest.TestCase):
    def setUp(self):
        # Initialize test parameters
        self.test_params = {
            Constant.COLLECTION_PATH: "./tmp",
            Constant.CLUSTER_ANALYSIS_OUTPUT_PATH: "./tmp/output",
            Constant.DATA_MAP: {0: "./tmp/rank0_ascend_pt", 1: "./tmp/rank1_ascend_pt"},
            Constant.DATA_TYPE: Constant.TEXT,
            Constant.ANALYSIS_MODE: Constant.ALL,
            Constant.IS_MSPROF: True
        }

        # Create test instance
        class TestCommunicationGroup(BaseCommunicationGroup):
            def read_communication_func(self, params):
                rank_id, _, _ = params
                return [rank_id, {"step1": {"collective": {}, "p2p": {}}}, {}]

            def dump_data(self):
                pass

        self.comm_group = TestCommunicationGroup(self.test_params)

    def test_add_collective_group_rank_map(self):
        """Test adding collective group rank mapping"""
        rank_id = 0
        comm_op_dict = {
            "hcom_broadcast__868_0_1@16207777699974144868": {},
            "hcom_allGather__508_0_1@14841742970657550508": {},
            "TotalOpInfo": {}  # Should be ignored
        }

        self.comm_group.add_collective_group_rank_map(rank_id, comm_op_dict)
        self.assertEqual(self.comm_group.collective_group_dict["16207777699974144868"], {0})

    def test_add_p2p_group_rank_map(self):
        """Test adding p2p group rank mapping"""
        comm_op_dict_rank_0 = {
            "hcom_send__226_1_1@14841742970657550226": {},
            "hcom_receive_226_1_1@14841742970657550226": {},
            "TotalOpInfo": {}  # Should be ignored
        }

        comm_op_dict_rank_4 = {
            "hcom_send__226_3_1@14841742970657550226": {},
            "hcom_receive_226_3_1@14841742970657550226": {},
            "TotalOpInfo": {}  # Should be ignored
        }

        self.comm_group.add_p2p_group_rank_map(0, comm_op_dict_rank_0)
        self.comm_group.add_p2p_group_rank_map(4, comm_op_dict_rank_4)
        self.assertEqual(self.comm_group.p2p_group_dict["14841742970657550226"], {0, 4})

    def test_generate_communication_group(self):
        """Test generation of communication groups"""
        self.comm_group.collective_group_dict["group1"] = {0, 1, 2}
        self.comm_group.p2p_group_dict["group2"] = {1, 2}

        self.comm_group.generate_communication_group()

        expected = {
            Constant.COLLECTIVE: [[0, 1, 2]],
            Constant.P2P: [[1, 2]]
        }
        self.assertEqual(self.comm_group.communication_group, expected)

    def test_add_communication_ops(self):
        """Test adding communication operations"""
        rank_id = "0"
        step_id = "step1"
        comm_op_type = "collective"
        comm_op_dict = {
            "AllReduce@group1": {"Communication Time Info": {}},
            "TotalOpInfo": {}
        }

        self.comm_group.add_communication_ops(rank_id, step_id, comm_op_type, comm_op_dict)
        self.assertEqual(len(self.comm_group.communication_ops), 1)

    def test_add_matrix_ops(self):
        """Test adding matrix operations"""
        rank_id = 0
        step_id = "step1"
        step_id_dict = {
            Constant.COLLECTIVE: {
                "AllReduce@group1": {"size": 1000},
                "TotalOpInfo": {}  # Should be ignored
            },
            Constant.P2P: {
                "Send@group2": {"size": 500}
            }
        }

        self.comm_group.add_matrix_ops(rank_id, step_id, step_id_dict)
        self.assertEqual(len(self.comm_group.matrix_ops), 2)

    @patch('msprof_analyze.prof_common.file_manager.FileManager.read_json_file')
    @patch('os.path.exists')
    def test_read_parallel_group_info(self, mock_exists, mock_read_json):
        """Test reading parallel group information"""
        mock_exists.return_value = True
        mock_read_json.return_value = {
            "distributed_args": {
                "tensor_model_parallel_size": 2,
                "pipeline_model_parallel_size": 2,
                "data_parallel_size": 2,
                "context_parallel_size": 1,
                "expert_model_parallel_size": 1,
                "sequence_parallel": True,
                "rank": 0,
                "world_size": 8
            },
            "parallel_group_info": {
                "100%enp189s0f1_55000_0_1738895521183247": {
                    "group_name": "dp",
                    "group_rank": 0,
                    "global_ranks": [0, 2]
                },
                "100%enp189s0f1_55000_0_1738895507756334": {
                    "group_name": "pp",
                    "group_rank": 0,
                    "global_ranks": [0, 4]
                }
            }
        }

        self.comm_group.read_parallel_group_info()

        expected_info = {
            "100%enp189s0f1_55000_0_1738895521183247": {
                "group_name": "dp",
                "group_rank": 0,
                "global_ranks": [0, 2]
            },
            "100%enp189s0f1_55000_0_1738895507756334": {
                "group_name": "pp",
                "group_rank": 0,
                "global_ranks": [0, 4]
            }
        }
        self.assertEqual(self.comm_group.parallel_group_info, expected_info)

    def test_analyze_parallel_group_info(self):
        """Test analyzing parallel group information"""
        # Setup test data
        self.comm_group.collective_group_dict = {"12809826787724806246": {0, 2}}
        self.comm_group.p2p_group_dict = {"9609979115979062393": {0, 4}}
        self.comm_group.parallel_group_info = {
            "100%enp189s0f1_55000_0_1738895521183247": {
                "group_name": "dp",
                "group_rank": 0,
                "global_ranks": [0, 2]
            },
            "100%enp189s0f1_55000_0_1738895507756334": {
                "group_name": "pp",
                "group_rank": 0,
                "global_ranks": [0, 4]
            }
        }

        self.comm_group.analyze_parallel_group_info()

        # Verify the resulting DataFrame
        self.assertIsInstance(self.comm_group.comm_group_parallel_info_df, pd.DataFrame)
        self.assertEqual(len(self.comm_group.comm_group_parallel_info_df), 2)

    def test_collect_comm_data(self):
        """Test collecting communication data"""
        self.comm_group.collective_group_dict = {"group1": {0, 1}}
        self.comm_group.communication_ops = [{"op": {}}]
        self.comm_group.matrix_ops = [{"matrix": {}}]
        self.comm_group.communication_group = {"collective": [[0, 1]]}
        self.comm_group.p2p_group_dict = {"6960437680420871035": {2, 3}}

        result = self.comm_group.collect_comm_data()

        expected = {
            Constant.COLLECTIVE_GROUP: {"group1": {0, 1}},
            Constant.COMMUNICATION_OPS: [{"op": {}}],
            Constant.MATRIX_OPS: [{"matrix": {}}],
            Constant.COMMUNICATION_GROUP: {"collective": [[0, 1]]},
            Constant.P2P_GROUP: {"6960437680420871035": {2, 3}}
        }
        self.assertEqual(result, expected)
