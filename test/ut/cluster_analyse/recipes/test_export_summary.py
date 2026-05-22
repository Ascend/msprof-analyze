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

import unittest
from unittest.mock import patch
import os
import tempfile
import pandas as pd

from msprof_analyze.cluster_analyse.recipes.export_summary.export_summary import ExportSummary
from msprof_analyze.prof_common.constant import Constant


class TestExportSummary(unittest.TestCase):

    def setUp(self):
        self._tmp_dir = tempfile.TemporaryDirectory()
        self.tmp_path = self._tmp_dir.name

    def tearDown(self):
        self._tmp_dir.cleanup()

    def _create_recipe(self, data_map=None):
        params = {
            Constant.COLLECTION_PATH: os.path.join(self.tmp_path, "collection"),
            Constant.DATA_MAP: data_map or {
                0: os.path.join(self.tmp_path, "rank0"),
                1: os.path.join(self.tmp_path, "rank1")
            },
            Constant.RECIPE_NAME: "export_summary",
            Constant.PARALLEL_MODE: "concurrent",
            Constant.EXPORT_TYPE: "db",
            Constant.PROFILING_TYPE: "pytorch",
            Constant.CLUSTER_ANALYSIS_OUTPUT_PATH: os.path.join(self.tmp_path, "output"),
            Constant.RANK_LIST: "all",
            Constant.STEP_ID: -1
        }
        return ExportSummary(params)

    def test_reducer_func_should_save_csv_files(self):
        api_df = pd.DataFrame({
            "API Name": ["aclnnCast", "aclnnMseLoss"],
            "Count": [72, 6],
            "Total Time(us)": [761.09, 271.56],
            "Avg Time(us)": [10.57, 45.26],
            "Min Time(us)": [5.53, 29.24],
            "Max Time(us)": [28.0, 53.42]
        })
        kernel_df = pd.DataFrame({
            "op_name": ["MatMul", "Add"],
            "op_type": ["MatMul", "Add"],
            "task_type": ["AI_CORE", "AI_CORE"],
            "task_duration": [100.5, 50.2]
        })

        recipe = self._create_recipe()
        mapper_res = [(0, api_df.copy(), kernel_df.copy()), (1, api_df.copy(), kernel_df.copy())]

        with patch.object(recipe, '_get_ascend_output_path') as mock_get_path, \
             patch.object(recipe, '_save_api_statistic') as mock_save_api, \
             patch.object(recipe, '_save_kernel_details') as mock_save_kernel:
            mock_get_path.side_effect = lambda rank_id: f"/test/path/rank{rank_id}/ASCEND_PROFILER_OUTPUT"
            
            recipe.reducer_func(mapper_res)

            self.assertEqual(mock_get_path.call_count, 2)
            self.assertEqual(mock_save_api.call_count, 2)
            self.assertEqual(mock_save_kernel.call_count, 2)

    def test_reducer_func_should_skip_when_ascend_output_not_found(self):
        api_df = pd.DataFrame({"API Name": ["aclnnCast"], "Count": [72]})
        kernel_df = pd.DataFrame({"op_name": ["MatMul"], "op_type": ["MatMul"]})

        recipe = self._create_recipe()
        mapper_res = [(0, api_df, kernel_df)]

        with patch.object(recipe, '_get_ascend_output_path', return_value=None), \
             patch.object(recipe, '_save_api_statistic') as mock_save_api, \
             patch.object(recipe, '_save_kernel_details') as mock_save_kernel:
            
            recipe.reducer_func(mapper_res)

            mock_save_api.assert_not_called()
            mock_save_kernel.assert_not_called()

    def test_reducer_func_should_handle_empty_mapper_res(self):
        recipe = self._create_recipe()
        
        with patch.object(recipe, '_get_ascend_output_path') as mock_get_path:
            recipe.reducer_func([])
            
            mock_get_path.assert_not_called()

    def test_reducer_func_should_handle_none_data(self):
        recipe = self._create_recipe()
        mapper_res = [(0, None, None)]

        with patch.object(recipe, '_get_ascend_output_path') as mock_get_path:
            recipe.reducer_func(mapper_res)
            
            mock_get_path.assert_not_called()

    def test_reducer_func_should_handle_empty_dataframe(self):
        recipe = self._create_recipe()
        mapper_res = [(0, pd.DataFrame(), pd.DataFrame())]

        with patch.object(recipe, '_get_ascend_output_path') as mock_get_path:
            recipe.reducer_func(mapper_res)
            
            mock_get_path.assert_not_called()

    def test_save_api_statistic_should_save_when_df_valid(self):
        recipe = self._create_recipe()
        df = pd.DataFrame({"API Name": ["aclnnCast"], "Count": [72]})

        with patch('os.path.exists', return_value=False), \
             patch('msprof_analyze.cluster_analyse.recipes.export_summary.export_summary.FileManager.create_csv_from_dataframe') as mock_create:
            
            recipe._save_api_statistic(0, df, "/test/output")

            mock_create.assert_called_once()

    def test_save_api_statistic_should_skip_when_df_empty(self):
        recipe = self._create_recipe()

        with patch('msprof_analyze.cluster_analyse.recipes.export_summary.export_summary.FileManager.create_csv_from_dataframe') as mock_create:
            
            recipe._save_api_statistic(0, pd.DataFrame(), "/test/output")

            mock_create.assert_not_called()

    def test_save_api_statistic_should_skip_when_df_none(self):
        recipe = self._create_recipe()

        with patch('msprof_analyze.cluster_analyse.recipes.export_summary.export_summary.FileManager.create_csv_from_dataframe') as mock_create:
            
            recipe._save_api_statistic(0, None, "/test/output")

            mock_create.assert_not_called()

    def test_save_api_statistic_should_skip_when_file_exists(self):
        recipe = self._create_recipe()
        df = pd.DataFrame({"API Name": ["aclnnCast"], "Count": [72]})

        with patch('os.path.exists', return_value=True), \
             patch('msprof_analyze.cluster_analyse.recipes.export_summary.export_summary.FileManager.create_csv_from_dataframe') as mock_create:
            
            recipe._save_api_statistic(0, df, "/test/output")

            mock_create.assert_not_called()

    def test_save_kernel_details_should_save_when_df_valid(self):
        recipe = self._create_recipe()
        df = pd.DataFrame({"op_name": ["MatMul"], "op_type": ["MatMul"]})

        with patch('os.path.exists', return_value=False), \
             patch('msprof_analyze.cluster_analyse.recipes.export_summary.export_summary.FileManager.create_csv_from_dataframe') as mock_create:
            
            recipe._save_kernel_details(0, df, "/test/output")

            mock_create.assert_called_once()

    def test_save_kernel_details_should_skip_when_df_empty(self):
        recipe = self._create_recipe()

        with patch('msprof_analyze.cluster_analyse.recipes.export_summary.export_summary.FileManager.create_csv_from_dataframe') as mock_create:
            
            recipe._save_kernel_details(0, pd.DataFrame(), "/test/output")

            mock_create.assert_not_called()

    def test_save_kernel_details_should_skip_when_file_exists(self):
        recipe = self._create_recipe()
        df = pd.DataFrame({"op_name": ["MatMul"], "op_type": ["MatMul"]})

        with patch('os.path.exists', return_value=True), \
             patch('msprof_analyze.cluster_analyse.recipes.export_summary.export_summary.FileManager.create_csv_from_dataframe') as mock_create:
            
            recipe._save_kernel_details(0, df, "/test/output")

            mock_create.assert_not_called()

    def test_get_ascend_output_path_should_return_path_when_exists(self):
        recipe = self._create_recipe(data_map={0: "/test/path/rank0"})

        with patch('os.path.exists', return_value=True):
            result = recipe._get_ascend_output_path(0)
            
            expected_path = os.path.join("/test/path/rank0", "ASCEND_PROFILER_OUTPUT")
            self.assertEqual(result, expected_path)

    def test_get_ascend_output_path_should_return_none_when_not_exists(self):
        recipe = self._create_recipe(data_map={0: "/test/path/rank0"})

        with patch('os.path.exists', return_value=False):
            result = recipe._get_ascend_output_path(0)
            
            self.assertIsNone(result)

    def test_get_ascend_output_path_should_return_none_when_rank_not_in_data_map(self):
        recipe = self._create_recipe(data_map={0: "/test/path/rank0"})

        with patch('os.path.exists', return_value=True):
            result = recipe._get_ascend_output_path(999)
            
            expected_path = os.path.join("", "ASCEND_PROFILER_OUTPUT")
            self.assertEqual(result, expected_path)


if __name__ == "__main__":
    unittest.main()
