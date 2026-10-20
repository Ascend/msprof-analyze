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

from msprof_analyze.cluster_analyse.recipes.p2p_pairing.p2p_pairing import P2PPairing
from msprof_analyze.prof_common.constant import Constant


class TestP2PPairing(unittest.TestCase):

    @patch("msprof_analyze.cluster_analyse.recipes.p2p_pairing.p2p_pairing.DBManager")
    def test_mapper_func_should_convert_mstx_checkpoints_to_communication_operators(self, mock_db_manager_class):
        mock_db_manager_class.create_connect_db.return_value = (None, None)
        mock_db_manager_class.check_columns_exist.return_value = set()
        recipe = P2PPairing({})
        expected_result = pd.DataFrame(
            {
                "opNameId": [707],
                "opConnectionId": ["849_0_0_0"]
            }
        )
        recipe.update_connection_info_to_table(expected_result, "")


    @patch("msprof_analyze.cluster_analyse.recipes.p2p_pairing.p2p_pairing.P2PPairing.update_connection_info_to_table")
    @patch("msprof_analyze.prof_exports.base_stats_export.BaseStatsExport.read_export_db")
    @patch("msprof_analyze.prof_common.db_manager.DBManager.check_tables_in_db", return_value=True)
    def test_mapper_func_should_generate_p2p_connection_ids(self, mock_check_tables_in_db,
        mock_read_export_db, mock_update_connection_info_to_table):
        mock_read_export_db.return_value = pd.DataFrame(
            {
                "opNameId": [707, 707],
                "opName": ["hcom_send__849_56_1", "hcom_send__849_56_1"],
                "startTime": [1755066160966106180, 1755066161066106180],
                "endTime": [1755066160966206180, 1755066161066206180],
                "globalRank": [0, 0],
                "srcRank": [0, 0],
                "dstRank": [0, 4294967295],
                "taskType": ["Notify_Record", "Reduce+Inline"],
                "coGroupName": ["100%enp189s0f1_55000_0_1738895521183247", "100%enp189s0f1_55000_0_1738895521183247"],
                "ctiGroupName": ["100%enp189s0f1_55000_0_1738895521183247", "100%enp189s0f1_55000_0_1738895521183247"],
            }
        )
        recipe = P2PPairing({})
        data_map = {Constant.RANK_ID: 0, Constant.PROFILER_DB_PATH: "",
                    Constant.ANALYSIS_DB_PATH: "", Constant.STEP_RANGE: {}}
        recipe._mapper_func(data_map, "P2PPairing")
        args, kwargs = mock_update_connection_info_to_table.call_args
        expected_result = pd.DataFrame(
            {
                "opNameId": [707],
                "opConnectionId": ["849_0_0_0"]
            }
        )
        self.assertTrue(expected_result.equals(args[0]))
