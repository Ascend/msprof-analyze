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

import tempfile
import unittest
from unittest.mock import patch

import pandas as pd

from msprof_analyze.cluster_analyse.recipes.operator_mfu.operator_mfu import OperatorMfu
from msprof_analyze.prof_common.constant import Constant


class TestOperatorMfu(unittest.TestCase):
    """测试算子 MFU 分析任务。"""

    def setUp(self):
        """创建使用临时输出目录的分析任务。"""
        self.temp_dir = tempfile.TemporaryDirectory()
        params = {
            Constant.COLLECTION_PATH: self.temp_dir.name,
            Constant.RECIPE_NAME: "operator_mfu",
            Constant.EXPORT_TYPE: Constant.TEXT,
            Constant.CLUSTER_ANALYSIS_OUTPUT_PATH: self.temp_dir.name,
        }
        self.analysis = OperatorMfu(params)

    def tearDown(self):
        """清理临时输出目录。"""
        self.temp_dir.cleanup()

    def test_run_when_save_is_false_then_return_valid_mapper_results(self):
        """测试 save=False 时保留包含 MFU 数据的 rank 结果。"""
        kernel_df = pd.DataFrame({'mfu': [0.5]})
        module_df = pd.DataFrame()
        mapper_res = [
            (0, kernel_df, module_df),
            (1, pd.DataFrame(), pd.DataFrame()),
        ]

        with patch.object(self.analysis, 'mapper_func', return_value=mapper_res):
            result = self.analysis.run(context=None, save=False)

        self.assertEqual([(0, kernel_df, module_df)], result)

    def test_generate_kernel_mfu_list_when_format_text_then_rename_duration_column(self):
        """测试 kernel 时长列能够按文本导出格式重命名。"""
        kernel_df = pd.DataFrame([{
            'op_name': 'op',
            'kernel_name': 'kernel',
            'kernel_ts': 10,
            'kernel_end': 30,
            'kernel_duration': 20,
            'mfu': 0.5,
            'chip_peak': 100 * 1e12,
        }])

        result = self.analysis._generate_kernel_mfu_list(kernel_df, rank_id=0)
        formatted_result = self.analysis._format_kernel_mfu_columns(result, Constant.TEXT)

        self.assertEqual(20, formatted_result.iloc[0]['Kernel Duration(ns)'])
        self.assertNotIn('kernel_duration', formatted_result.columns)
