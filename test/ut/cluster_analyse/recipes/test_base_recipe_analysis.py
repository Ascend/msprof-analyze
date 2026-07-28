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

import json
import os
import unittest
from unittest.mock import patch, MagicMock, call

import pandas as pd

from msprof_analyze.cluster_analyse.recipes.base_recipe_analysis import BaseRecipeAnalysis
from msprof_analyze.prof_common.constant import Constant
from msprof_analyze.prof_common.db_manager import DBManager
from msprof_analyze.prof_common.file_manager import FileManager


class TestBaseRecipeAnalysis(unittest.TestCase):
    def setUp(self):
        self.params = {
            Constant.COLLECTION_PATH: '/tmp/to/collection',
            Constant.DATA_MAP: {0: '/tmp/to/data/0', 1: '/tmp/to/data/1'},
            Constant.RECIPE_NAME: 'test_recipe',
            Constant.PARALLEL_MODE: 'parallel',
            Constant.EXPORT_TYPE: 'csv',
            Constant.PROFILING_TYPE: Constant.PYTORCH,
            Constant.IS_MSPROF: False,
            Constant.IS_MINDSPORE: False,
            Constant.CLUSTER_ANALYSIS_OUTPUT_PATH: '/tmp/to/output',
            Constant.RANK_LIST: '0,1',
            Constant.STEP_ID: 1,
            Constant.EXTRA_ARGS: [],
        }

        # 创建一个 BaseRecipeAnalysis 的子类用于测试
        class ConcreteRecipeAnalysis(BaseRecipeAnalysis):
            @property
            def base_dir(self):
                return 'test_dir'

            def run(self, context):
                pass

        with patch('msprof_analyze.prof_common.path_manager.PathManager.check_output_directory_path'):
            self.analysis = ConcreteRecipeAnalysis(self.params)

    def test_enter_exit(self):
        with self.analysis as instance:
            self.assertEqual(instance, self.analysis)

        with patch('msprof_analyze.cluster_analyse.recipes.base_recipe_analysis.logger.error') as mock_logger:
            try:
                with self.analysis:
                    raise ValueError('Test error')
            except ValueError:
                pass
        mock_logger.assert_called_once()

    def test_output_path_property(self):
        self.assertEqual(
            self.analysis.output_path, os.path.join('/tmp/to/output', Constant.CLUSTER_ANALYSIS_OUTPUT, 'test_recipe')
        )

    def test_filter_data(self):
        test_data = [(1, [1, 2, 3]), (2, []), (3, None), (4, [4, 5])]
        result = BaseRecipeAnalysis._filter_data(test_data)
        self.assertEqual(result, [(1, [1, 2, 3]), (4, [4, 5])])

    @patch.object(DBManager, 'create_connect_db')
    @patch.object(DBManager, 'destroy_db_connect')
    def test_dump_data_to_db(self, mock_destroy, mock_create):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_create.return_value = (mock_conn, mock_cursor)
        data = pd.DataFrame({'a': [1, 2], 'b': [3, 4]})

        self.analysis.dump_data(data, 'test.db', 'test_table')

        mock_create.assert_called_once_with(os.path.join(self.analysis.output_path, 'test.db'))
        mock_destroy.assert_called_once_with(mock_conn, mock_cursor)

    @patch.object(FileManager, 'create_csv_from_dataframe')
    def test_dump_data_to_csv(self, mock_create_csv):
        data = pd.DataFrame({'a': [1, 2], 'b': [3, 4]})
        with patch('msprof_analyze.cluster_analyse.common_func.utils.convert_unit', return_value=data):
            self.analysis.dump_data(data, 'test.csv')

    @patch('shutil.copy')
    def test_create_notebook_without_replace(self, mock_copy):
        self.analysis.create_notebook('test.ipynb')
        mock_copy.assert_called_once_with(
            os.path.realpath(
                os.path.join(
                    os.path.dirname(__file__),
                    "..",
                    "..",
                    "..",
                    "..",
                    "msprof_analyze",
                    "cluster_analyse",
                    "recipes",
                    'test_dir',
                    'test.ipynb',
                )
            ),
            os.path.join(self.analysis.output_path, 'test.ipynb'),
        )

    @patch('shutil.copy')
    def test_add_helper_file(self, mock_copy):
        # 准备测试数据
        helper_file = 'test_helper.txt'
        mock_dirname = MagicMock(return_value='test_dir')

        with patch('os.path.dirname', mock_dirname):
            # 调用函数
            self.analysis.add_helper_file(helper_file)

            # 验证 shutil.copy 被调用
            mock_copy.assert_called_once_with(
                os.path.join('test_dir', helper_file), os.path.join(self.analysis.output_path, helper_file)
            )

    def test_map_rank_pp_stage(self):
        # 测试用例 1: 默认参数
        distributed_args = {}
        result = self.analysis.map_rank_pp_stage(distributed_args)
        self.assertEqual(result, {0: 0})

        # 测试用例 2: 仅设置 TP_SIZE
        distributed_args = {self.analysis.TP_SIZE: 2}
        result = self.analysis.map_rank_pp_stage(distributed_args)
        self.assertEqual(result, {0: 0, 1: 0})

        # 测试用例 3: 仅设置 PP_SIZE
        distributed_args = {self.analysis.PP_SIZE: 2}
        result = self.analysis.map_rank_pp_stage(distributed_args)
        self.assertEqual(result, {0: 0, 1: 1})

        # 测试用例 4: 设置所有参数
        distributed_args = {self.analysis.TP_SIZE: 2, self.analysis.PP_SIZE: 2, self.analysis.DP_SIZE: 2}
        result = self.analysis.map_rank_pp_stage(distributed_args)
        self.assertEqual(result, {0: 0, 1: 0, 2: 0, 3: 0, 4: 1, 5: 1, 6: 1, 7: 1})

    @patch('os.path.exists')
    @patch('json.loads')
    def test_load_distributed_args_from_extra_args(self, mock_json_loads, mock_exists):
        # 测试从 _extra_args 获取参数
        self.analysis._extra_args = {'tp': 2, 'pp': 2, 'dp': 2}
        result = self.analysis.load_distributed_args()
        self.assertEqual(result, {self.analysis.TP_SIZE: 2, self.analysis.PP_SIZE: 2, self.analysis.DP_SIZE: 2})

    @patch('os.path.exists')
    @patch('json.loads')
    @patch('msprof_analyze.cluster_analyse.recipes.base_recipe_analysis.DatabaseService')
    def test_load_distributed_args_from_db(self, mock_service, mock_json_loads, mock_exists):
        # 测试从数据库获取参数
        mock_exists.return_value = True
        mock_df = MagicMock()
        mock_df.loc.return_value = MagicMock(
            empty=False,
            values=[json.dumps({self.analysis.TP_SIZE: 1, self.analysis.PP_SIZE: 1, self.analysis.DP_SIZE: 1})],
        )
        mock_service.return_value.query_data.return_value = {'META_DATA': mock_df}
        result = self.analysis.load_distributed_args()
        self.assertEqual(result, {self.analysis.TP_SIZE: 1, self.analysis.PP_SIZE: 1, self.analysis.DP_SIZE: 1})

    @patch('os.path.exists')
    def test_get_rank_db(self, mock_exists):
        # 测试 _get_rank_db 函数
        mock_exists.return_value = True
        self.analysis._get_step_range = MagicMock(return_value={'id': 1})
        self.analysis._get_profiler_db_path = MagicMock(return_value='test_profiler.db')
        self.analysis._get_analysis_db_path = MagicMock(return_value='test_analysis.db')
        result = self.analysis._get_rank_db()
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0][Constant.RANK_ID], 0)
        self.assertEqual(result[0][Constant.PROFILER_DB_PATH], 'test_profiler.db')
        self.assertEqual(result[0][Constant.ANALYSIS_DB_PATH], 'test_analysis.db')
        self.assertEqual(result[0][Constant.STEP_RANGE], {'id': 1})

    @patch('msprof_analyze.cluster_analyse.recipes.base_recipe_analysis.logger.warning')
    @patch('os.path.exists')
    def test_get_rank_db_filters_by_required_db_keys_and_logs_summary(self, mock_exists, mock_warning):
        class RequiredDbRecipeAnalysis(BaseRecipeAnalysis):
            @property
            def base_dir(self):
                return 'test_dir'

            @property
            def required_db_keys(self):
                return [Constant.PROFILER_DB_PATH, Constant.ANALYSIS_DB_PATH]

            def run(self, context):
                pass

        params = dict(self.params)
        params[Constant.RANK_LIST] = '0,1,9'
        with patch('msprof_analyze.prof_common.path_manager.PathManager.check_output_directory_path'):
            analysis = RequiredDbRecipeAnalysis(params)

        analysis._get_step_range = MagicMock(return_value={'id': 1})
        analysis._get_profiler_db_path = MagicMock(side_effect=lambda rank_id, _: f'profiler_{rank_id}.db')
        analysis._get_analysis_db_path = MagicMock(
            side_effect=lambda rank_path: f'analysis_{os.path.basename(rank_path)}.db'
        )
        mock_exists.side_effect = lambda path: path in {'profiler_0.db', 'analysis_0.db', 'profiler_1.db'}

        result = analysis._get_rank_db()

        self.assertEqual(
            result,
            [
                {
                    Constant.RANK_ID: 0,
                    Constant.PROFILER_DB_PATH: 'profiler_0.db',
                    Constant.ANALYSIS_DB_PATH: 'analysis_0.db',
                    Constant.STEP_RANGE: {'id': 1},
                    Constant.PROFILING_PATH: '/tmp/to/data/0',
                }
            ],
        )
        mock_warning.assert_has_calls(
            [
                call("Invalid Rank id: [%s].", "9"),
                call(
                    '%s: missing %s for %d rank(s) [%s]; these ranks will be skipped.',
                    'test_recipe',
                    'analysis DB file (analysis.db)',
                    1,
                    '1',
                ),
            ]
        )

    @patch.object(BaseRecipeAnalysis, '_get_rank_db')
    def test_mapper_func_returns_empty_when_no_valid_rank_db(self, mock_get_rank_db):
        mock_get_rank_db.return_value = []
        context = MagicMock()

        result = self.analysis.mapper_func(context)

        self.assertEqual(result, [])
        context.map.assert_not_called()
        context.wait.assert_not_called()

    def test_get_profiler_db_path(self):
        # 测试 _get_profiler_db_path 函数
        # 测试 PyTorch 情况
        result = self.analysis._get_profiler_db_path(0, 'test_path')
        self.assertEqual(result, os.path.join('test_path', Constant.SINGLE_OUTPUT, 'ascend_pytorch_profiler_0.db'))
        result = self.analysis._get_profiler_db_path(-1, 'test_path')
        self.assertEqual(result, os.path.join('test_path', Constant.SINGLE_OUTPUT, 'ascend_pytorch_profiler.db'))

        # 测试 MindSpore 情况
        self.analysis._prof_type = Constant.MINDSPORE
        result = self.analysis._get_profiler_db_path(0, 'test_path')
        self.assertEqual(result, os.path.join('test_path', Constant.SINGLE_OUTPUT, 'ascend_mindspore_profiler_0.db'))
        result = self.analysis._get_profiler_db_path(-1, 'test_path')
        self.assertEqual(result, os.path.join('test_path', Constant.SINGLE_OUTPUT, 'ascend_mindspore_profiler.db'))

    def test_get_analysis_db_path(self):
        # 测试 _get_analysis_db_path 函数
        # 测试 PyTorch 情况
        result = self.analysis._get_analysis_db_path('test_path')
        self.assertEqual(result, os.path.join('test_path', Constant.SINGLE_OUTPUT, 'analysis.db'))

        # 测试 MindSpore 情况
        self.analysis._prof_type = Constant.MINDSPORE
        result = self.analysis._get_analysis_db_path('test_path')
        self.assertEqual(result, os.path.join('test_path', Constant.SINGLE_OUTPUT, 'communication_analyzer.db'))

    @patch('msprof_analyze.cluster_analyse.recipes.base_recipe_analysis.DBManager.create_connect_db')
    @patch('msprof_analyze.cluster_analyse.recipes.base_recipe_analysis.DBManager.judge_table_exists')
    @patch('msprof_analyze.cluster_analyse.recipes.base_recipe_analysis.DBManager.fetch_all_data')
    @patch('msprof_analyze.cluster_analyse.recipes.base_recipe_analysis.DBManager.destroy_db_connect')
    def test_get_step_range(self, mock_destroy, mock_fetch, mock_judge, mock_connect):
        # 测试 _get_step_range 函数
        mock_conn, mock_cursor = MagicMock(), MagicMock()
        mock_connect.return_value = (mock_conn, mock_cursor)
        mock_judge.return_value = True
        mock_fetch.return_value = [{'id': 1, 'startNs': 0, 'endNs': 100}]
        self.analysis._step_id = 1
        result = self.analysis._get_step_range('test.db')
        self.assertEqual(result, {'id': 1, 'startNs': 0, 'endNs': 100})


if __name__ == '__main__':
    unittest.main()
