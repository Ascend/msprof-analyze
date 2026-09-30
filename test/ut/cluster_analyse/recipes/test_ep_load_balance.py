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
import pandas as pd

from msprof_analyze.prof_common.constant import Constant
from msprof_analyze.cluster_analyse.recipes.ep_load_balance.ep_load_balance import EPLoadBalance


class TestEPLoadBalance(unittest.TestCase):

    def setUp(self):
        self.params = {}
        self.ep_load_balance = EPLoadBalance(self.params)
        self.mock_db_path = "mock_db_path"
        self.mock_rank_id = 0
        self.mock_step_range = {Constant.START_NS: 0, Constant.END_NS: 1000}
        self.mock_global_ranks = [0, 1]

    @patch("msprof_analyze.cluster_analyse.recipes.ep_load_balance.ep_load_balance.DatabaseService")
    def test_mapper_func_given_valid_data_map_when_called_then_pass(self, mock_db_service):
        """
        Test _mapper_func method to ensure it returns a DataFrame with correct Rank and epRanks columns
        when provided with a valid data map.
        """
        # Mock the DatabaseService and its methods
        mock_db_instance = mock_db_service.return_value
        mock_db_instance.query_data.return_value = {
            "META_DATA": pd.DataFrame(
                {
                    "name": ["parallel_group_info"],
                    "value": ['{"group1": {"group_name": "exp", "global_ranks": [0, 1]}}'],
                }
            )
        }

        # Mock the InputShapeExport

        mock_input_shape_export = MagicMock()
        mock_input_shape_export.read_export_db.return_value = pd.DataFrame(
            {"InputShapes": ["1,3;4,6;;;;;4", "1,3;4,6;;;;;4"]}
        )

        with patch(
            "msprof_analyze.cluster_analyse.recipes.ep_load_balance.ep_load_balance.InputShapeExport",
            return_value=mock_input_shape_export,
        ):
            data_map = {
                Constant.PROFILER_DB_PATH: self.mock_db_path,
                Constant.RANK_ID: self.mock_rank_id,
                Constant.STEP_RANGE: self.mock_step_range,
            }
            result = self.ep_load_balance._mapper_func(data_map, "mock_analysis_class")

            self.assertIsNotNone(result)
            self.assertEqual(result["Rank"].tolist(), [self.mock_rank_id] * 2)
            self.assertEqual(result["epRanks"].tolist(), [self.mock_global_ranks] * 2)

    def test_reducer_func_given_dataframes_when_called_then_pass(self):
        """
        Test reducer_func method to ensure it processes multiple DataFrames and generates
        ep_tokens_summary and top_ep_tokens_map correctly.
        """
        mock_mapper_res = [
            pd.DataFrame(
                {"Rank": [0, 1], "epRanks": [[0, 1], [0, 1]], "InputShapes": ["1,3;4,6;;;;;4", "7,8;10,12;;;;4"]}
            ),
            pd.DataFrame(
                {"Rank": [2, 3], "epRanks": [[0, 1], [0, 1]], "InputShapes": ["1,3;4,6;;;;;4", "1,3;4,6;;;;;4"]}
            ),
        ]

        self.ep_load_balance.reducer_func(mock_mapper_res)

        self.assertIsNotNone(self.ep_load_balance.ep_tokens_summary)
        self.assertIsNotNone(self.ep_load_balance.top_ep_tokens_map)
