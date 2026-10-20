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
from unittest import mock
from unittest.mock import patch, MagicMock
import pandas as pd

from msprof_analyze.cluster_analyse.common_func.context import Context
from msprof_analyze.cluster_analyse.recipes.pp_chart.pp_chart import PPChart
from msprof_analyze.prof_common.constant import Constant

NAMESPACE = "msprof_analyze.cluster_analyse.recipes"


class TestClusterTimeCompareSummary(unittest.TestCase):
    def setUp(self):
        self.expected_pp_stage_mstx_num = {
            0: 44,
            1: 32,
            2: 30,
            3: 29
        }
        self.expected_micro_batch_id_dict = {
            0: [['0', 0], ['1', 0], ['2', 0], ['3', 0], ['4', 0], ['5', 0], ['6', 1], ['10', 1], ['logits', 2],
                ['10b', 2], ['10w', 2], ['11', 2], ['logits', 2], ['11b', 2], ['11w', 2], ['12', 2], ['logits', 2],
                ['12b', 2], ['12w', 2], ['13', 2], ['logits', 3], ['7F+13B', 3], ['14F+0B', 3], ['logits', 3],
                ['8F+14B', 3], ['15F+1B', 3], ['logits', 3], ['9F+15B', 3], ['16F+2B', 3], ['logits', 4], ['16B', 4],
                ['17F+3B', 4], ['logits', 4], ['17B', 4], ['18F+4B', 4], ['logits', 4], ['18B', 4], ['19F+5B', 4],
                ['logits', 5], ['19B', 5], ['6B', 6], ['7B', 6], ['8B', 6], ['9B', 6]],
            1: [['0', 0], ['1', 0], ['2', 0], ['3', 0], ['4', 1], ['10', 1], ['5', 1], ['11', 1], ['10b', 2],
                ['10w', 2], ['12', 2], ['11b', 2], ['11w', 2], ['13', 2], ['6F+12B', 3], ['14F+0B', 3], ['7F+13B', 3],
                ['15F+1B', 3], ['8F+14B', 3], ['16F+2B', 3], ['9F+15B', 3], ['17F+3B', 3], ['16B', 4], ['18F+4B', 4],
                ['17B', 4], ['19F+5B', 4], ['18B', 5], ['6B', 5], ['19B', 6], ['7B', 6], ['8B', 6], ['9B', 6]],
            2: [['0', 0], ['1', 0], ['2', 1], ['10', 1], ['3', 1], ['11', 1], ['4', 1], ['12', 1], ['10b', 2],
                ['10w', 2], ['13', 2], ['5F+11B', 3], ['14F+0B', 3], ['6F+12B', 3], ['15F+1B', 3], ['7F+13B', 3],
                ['16F+2B', 3], ['8F+14B', 3], ['17F+3B', 3], ['9F+15B', 3], ['18F+4B', 3], ['16B', 4], ['19F+5B', 4],
                ['17B', 5], ['6B', 5], ['18B', 5], ['7B', 6], ['19B', 6], ['8B', 6], ['9B', 6]],
            3: [['0', 1], ['10', 1], ['1', 1], ['11', 1], ['2', 1], ['12', 1], ['3', 1], ['13', 1], ['4F', 3],
                ['10B', 3], ['14F+0B', 3], ['5F+11B', 3], ['15F+1B', 3], ['6F+12B', 3], ['16F+2B', 3], ['7F+13B', 3],
                ['17F+3B', 3], ['8F+14B', 3], ['18F+4B', 3], ['9F+15B', 3], ['19F+5B', 3], ['16B', 5], ['6B', 5],
                ['17B', 5], ['7B', 5], ['18B', 6], ['8B', 6], ['19B', 6], ['9B', 6]]
        }

    @patch("msprof_analyze.prof_common.path_manager.PathManager.check_output_directory_path")
    def test_calculate_micro_batch_id_for_dualpipev_when_pp_size_4_and_num_microbatches_10(self,
        mock_check_output_directory_path):
        with mock.patch(NAMESPACE + ".pp_chart.pp_chart.PPChart.load_pp_info"):
            pp_chart_instance = PPChart({})
            pp_chart_instance.micro_batch_num = 10
            pp_chart_instance.distributed_args = {PPChart.PP_SIZE: 4}
            pp_chart_instance.calculate_micro_batch_id_for_dualpipev()
            self.assertEqual(pp_chart_instance.pp_stage_mstx_num, self.expected_pp_stage_mstx_num)
            self.assertEqual(pp_chart_instance.micro_batch_id_dict, self.expected_micro_batch_id_dict)

    @patch("msprof_analyze.prof_common.path_manager.PathManager.check_output_directory_path")
    def test_pp_chart_should_generate_table_when_pp_info_not_existed(self, mock_check_output_directory_path):
        df = pd.DataFrame({"step": [0, 0], "msg": ["forward_step", "backward_step"], "startNs": [1, 4],
                           "endNs": [2, 5]})
        with mock.patch(NAMESPACE + ".base_recipe_analysis.BaseRecipeAnalysis.load_distributed_args",
                        return_value={}), \
             mock.patch(NAMESPACE + ".base_recipe_analysis.BaseRecipeAnalysis.dump_data"), \
             mock.patch(NAMESPACE + ".pp_chart.pp_chart.PPChart.load_pp_info"), \
             mock.patch("msprof_analyze.prof_exports.base_stats_export.BaseStatsExport.read_export_db",
                        return_value=df):
            with Context.create_context() as context:
                pp_chart_instance = PPChart({})
                pp_chart_instance.micro_batch_num = 10
                pp_chart_instance.run(context)
                self.assertFalse(pp_chart_instance.micro_batch_id_dict)

    @patch("msprof_analyze.prof_common.path_manager.PathManager.check_output_directory_path")
    @patch("msprof_analyze.prof_common.database_service.DatabaseService.query_data")
    @patch("os.path.exists", return_value=True)
    def test_load_pp_info_should_load_pp_info_successfully_when_pp_info_existed(self, mock_exists, mock_query_data,
                                                                                mock_check_output_directory_path):
        df_dict = {
            "META_DATA": pd.DataFrame({
                "name": ["pp_info"],
                "value": [
                    '{"microbatch_num":10,"pp_type":"dualpipev"}'
                ]
            })
        }
        mock_query_data.return_value = df_dict
        pp_chart_instance = PPChart({Constant.DATA_MAP: {0: "./profiling_path"}})
        pp_chart_instance.load_pp_info()
        self.assertEqual(pp_chart_instance.micro_batch_num, 10)
        self.assertEqual(pp_chart_instance.pp_type, "dualpipev")

    @patch("msprof_analyze.prof_common.path_manager.PathManager.check_output_directory_path")
    @patch("msprof_analyze.prof_common.database_service.DatabaseService.query_data")
    @patch("os.path.exists")
    def test_load_pp_info_should_return_when_pp_info_not_existed(self, mock_exists, mock_query_data,
                                                                 mock_check_output_directory_path):
        df_dict = {}
        mock_query_data.return_value = df_dict
        pp_chart_instance = PPChart({Constant.DATA_MAP: {0: "./profiling_path"}})
        mock_exists.return_value = False
        pp_chart_instance.load_pp_info()
        self.assertIsNone(pp_chart_instance.micro_batch_num)
        self.assertIsNone(pp_chart_instance.pp_type)
        mock_exists.return_value = True
        pp_chart_instance.load_pp_info()
        self.assertIsNone(pp_chart_instance.micro_batch_num)
        self.assertIsNone(pp_chart_instance.pp_type)
        df_dict = {
            "META_DATA": pd.DataFrame({
                "name": ["ENV_VARIABLES"],
                "value": [""]
            })
        }
        mock_query_data.return_value = df_dict
        pp_chart_instance.load_pp_info()
        self.assertIsNone(pp_chart_instance.micro_batch_num)
        self.assertIsNone(pp_chart_instance.pp_type)

    @patch(NAMESPACE + '.pp_chart.pp_chart.Mstx2Commop')
    @patch(NAMESPACE + '.pp_chart.pp_chart.PPChart.load_pp_info')
    @patch("msprof_analyze.prof_common.path_manager.PathManager.check_output_directory_path")
    def test_run_mstx2commop_recipe_should_return_true_when_run_successfully(self,
        mock_check_output_directory_path, mock_load_pp_info, mock_mstx2commop_class):
        mock_instance = MagicMock()
        mock_mstx2commop_class.return_value = mock_instance
        mock_instance.run.return_value = None
        pp_chart_instance = PPChart({})
        result = pp_chart_instance.run_mstx2commop_recipe(None)
        self.assertTrue(result)
        mock_mstx2commop_class.assert_called_once_with({})
        mock_instance.run.assert_called_once_with(None, copy_db=False)

    @patch(NAMESPACE + '.pp_chart.pp_chart.Mstx2Commop')
    @patch(NAMESPACE + '.pp_chart.pp_chart.PPChart.load_pp_info')
    @patch("msprof_analyze.prof_common.path_manager.PathManager.check_output_directory_path")
    def test_run_mstx2commop_recipe_should_return_true_when_run_failed(self,
        mock_check_output_directory_path, mock_load_pp_info, mock_mstx2commop_class):
        mock_instance = MagicMock()
        mock_mstx2commop_class.return_value = mock_instance
        mock_instance.run.side_effect = Exception("ERROR")
        pp_chart_instance = PPChart({})
        result = pp_chart_instance.run_mstx2commop_recipe(None)
        self.assertFalse(result)

    @patch(NAMESPACE + '.pp_chart.pp_chart.P2PPairing')
    @patch(NAMESPACE + '.pp_chart.pp_chart.PPChart.load_pp_info')
    @patch("msprof_analyze.prof_common.path_manager.PathManager.check_output_directory_path")
    def test_run_p2p_pairing_recipe_should_return_true_when_run_successfully(self,
        mock_check_output_directory_path, mock_load_pp_info, mock_p2ppairing_class):
        mock_instance = MagicMock()
        mock_p2ppairing_class.return_value = mock_instance
        mock_instance.run.return_value = None
        pp_chart_instance = PPChart({})
        result = pp_chart_instance.run_p2p_pairing_recipe(None)
        self.assertTrue(result)
        mock_p2ppairing_class.assert_called_once_with({})
        mock_instance.run.assert_called_once_with(None)

    @patch(NAMESPACE + '.pp_chart.pp_chart.P2PPairing')
    @patch(NAMESPACE + '.pp_chart.pp_chart.PPChart.load_pp_info')
    @patch("msprof_analyze.prof_common.path_manager.PathManager.check_output_directory_path")
    def test_run_p2p_pairing_recipe_should_return_true_when_run_failed(self,
        mock_check_output_directory_path, mock_load_pp_info, mock_p2ppairing_class):
        mock_instance = MagicMock()
        mock_p2ppairing_class.return_value = mock_instance
        mock_instance.run.side_effect = Exception("ERROR")
        pp_chart_instance = PPChart({})
        result = pp_chart_instance.run_p2p_pairing_recipe(None)
        self.assertFalse(result)

    @patch(NAMESPACE + ".base_recipe_analysis.BaseRecipeAnalysis.dump_data")
    @patch('msprof_analyze.prof_exports.pp_chart_export.PPChartExport.read_export_db')
    @patch('msprof_analyze.prof_common.db_manager.DBManager.check_tables_in_db', return_value=True)
    @patch(NAMESPACE + '.pp_chart.pp_chart.PPChart.load_pp_info')
    @patch("msprof_analyze.prof_common.path_manager.PathManager.check_output_directory_path")
    def test__mapper_func_for_dualpipev_should_dump_db_successfully(self, mock_check_output_directory_path,
        mock_load_pp_info, mock_check_tables_in_db, mock_read_export_db, mock_dump_data):
        data_map = {
            Constant.RANK_ID: 0,
            Constant.PROFILER_DB_PATH: "",
            Constant.ANALYSIS_DB_PATH: ""
        }
        rank_pp_stage_map = {
            0: 0,
            1: 1,
            2: 2,
            3: 3
        }
        mock_read_export_db.return_value = pd.DataFrame({
            "step": [0] * 44,
            "msg": [str(i) for i in range(1, 45)],
            "startNs": [i * 2 for i in range(1, 45)],
            "endNs": [i * 2 + 1 for i in range(1, 45)]
        })
        pp_chart_instance = PPChart({})
        pp_chart_instance._mapper_func_for_dualpipev(data_map, "PPChart", rank_pp_stage_map,
            self.expected_pp_stage_mstx_num, self.expected_micro_batch_id_dict)
        mock_dump_data.assert_called_once()
