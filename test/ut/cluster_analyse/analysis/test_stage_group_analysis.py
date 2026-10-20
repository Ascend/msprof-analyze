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

from msprof_analyze.cluster_analyse.analysis.stage_group_analysis import StageInfoAnalysis
from msprof_analyze.cluster_analyse.common_func.table_constant import TableConstant
from msprof_analyze.prof_common.constant import Constant


class TestStageInfoAnalysis(unittest.TestCase):
    """Unit tests for StageInfoAnalysis class"""

    def setUp(self):
        """Set up test fixtures before each test method"""
        self.base_param = {
            Constant.CLUSTER_ANALYSIS_OUTPUT_PATH: "/test/path",
            Constant.DATA_TYPE: Constant.TEXT,
            Constant.COMM_DATA_DICT: {}
        }

        # Sample communication group data
        self.sample_comm_group_data = [
            {
                TableConstant.TYPE: Constant.COLLECTIVE,
                TableConstant.RANK_SET: {0, 1, 2, 3},
                TableConstant.GROUP_NAME: "group1",
                TableConstant.GROUP_ID: "g1",
                TableConstant.PG_NAME: "default_group"
            },
            {
                TableConstant.TYPE: Constant.P2P,
                TableConstant.RANK_SET: {0, 2},
                TableConstant.GROUP_NAME: "group2",
                TableConstant.GROUP_ID: "g2",
                TableConstant.PG_NAME: "pp"
            },
            {
                TableConstant.TYPE: Constant.P2P,
                TableConstant.RANK_SET: {1, 3},
                TableConstant.GROUP_NAME: "group3",
                TableConstant.GROUP_ID: "g3",
                TableConstant.PG_NAME: "pp"
            },
            {
                TableConstant.TYPE: Constant.COLLECTIVE,
                TableConstant.RANK_SET: {0, 1},
                TableConstant.GROUP_NAME: "group4",
                TableConstant.GROUP_ID: "g4",
                TableConstant.PG_NAME: "dp"
            },
            {
                TableConstant.TYPE: Constant.COLLECTIVE,
                TableConstant.RANK_SET: {2, 3},
                TableConstant.GROUP_NAME: "group5",
                TableConstant.GROUP_ID: "g5",
                TableConstant.PG_NAME: "dp"
            }
        ]

    def test_init_when_valid_params_then_initialize_correctly(self):
        """Test initialization with valid parameters"""
        param = self.base_param.copy()
        stage_analysis = StageInfoAnalysis(param)
        self.assertEqual(stage_analysis.cluster_analysis_output_path, "/test/path")
        self.assertEqual(stage_analysis.data_type, Constant.TEXT)
        self.assertEqual(stage_analysis.communication_data_dict, {})
        self.assertEqual(stage_analysis.collective_group_dict, {})
        self.assertEqual(stage_analysis.p2p_link, [])
        self.assertEqual(stage_analysis.p2p_union_group, [])
        self.assertEqual(stage_analysis.stage_group, [])

    def test_prepare_data_when_comm_data_in_dict_then_extract_successfully(self):
        """Test prepare_data when communication data is provided in dict"""
        param = self.base_param.copy()
        param[Constant.COMM_DATA_DICT] = {
            Constant.KEY_COMM_GROUP_PARALLEL_INFO: self.sample_comm_group_data
        }
        stage_analysis = StageInfoAnalysis(param)
        result = stage_analysis.prepare_data()

        self.assertTrue(result)
        self.assertEqual(len(stage_analysis.collective_group_dict), 3)
        self.assertEqual(len(stage_analysis.p2p_link), 2)

    def test_prepare_data_when_no_comm_data_then_return_false(self):
        """Test prepare_data when no communication data available"""
        # Given no communication data
        stage_analysis = StageInfoAnalysis(self.base_param)

        # When calling prepare_data with mocked load_communication_group_df returning None
        with patch.object(stage_analysis, 'load_communication_group_df', return_value=None):
            result = stage_analysis.prepare_data()

        # Then should return False
        self.assertFalse(result)

    def test_extract_infos_when_valid_dataframe_then_extract_correctly(self):
        """Test extract_infos with valid dataframe"""
        # Given valid dataframe
        df = pd.DataFrame(self.sample_comm_group_data)
        stage_analysis = StageInfoAnalysis(self.base_param)

        # When calling extract_infos
        result = stage_analysis.extract_infos(df)

        # Then should extract collective and p2p groups correctly
        self.assertTrue(result)
        self.assertEqual(len(stage_analysis.collective_group_dict), 3)
        self.assertEqual(len(stage_analysis.p2p_link), 2)
        self.assertIn("group1", stage_analysis.collective_group_dict)
        self.assertEqual(stage_analysis.collective_group_dict["group1"], {0, 1, 2, 3})

    def test_extract_infos_when_no_p2p_groups_then_return_false(self):
        """Test extract_infos when no p2p groups found"""
        data = [
            {
                TableConstant.TYPE: Constant.COLLECTIVE,
                TableConstant.RANK_SET: {0, 1, 2, 3},
                TableConstant.GROUP_NAME: "group1",
                TableConstant.GROUP_ID: "g1",
                TableConstant.PG_NAME: "default_group"
            }
        ]
        df = pd.DataFrame(data)
        stage_analysis = StageInfoAnalysis(self.base_param)
        result = stage_analysis.extract_infos(df)
        # Then should return False due to no p2p groups
        self.assertFalse(result)
        self.assertEqual(len(stage_analysis.collective_group_dict), 1)
        self.assertEqual(len(stage_analysis.p2p_link), 0)

    def test_extract_infos_when_none_dataframe_then_return_false(self):
        """Test extract_infos with None dataframe"""
        # Given None dataframe, should return False
        stage_analysis = StageInfoAnalysis(self.base_param)
        result = stage_analysis.extract_infos(None)
        self.assertFalse(result)

    def test_generate_p2p_union_group_when_disconnected_groups_then_create_separate_groups(self):
        """Test generate_p2p_union_group with disconnected p2p groups"""
        stage_analysis = StageInfoAnalysis(self.base_param)
        stage_analysis.p2p_link = [{0, 1}, {2, 3}, {4, 5}]
        stage_analysis.generate_p2p_union_group()
        self.assertEqual(len(stage_analysis.p2p_union_group), 3)
        self.assertIn({0, 1}, stage_analysis.p2p_union_group)
        self.assertIn({2, 3}, stage_analysis.p2p_union_group)
        self.assertIn({4, 5}, stage_analysis.p2p_union_group)

    def test_generate_p2p_union_group_when_connected_groups_then_merge_correctly(self):
        """Test generate_p2p_union_group with connected p2p groups"""
        stage_analysis = StageInfoAnalysis(self.base_param)
        stage_analysis.p2p_link = [{0, 1}, {1, 2}, {3, 4}]
        stage_analysis.generate_p2p_union_group()
        self.assertEqual(len(stage_analysis.p2p_union_group), 2)
        # {0,1} and {1,2} should be merged into {0,1,2}
        self.assertIn({0, 1, 2}, stage_analysis.p2p_union_group)
        self.assertIn({3, 4}, stage_analysis.p2p_union_group)

    def test_generate_stage_group_when_valid_collective_groups_then_generate_stages(self):
        """Test generate_stage_group with valid collective groups"""
        stage_analysis = StageInfoAnalysis(self.base_param)
        stage_analysis.collective_group_dict = {
            "group1": {4, 5},
            "group2": {5, 7},
            "group3": {0, 1, 2, 3, 4, 5, 6, 7},
            "group4": {0, 1},
            "group5": {1, 3},
            "group6": {2, 3},
            "group7": {6, 7},
        }
        stage_analysis.p2p_union_group = [{0, 4}, {1, 5}, {2, 6}, {3, 7}]
        stage_analysis.generate_stage_group()
        self.assertEqual(len(stage_analysis.stage_group), 2)
        # Each collective group should become a stage
        self.assertIn([0, 1, 2, 3], stage_analysis.stage_group)
        self.assertIn([4, 5, 6, 7], stage_analysis.stage_group)

    def test_whether_valid_comm_group_when_valid_group_then_return_true(self):
        """Test whether_valid_comm_group with valid communication group"""
        stage_analysis = StageInfoAnalysis(self.base_param)
        stage_analysis.p2p_union_group = [{0, 1}, {2, 3}]
        rank_set = {0, 4, 5}  # Only intersects with one p2p group
        result = stage_analysis.whether_valid_comm_group(rank_set)
        self.assertTrue(result)

    def test_whether_valid_comm_group_when_invalid_group_then_return_false(self):
        """Test whether_valid_comm_group with invalid communication group"""
        # Given invalid communication group
        stage_analysis = StageInfoAnalysis(self.base_param)
        stage_analysis.p2p_union_group = [{0, 1}, {2, 3}]
        rank_set = {0, 1, 2}  # Intersects with multiple p2p groups
        result = stage_analysis.whether_valid_comm_group(rank_set)
        self.assertFalse(result)

    @patch('os.path.exists')
    def test_load_communication_group_df_when_cluster_output_not_exist_when_return_none(self, mock_exists):
        mock_exists.return_value = False
        stage_analysis = StageInfoAnalysis(self.base_param)
        result = stage_analysis.load_communication_group_df()
        self.assertIsNone(result)

    @patch('os.path.exists')
    @patch('msprof_analyze.prof_common.file_manager.FileManager.read_json_file')
    def test_load_communication_group_df_for_text_when_valid_file_then_load_successfully(self, mock_json_load,
                                                                                         mock_exists):
        """Test load_communication_group_df_for_text with valid file"""
        # Given valid file and data
        mock_exists.return_value = True
        mock_json_load.return_value = {
            Constant.KEY_COMM_GROUP_PARALLEL_INFO: self.sample_comm_group_data
        }
        stage_analysis = StageInfoAnalysis(self.base_param)
        result = stage_analysis.load_communication_group_df_for_text()

        self.assertIsNotNone(result)
        self.assertEqual(len(result), 5)
        self.assertIn(TableConstant.TYPE, result.columns)

    @patch('os.path.exists')
    @patch('msprof_analyze.prof_common.file_manager.FileManager.read_json_file')
    def test_load_communication_group_df_for_text_when_file_not_exists_then_return_none(self, mock_json_load,
                                                                                        mock_exists):
        """Test load_communication_group_df_for_text when file doesn't exist"""
        # Mock path doesn't exist
        mock_exists.return_value = False
        stage_analysis = StageInfoAnalysis(self.base_param)
        result = stage_analysis.load_communication_group_df_for_text()
        self.assertIsNone(result)
        # Mock path exist but json doesn't have parallel info empty
        mock_exists.return_value = True
        mock_json_load.return_value = {Constant.KEY_COMM_GROUP_PARALLEL_INFO: []}
        stage_analysis = StageInfoAnalysis(self.base_param)
        result = stage_analysis.load_communication_group_df_for_text()
        self.assertIsNone(result)

    @patch('os.path.exists')
    @patch('msprof_analyze.prof_common.database_service.DatabaseService.query_data')
    def test_load_communication_group_df_for_db_when_valid_db_then_load_successfully(self, mock_query, mock_exists):
        """Test load_communication_group_df_for_db with valid database"""
        mock_exists.return_value = True
        comm_group_df = pd.DataFrame(self.sample_comm_group_data)
        comm_group_df["rank_set"] = comm_group_df["rank_set"].apply(lambda x: "(" + ",".join(str(i) for i in x) + ")")
        mock_query.return_value = {
            Constant.TABLE_COMMUNICATION_GROUP_MAPPING: comm_group_df
        }
        param = self.base_param.copy()
        param[Constant.DATA_TYPE] = Constant.DB
        stage_analysis = StageInfoAnalysis(param)
        result = stage_analysis.load_communication_group_df_for_db()
        self.assertIsNotNone(result)
        self.assertEqual(len(result), 5)

    @patch('os.path.exists')
    @patch('msprof_analyze.prof_common.database_service.DatabaseService.query_data')
    def test_load_communication_group_df_for_db_when_dir_not_exists_then_return_none(self, mock_query, mock_exists):
        """Test load_communication_group_df_for_db when directory doesn't exist"""
        # Given directory doesn't exist
        mock_exists.return_value = False
        param = self.base_param.copy()
        param[Constant.DATA_TYPE] = Constant.DB
        stage_analysis = StageInfoAnalysis(param)
        result = stage_analysis.load_communication_group_df_for_db()
        self.assertIsNone(result)
        # Mock path exist but json doesn't have parallel info empty
        mock_exists.return_value = True
        mock_query.return_value = {}
        param = self.base_param.copy()
        stage_analysis = StageInfoAnalysis(param)
        result = stage_analysis.load_communication_group_df_for_db()
        self.assertIsNone(result)

    def test_run_when_prepare_data_succeeds_then_return_stage_group(self):
        """Test run method when prepare_data succeeds"""
        # Given successful data preparation
        param = self.base_param.copy()
        param[Constant.COMM_DATA_DICT] = {
            Constant.KEY_COMM_GROUP_PARALLEL_INFO: self.sample_comm_group_data
        }
        stage_analysis = StageInfoAnalysis(param)

        result = stage_analysis.run()
        self.assertIsInstance(result, list)
        self.assertEqual(len(result), 2)  # One collective group becomes one stage

    def test_run_when_prepare_data_fails_then_return_empty_list(self):
        """Test run method when prepare_data fails"""
        stage_analysis = StageInfoAnalysis(self.base_param)
        with patch.object(stage_analysis, 'prepare_data', return_value=False):
            result = stage_analysis.run()
        self.assertEqual(result, [])
