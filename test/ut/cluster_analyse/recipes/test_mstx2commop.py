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
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
import pandas as pd

from msprof_analyze.cluster_analyse.recipes.mstx2commop.mstx2commop import Mstx2Commop
from msprof_analyze.prof_common.constant import Constant
from msprof_analyze.prof_exports.mstx2commop_export import Mstx2CommopExport


class TestMstx2Commop(unittest.TestCase):

    def test_mstx_export_should_support_connection_id_and_stream_id_matching(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = os.path.join(tmp_dir, "profiler.db")
            connection = sqlite3.connect(db_path)
            connection.executescript("""
                CREATE TABLE MSTX_EVENTS (startNs INTEGER, connectionId INTEGER, message INTEGER);
                CREATE TABLE TASK (startNs INTEGER, endNs INTEGER, connectionId INTEGER, streamId INTEGER);
                CREATE TABLE STRING_IDS (id INTEGER, value TEXT);
            """)
            connection.executemany(
                "INSERT INTO MSTX_EVENTS VALUES (?, ?, ?)",
                [(100, 1, 7), (101, 2, 8), (102, 3, 9), (103, 5, 10), (104, 6, 11)]
            )
            connection.executemany(
                "INSERT INTO TASK VALUES (?, ?, ?, ?)",
                [
                    (110, 120, 4, 99),
                    (130, 140, 2, 200),
                    (150, 160, 3, 101),
                    (170, 180, 5, 500),
                    (190, 200, 6, 600),
                ]
            )
            connection.executemany(
                "INSERT INTO STRING_IDS VALUES (?, ?)",
                [
                    (7, '{"streamId": "99", "count": "1", "dataType": "bfp16", '
                        '"groupName": "group_name_13", "opName": "stream_only"}'),
                    (8, r'{\"streamId\": \"100\", \"count\": \"1\", \"dataType\": \"bfp16\", '
                        r'\"groupName\": \"group_name_13\", \"opName\": \"escaped_connection_only\"}'),
                    (9, '{"streamId": "101", "count": "1", "dataType": "bfp16", '
                        '"groupName": "group_name_13", "opName": "both_match"}'),
                    (10, '{"streamId": "102", "count": "1", "dataType": "bfp16", '
                         '"groupName": "group_name_13", "opName": "connection_only"}'),
                    (11, 'message "streamId": "103", "count": "1", "dataType": "bfp16", '
                         '"groupName": "group_name_13", "opName": "non_json_connection_only"')
                ]
            )
            connection.commit()
            connection.close()

            export = Mstx2CommopExport(db_path, "Mstx2Commop", {
                Constant.START_NS: 0,
                Constant.END_NS: 200,
            })
            result = export.read_export_db()

        self.assertEqual(len(result), 5)
        self.assertEqual(set(result["connectionId"]), {2, 3, 4, 5, 6})

        matched_connections = {
            value.split('"opName": "')[1].split('"')[0]: connection_id
            for value, connection_id in zip(result["value"], result["connectionId"])
        }
        self.assertEqual(matched_connections, {
            "stream_only": 4,
            "escaped_connection_only": 2,
            "both_match": 3,
            "connection_only": 5,
            "non_json_connection_only": 6,
        })
        self.assertEqual((result["value"].str.contains('"opName": "both_match"')).sum(), 1)
        self.assertTrue(
            result.loc[result["value"].str.contains("escaped_connection_only"), "value"]
            .iloc[0]
            .startswith('{"streamId"')
        )

    @patch("msprof_analyze.prof_common.db_manager.DBManager.insert_data_into_db")
    @patch("msprof_analyze.cluster_analyse.recipes.base_recipe_analysis.BaseRecipeAnalysis.dump_data")
    @patch("msprof_analyze.prof_exports.base_stats_export.BaseStatsExport.read_export_db")
    @patch("msprof_analyze.cluster_analyse.recipes.ep_load_balance.ep_load_balance.DatabaseService.query_data")
    @patch("msprof_analyze.prof_common.db_manager.DBManager.check_tables_in_db", return_value=False)
    def test_mapper_func_should_convert_mstx_checkpoints_to_communication_operators(self, mock_check_tables_in_db,
        mock_db_service, mock_read_export_db, mock_dump_data, mock_insert_data_into_db):
        mock_db_service.return_value = {
            "ENUM_HCCL_DATA_TYPE": pd.DataFrame(
                {
                    "id": [0, 1],
                    "name": ["INT64", "BFP16"]
                }
            ),
            "STRING_IDS": pd.DataFrame(
                {
                    "id": [0, 1],
                    "value": ["AIC", "AIV"]
                }
            )
        }
        mock_read_export_db.return_value = pd.DataFrame(
            {
                "startNs": [1755066160966106180, 1755066161966106180],
                "endNs": [1755066160966206180, 1755066161966206180],
                "connectionId": [4000000004, 4000000005],
                "value": [
                    '{"streamId": "9","count": "8194","dataType": "int64",'
                    '"groupName": "group_name_29","opName": "HcclBroadcast"}',
                    '{"streamId": "10","count": "8","dataType": "bfp16",'
                    '"groupName": "group_name_84","opName": "HcclAlltoAllV"}'
                ],
            }
        )
        params = {Constant.EXPORT_TYPE: Constant.DB}
        recipe = Mstx2Commop(params)
        recipe.copy_db = False
        data_map = {Constant.RANK_ID: 0, Constant.PROFILER_DB_PATH: "",
                    Constant.ANALYSIS_DB_PATH: "", Constant.STEP_RANGE: {}}
        recipe._mapper_func(data_map, "Mstx2Commop")
        args, kwargs = mock_dump_data.call_args
        communication_op = kwargs["data"]
        args, kwargs = mock_insert_data_into_db.call_args
        string_ids_insert = args[2]
        new_value = {x[1] for x in string_ids_insert}
        min_id = min([x[0] for x in string_ids_insert])
        self.assertEqual(len(communication_op), 2)
        self.assertEqual(min_id, 2)
        self.assertEqual(new_value, {"HcclAlltoAllV_", "HcclBroadcast_", "group_name_29", "group_name_84",
                                     "HcclAlltoAllV__648_0_1", "HcclBroadcast__843_0_1"})

    @patch("shutil.copyfile")
    @patch("msprof_analyze.prof_common.path_manager.PathManager.make_dir_safety")
    def test_prepare_output_profiler_db_should_return_new_db_path_when_copy_db_is_true(self, mock_make_dir_safety,
                                                                                       mock_copyfile):
        params = {
            Constant.COLLECTION_PATH: "./",
            Constant.DATA_TYPE: Constant.DB,
            Constant.CLUSTER_ANALYSIS_OUTPUT_PATH: "",
            Constant.RECIPE_NAME: "Mstx2Commop",
            Constant.EXPORT_TYPE: Constant.DB,
        }
        recipe = Mstx2Commop(params)
        new_db_path = recipe._prepare_output_profiler_db(
            os.path.join("msprof_ascend_pt", "ASCEND_PROFILER_OUTPUT", "ascend_pytorch_profiler_0.db")
        )
        expected_db_path = os.path.join(
            "cluster_analysis_output", "Mstx2Commop", "msprof_ascend_pt",
            "ASCEND_PROFILER_OUTPUT", "ascend_pytorch_profiler_0.db"
        )
        self.assertEqual(new_db_path, expected_db_path)
