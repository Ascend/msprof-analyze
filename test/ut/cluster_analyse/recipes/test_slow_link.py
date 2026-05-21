# Copyright (c) 2026, Huawei Technologies Co., Ltd.
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

import tempfile
import unittest
from unittest.mock import patch

import pandas as pd

from msprof_analyze.cluster_analyse.recipes.slow_link.slow_link import SlowLink
from msprof_analyze.prof_common.constant import Constant


class TestSlowLink(unittest.TestCase):

    @staticmethod
    def _make_params(output_dir, export_type=Constant.DB, extra_args=None):
        return {
            Constant.COLLECTION_PATH: output_dir,
            Constant.DATA_MAP: {},
            Constant.RECIPE_NAME: "slow_link",
            Constant.PARALLEL_MODE: "concurrent",
            Constant.EXPORT_TYPE: export_type,
            Constant.PROFILING_TYPE: "pytorch",
            Constant.CLUSTER_ANALYSIS_OUTPUT_PATH: output_dir,
            Constant.RANK_LIST: "all",
            Constant.STEP_ID: -1,
            Constant.EXTRA_ARGS: extra_args or []
        }

    def _create_recipe(self, export_type=Constant.DB, extra_args=None):
        tmp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(tmp_dir.cleanup)
        return SlowLink(self._make_params(tmp_dir.name, export_type, extra_args))

    @staticmethod
    def _build_mapper_df(rank_id, op_name, communication_time, op_type="all_reduce", data_size=1024,
                         group_name="group_0"):
        return pd.DataFrame({
            "rankId": [rank_id],
            "groupName": [group_name],
            "opName": [op_name],
            "communicationTime": [communication_time],
            "opType": [op_type],
            "dataSize": [data_size]
        })

    def test_init_should_parse_valid_top_num_and_fallback_invalid_top_num(self):
        self.assertEqual(self._create_recipe(extra_args=["--top_num", "3"]).top_num, 3)
        self.assertEqual(self._create_recipe(extra_args=["--top_num", "bad"]).top_num, SlowLink.DEFAULT_TOP_NUM)

    def test_base_dir_should_return_recipe_directory_name(self):
        recipe = self._create_recipe()

        self.assertEqual(recipe.base_dir, "slow_link")

    def test_merge_func_should_add_transmit_time_and_related_ranks(self):
        recipe = self._create_recipe()
        mapper_res = [
            self._build_mapper_df(0, "hcom_allreduce_0", 100),
            self._build_mapper_df(1, "hcom_allreduce_0", 120),
            self._build_mapper_df(2, "hcom_send_0", 999)
        ]

        with patch.object(recipe, "filter_func") as mock_filter:
            recipe.merge_func(mapper_res)

        merged_df = mock_filter.call_args.args[0]
        allreduce_rows = merged_df[merged_df["opName"] == "hcom_allreduce_0"]
        send_row = merged_df[merged_df["opName"] == "hcom_send_0"].iloc[0]
        self.assertEqual(allreduce_rows["transmitTime"].tolist(), [100, 100])
        self.assertEqual(allreduce_rows["relatedRanks"].tolist(), [2, 2])
        self.assertEqual(send_row["transmitTime"], 0)
        self.assertEqual(send_row["relatedRanks"], 0)

    @patch("msprof_analyze.cluster_analyse.recipes.slow_link.slow_link.logger")
    def test_merge_func_should_return_when_mapper_result_empty(self, mock_logger):
        recipe = self._create_recipe()

        recipe.merge_func([None, None])

        mock_logger.error.assert_called_once()
        self.assertEqual(recipe.slow_link_sum, [])
        self.assertEqual(recipe.slow_link_ops, [])

    @patch("msprof_analyze.cluster_analyse.recipes.slow_link.slow_link.detect_outliers_z_score")
    def test_filter_func_should_build_slow_link_ops_and_summary_when_outlier_exists(self, mock_detect):
        mock_detect.return_value = True
        recipe = self._create_recipe(extra_args=["--top_num", "1"])
        mapper_res = pd.DataFrame({
            "rankId": [0, 1, 2],
            "opType": ["all_reduce", "all_reduce", "all_reduce"],
            "dataSize": [1024, 1024, 1024],
            "relatedRanks": [3, 3, 3],
            "transmitTime": [100, 110, 1000]
        })

        recipe.filter_func(mapper_res)

        self.assertEqual(recipe.slow_link_ops.shape[0], 3)
        self.assertEqual(recipe.slow_link_sum.shape[0], 1)
        self.assertEqual(recipe.slow_link_sum["opTypeRelatedRanksDataSize"].iloc[0], "all_reduce3_1024")
        self.assertEqual(recipe.slow_link_sum["maxRank"].iloc[0], 2)
        self.assertEqual(recipe.slow_link_sum["minRank"].iloc[0], 0)
        self.assertIn("offsetRatio", recipe.slow_link_sum.columns)

    @patch("msprof_analyze.cluster_analyse.recipes.slow_link.slow_link.detect_outliers_z_score")
    def test_filter_func_should_keep_result_empty_when_no_outlier_exists(self, mock_detect):
        mock_detect.return_value = False
        recipe = self._create_recipe()
        mapper_res = pd.DataFrame({
            "rankId": [0, 1],
            "opType": ["all_reduce", "all_reduce"],
            "dataSize": [1024, 1024],
            "relatedRanks": [2, 2],
            "transmitTime": [100, 101]
        })

        recipe.filter_func(mapper_res)

        self.assertEqual(recipe.slow_link_sum, [])
        self.assertEqual(recipe.slow_link_ops, [])

    @patch("msprof_analyze.cluster_analyse.recipes.slow_link.slow_link.SlowLink.save_db")
    @patch("msprof_analyze.cluster_analyse.recipes.slow_link.slow_link.SlowLink.merge_func")
    @patch("msprof_analyze.cluster_analyse.recipes.base_recipe_analysis.BaseRecipeAnalysis.mapper_func")
    def test_run_should_save_db_and_reset_invalid_top_num(self, mock_mapper_func, mock_merge_func, mock_save_db):
        recipe = self._create_recipe()
        recipe.top_num = 0
        mock_mapper_func.return_value = ["mapper_result"]

        recipe.run(context=None)

        mock_mapper_func.assert_called_once_with(None)
        mock_merge_func.assert_called_once_with(["mapper_result"])
        mock_save_db.assert_called_once()
        self.assertEqual(recipe.top_num, SlowLink.DEFAULT_TOP_NUM)

    @patch("msprof_analyze.cluster_analyse.recipes.slow_link.slow_link.SlowLink.save_notebook")
    @patch("msprof_analyze.cluster_analyse.recipes.slow_link.slow_link.SlowLink.merge_func")
    @patch("msprof_analyze.cluster_analyse.recipes.base_recipe_analysis.BaseRecipeAnalysis.mapper_func")
    def test_run_should_save_notebook_when_export_type_notebook(self, mock_mapper_func, mock_merge_func,
                                                                mock_save_notebook):
        recipe = self._create_recipe(export_type=Constant.NOTEBOOK)
        mock_mapper_func.return_value = []

        recipe.run(context=None)

        mock_merge_func.assert_called_once_with([])
        mock_save_notebook.assert_called_once()

    @patch("msprof_analyze.cluster_analyse.recipes.slow_link.slow_link.logger")
    @patch("msprof_analyze.cluster_analyse.recipes.slow_link.slow_link.SlowLink.merge_func")
    @patch("msprof_analyze.cluster_analyse.recipes.base_recipe_analysis.BaseRecipeAnalysis.mapper_func")
    def test_run_should_log_error_when_export_type_unknown(self, mock_mapper_func, mock_merge_func, mock_logger):
        recipe = self._create_recipe(export_type="unknown")
        mock_mapper_func.return_value = []

        recipe.run(context=None)

        mock_merge_func.assert_called_once_with([])
        mock_logger.error.assert_called_with("Unknown export type.")

    @patch("msprof_analyze.cluster_analyse.recipes.base_recipe_analysis.BaseRecipeAnalysis.add_helper_file")
    @patch("msprof_analyze.cluster_analyse.recipes.base_recipe_analysis.BaseRecipeAnalysis.create_notebook")
    @patch("msprof_analyze.cluster_analyse.recipes.base_recipe_analysis.BaseRecipeAnalysis.dump_data")
    def test_save_notebook_should_dump_csv_and_copy_helper_files(self, mock_dump_data, mock_create_notebook,
                                                                 mock_add_helper_file):
        recipe = self._create_recipe(export_type=Constant.NOTEBOOK)
        recipe.slow_link_sum = pd.DataFrame({"rankId": [0]})
        recipe.slow_link_ops = pd.DataFrame({"rankId": [1]})

        recipe.save_notebook()

        self.assertEqual(mock_dump_data.call_count, 2)
        mock_create_notebook.assert_called_once_with("stats.ipynb")
        mock_add_helper_file.assert_called_once_with("cluster_display.py")

    @patch("msprof_analyze.cluster_analyse.recipes.base_recipe_analysis.BaseRecipeAnalysis.dump_data")
    def test_save_db_should_dump_summary_and_ops_tables(self, mock_dump_data):
        recipe = self._create_recipe()
        recipe.slow_link_sum = pd.DataFrame({"rankId": [0]})
        recipe.slow_link_ops = pd.DataFrame({"rankId": [1]})

        recipe.save_db()

        self.assertEqual(mock_dump_data.call_count, 2)
        self.assertEqual(mock_dump_data.call_args_list[0].args[2], SlowLink.TABLE_SLOW_LINK_SUM)
        self.assertEqual(mock_dump_data.call_args_list[1].args[2], SlowLink.TABLE_SLOW_LINK_OPS)

    @patch("msprof_analyze.cluster_analyse.recipes.slow_link.slow_link.SlowLinkExport")
    def test_mapper_func_should_insert_rank_id_when_export_data_exists(self, mock_export):
        recipe = self._create_recipe()
        export_df = pd.DataFrame({"opName": ["hcom_allreduce"], "communicationTime": [100]})
        mock_export.return_value.read_export_db.return_value = export_df
        data_map = {Constant.PROFILER_DB_PATH: "/tmp/profiler.db", Constant.RANK_ID: 3}

        result = recipe._mapper_func(data_map, "SlowLink")

        mock_export.assert_called_once_with("/tmp/profiler.db", "SlowLink")
        self.assertEqual(result["rankId"].tolist(), [3])
        self.assertEqual(result["opName"].tolist(), ["hcom_allreduce"])

    @patch("msprof_analyze.cluster_analyse.recipes.slow_link.slow_link.logger")
    @patch("msprof_analyze.cluster_analyse.recipes.slow_link.slow_link.SlowLinkExport")
    def test_mapper_func_should_return_none_when_export_data_empty(self, mock_export, mock_logger):
        recipe = self._create_recipe()
        mock_export.return_value.read_export_db.return_value = pd.DataFrame()
        data_map = {Constant.PROFILER_DB_PATH: "/tmp/profiler.db", Constant.RANK_ID: 3}

        result = recipe._mapper_func(data_map, "SlowLink")

        self.assertIsNone(result)
        mock_logger.warning.assert_called_once()


if __name__ == "__main__":
    unittest.main()
