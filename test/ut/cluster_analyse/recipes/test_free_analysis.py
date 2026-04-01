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
from unittest import mock
from unittest.mock import MagicMock, patch, Mock
import pandas as pd

from msprof_analyze.cluster_analyse.recipes.free_analysis.free_analysis import FreeAnalysis, FreeReason
from msprof_analyze.prof_common.constant import Constant
from msprof_analyze.prof_common.path_manager import PathManager


NAMESPACE_RECIPE = "msprof_analyze.cluster_analyse.recipes.free_analysis.free_analysis"


class TestFreeAnalysis(unittest.TestCase):
    PARAMS = {
        Constant.COLLECTION_PATH: "/data",
        Constant.DATA_MAP: {0: "/rank0", 1: "/rank1"},
        Constant.CLUSTER_ANALYSIS_OUTPUT_PATH: "./tmp_free_analysis_ut",
        Constant.RECIPE_NAME: "FreeAnalysis",
        Constant.PARALLEL_MODE: Constant.CONCURRENT_MODE,
        Constant.EXPORT_TYPE: Constant.DB,
        Constant.RANK_LIST: Constant.ALL,
        Constant.EXTRA_ARGS: {},
    }

    def setUp(self):
        self.recipe = FreeAnalysis(self.PARAMS)

    def tearDown(self):
        PathManager.remove_path_safety(self.PARAMS.get(Constant.CLUSTER_ANALYSIS_OUTPUT_PATH))

    def test_reducer_func_when_has_free_reasons_then_return_us_dataframe(self):
        free_reason1 = FreeReason(1000, 2000, 0)
        free_reason1.reason = "Test reason 1"
        free_reason1.pytorch_idle_time = 500
        free_reason1.cann_idle_time = 300
        
        free_reason2 = FreeReason(3000, 4000, 1)
        free_reason2.reason = "Test reason 2"
        free_reason2.pytorch_idle_time = None
        free_reason2.cann_idle_time = None
        
        mapper_res = [(0, [free_reason1]), (1, [free_reason2])]
        result = self.recipe.reducer_func(mapper_res)
        
        self.assertIsNotNone(result)
        self.assertEqual(len(result), 2)
        self.assertEqual(result['rankId'].tolist(), [0, 1])
        self.assertIn('startTime(us)', result.columns)
        self.assertIn('endTime(us)', result.columns)
        self.assertIn('duration(us)', result.columns)
        self.assertIn('reason', result.columns)

    @patch(f"{NAMESPACE_RECIPE}.free_analysis_export.BusyTimeOverlapExport")
    def test_obtain_top_free_time_when_busy_df_empty_then_return_none(self, mock_busy_export):
        mock_export = MagicMock()
        mock_export.read_export_db.return_value = None
        mock_busy_export.return_value = mock_export
        
        result = self.recipe.obtain_top_free_time("/path/to/db", "FreeAnalysis", 0)
        self.assertIsNone(result)

    @patch(f"{NAMESPACE_RECIPE}.free_analysis_export.BusyTimeOverlapExport")
    def test_obtain_top_free_time_when_has_busy_data_then_return_top_free_intervals(self, mock_busy_export):
        busy_df = pd.DataFrame({
            'start_ns': [0, 1000, 2000],
            'end_ns': [500, 1500, 2500]
        })
        
        mock_export = MagicMock()
        mock_export.read_export_db.return_value = busy_df
        mock_busy_export.return_value = mock_export
        
        self.recipe.top_num = 2
        result = self.recipe.obtain_top_free_time("/path/to/db", "FreeAnalysis", 0)
        
        self.assertIsNotNone(result)
        self.assertIn('start_ns', result.columns)
        self.assertIn('end_ns', result.columns)
        self.assertIn('duration', result.columns)
        self.assertTrue(len(result) <= 2)

    def test_analyze_free_reason_when_no_prev_or_next_task_then_return_skip_reason(self):
        link_df = pd.DataFrame({
            'task_ts': [4000],
            'task_end': [4100],
            'task_type': ['task2'],
            'pytorch_ts': [4010],
            'pytorch_end': [4020],
            'cann_ts': [4050],
            'cann_end': [4080]
        })
        
        free_reason = self.recipe.analyze_free_reason(0, 1000, 3000, link_df)
        self.assertIn("Skip free analysis due to no prev or next task", free_reason.reason)

    def test_analyze_free_reason_when_no_pytorch_ts_then_return_skip_reason(self):
        link_df = pd.DataFrame({
            'task_ts': [500, 4000],
            'task_end': [600, 4100],
            'task_type': ['task1', 'task2'],
            'pytorch_ts': [None, None],
            'pytorch_end': [None, None],
            'cann_ts': [550, 4050],
            'cann_end': [580, 4080]
        })
        
        free_reason = self.recipe.analyze_free_reason(0, 1000, 3000, link_df)
        self.assertIn("Skip free analysis due to no pytorch dispatch time", free_reason.reason)

    def test_analyze_free_reason_when_pytorch_idle_then_return_idle_reason(self):
        link_df = pd.DataFrame({
            'task_ts': [500, 4000],
            'task_end': [600, 4100],
            'task_type': ['task1', 'task2'],
            'pytorch_ts': [510, 4010],
            'pytorch_end': [520, 4020],
            'cann_ts': [550, 4050],
            'cann_end': [580, 4080]
        })
        
        free_reason = self.recipe.analyze_free_reason(0, 1000, 3000, link_df)
        self.assertIn("Idle Pytorch layer", free_reason.reason)
        self.assertIsNotNone(free_reason.pytorch_idle_time)

    def test_analyze_free_reason_when_cann_abnormal_then_return_abnormal_reason(self):
        link_df = pd.DataFrame({
            'task_ts': [500, 4000],
            'task_end': [600, 4100],
            'task_type': ['task1', 'task2'],
            'pytorch_ts': [510, 4010],
            'pytorch_end': [520, 4020],
            'cann_ts': [550, 65000],  # 大的间隔
            'cann_end': [580, 65080]
        })
        
        free_reason = self.recipe.analyze_free_reason(0, 1000, 3000, link_df)
        self.assertIn("Abnormal CANN layer", free_reason.reason)
        self.assertIsNotNone(free_reason.cann_idle_time)

    def test_analyze_device_task_remaining_free(self):
        task_df = pd.DataFrame({
            'task_ts': [1100, 2100],
            'task_end': [1200, 2200],
            'task_type': ['task1', 'task2']
        })
        
        free_reason = FreeReason(1000, 3000, 0)
        self.recipe._analyze_device_task_remaining_free(task_df, free_reason)

        self.assertIn("Device task running", free_reason.reason)
        self.assertIn("max remaining free", free_reason.reason)

    def test_save_excel_when_dataframe_valid_then_rename_columns_and_dump_data(self):
        df = pd.DataFrame({
            'rankId': [0],
            'startTime(us)': ['1000.000'],
            'endTime(us)': ['2000.000'],
            'duration(us)': [1000.0],
            'reason': ['Test reason'],
            'pytorchIdleTime(us)': [500.0],
            'cannIdleTime(us)': [300.0]
        })
        
        with patch.object(self.recipe, 'dump_data') as mock_dump:
            self.recipe.save_csv(df)
            mock_dump.assert_called_once()
            call_args = mock_dump.call_args
            csv_df = call_args[0][0]
            self.assertIn('Rank ID', csv_df.columns)
            self.assertIn('Start Time(us)', csv_df.columns)
            self.assertIn('End Time(us)', csv_df.columns)
            self.assertEqual(call_args[0][1], "free_analysis.csv")

    @patch(f"{NAMESPACE_RECIPE}.DeviceTaskLinkCannPytorchExport")
    @patch(f"{NAMESPACE_RECIPE}.free_analysis_export.BusyTimeOverlapExport")
    def test_mapper_func_when_no_free_time_then_return_empty_list(self, mock_busy_export, mock_link_export):
        mock_busy = MagicMock()
        mock_busy.read_export_db.return_value = None
        mock_busy_export.return_value = mock_busy
        
        data_map = {
            Constant.RANK_ID: 0,
            Constant.PROFILER_DB_PATH: "/path/to/db"
        }
        
        result = self.recipe._mapper_func(data_map, "FreeAnalysis")
        self.assertEqual(result, (0, []))

if __name__ == '__main__':
    unittest.main()
