# -------------------------------------------------------------------------
# This file is part of the MindStudio project.
# Copyright (c) 2024 Huawei Technologies Co.,Ltd.
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

from msprof_analyze.advisor.analyzer.computation.aicpu.aicpu_checker import AicpuChecker, BaserChecker, CommonChecker, \
    ExampleGuideChecker
from msprof_analyze.advisor.dataset.profiling.profiling_dataset import ProfilingDataset
from msprof_analyze.prof_common.constant import Constant


class TestAicpuChecker(unittest.TestCase):
    def setUp(self):
        self.cann_version = '1.0'
        self.checker = AicpuChecker(self.cann_version)

    @patch('msprof_analyze.prof_common.file_manager.FileManager.read_yaml_file')
    @patch('os.path.exists')
    def test_load_aicpu_rules(self, mock_exists, mock_read_yaml):
        mock_exists.return_value = True
        mock_read_yaml.return_value = {
            'problem': 'test_problem',
            'description': 'test_description',
            'suggestion': 'test_suggestion',
            'double_suggestion': 'test_double_suggestion',
            'CommonChecker': [{'DataTypeChecker': {'cann_version': [self.cann_version]}}]
        }
        self.checker.load_aicpu_rules()
        self.assertEqual(self.checker._problem, 'test_problem')
        self.assertEqual(self.checker._description, 'test_description')
        self.assertEqual(self.checker._suggestion, ['test_suggestion'])
        self.assertEqual(self.checker.double_suggestion, 'test_double_suggestion')

    def test_filter_aicpu_rules(self):
        aicpu_rules = {
            'CommonChecker': [
                {'DataTypeChecker': {'cann_version': [self.cann_version]}},
                {'OtherChecker': {'cann_version': ['2.0']}}
            ]
        }
        self.checker.filter_aicpu_rules(aicpu_rules)
        self.assertEqual(len(aicpu_rules['CommonChecker']), 1)

    def test_check_aicpu_attr(self):
        mock_checker = MagicMock()
        mock_checker.check.return_value = ['suggestion']
        self.checker.aicpu_checker = {'test': mock_checker}
        op_info = MagicMock()
        result = self.checker.check_aicpu_attr(op_info)
        self.assertEqual(result, ['suggestion'])

    @patch(
        'msprof_analyze.advisor.analyzer.computation.aicpu.aicpu_checker.AicpuChecker.query_stack_from_timeline_json')
    @patch('msprof_analyze.advisor.analyzer.computation.aicpu.aicpu_checker.AicpuChecker.query_stack_from_db')
    def test_get_operator_stack_info(self, mock_query_db, mock_query_json):
        mock_profiling_data = MagicMock(spec=ProfilingDataset)
        mock_profiling_data.data_type = Constant.TEXT
        mock_profiling_data.collection_path = 'test_path'
        op_name_list = ['test_op']
        self.checker.get_operator_stack_info(mock_profiling_data, op_name_list)
        mock_query_json.assert_called_once()

    @patch('msprof_analyze.advisor.dataset.timeline_event_dataset.ComputationAnalysisDataset')
    @patch('msprof_analyze.advisor.dataset.stack.timeline_stack_finder.TimelineOpStackFinder')
    def test_query_stack_from_timeline_json(self, mock_stack_finder, mock_event_dataset):
        collection_path = 'test_path'
        op_name_list = ['test_op']
        task_type = Constant.AI_CPU
        self.checker.query_stack_from_timeline_json(collection_path, op_name_list, task_type)

    @patch('msprof_analyze.advisor.dataset.stack.db_stack_finder.DBStackFinder')
    def test_query_stack_from_db(self, mock_db_stack_finder):
        db_path = 'test_path'
        op_name_list = ['test_op']
        task_type = Constant.AI_CPU
        self.checker.query_stack_from_db(db_path, op_name_list, task_type)

    def test_make_render(self):
        html_render = MagicMock()
        record = MagicMock()
        self.checker.make_render(html_render, record)
        html_render.render_template.assert_called_once()

    def test_format_operator_result(self):
        record = MagicMock()
        limit = 10
        result = self.checker.format_operator_result(record, limit)
        self.assertIsInstance(result, dict)

    def test_group_by_list(self):
        op_list = [MagicMock()]
        result = self.checker.group_by_list(op_list)
        self.assertIsNotNone(result)

    @patch('msprof_analyze.advisor.analyzer.computation.aicpu.aicpu_checker.AicpuChecker._check_summary')
    def test__check_data(self, mock_check_summary):
        mock_check_summary.return_value = True
        mock_profiling_data = MagicMock(spec=ProfilingDataset)
        result = self.checker._check_data(mock_profiling_data)
        self.assertTrue(result)

    def test__check_operator(self):
        op_info = MagicMock(task_type=Constant.AI_CPU)
        result = self.checker._check_operator(op_info)
        self.assertTrue(result)


class TestBaserChecker(unittest.TestCase):
    def setUp(self):
        self.checker = BaserChecker()

    def test_build(self):
        with self.assertRaises(NotImplementedError):
            self.checker.build()

    def test_check(self):
        mock_checker = MagicMock(return_value='suggestion')
        self.checker.checker_list = [mock_checker]
        op_info = MagicMock()
        result = self.checker.check(op_info)
        self.assertEqual(result, ['suggestion'])


class TestCommonChecker(unittest.TestCase):
    def setUp(self):
        check_rules = [{'DataTypeChecker': {'cann_version': ['1.0']}}]
        self.checker = CommonChecker(check_rules)

    def test_datatype_checker(self):
        check_item = {
            'op_type': ['__ALL__'],
            'suggestion': 'test_suggestion',
            'input': ['float'],
            'output': ['float'],
            'ignore_type': []
        }
        op_info = MagicMock(op_type='TestOp', input_data_types='double;int', output_data_types='double')
        result = CommonChecker.datatype_checker(check_item, op_info)
        self.assertEqual(result, 'test_suggestion')

    def test_build(self):
        self.assertEqual(len(self.checker.checker_list), 1)


class TestExampleGuideChecker(unittest.TestCase):
    def setUp(self):
        check_rules = [{'Guide': {'op_type': ['test_op'], 'url': 'test_url', 'suggestion': 'test_suggestion'}}]
        self.checker = ExampleGuideChecker(check_rules)

    def test_build(self):
        self.assertEqual(len(self.checker.checker_list), 1)


if __name__ == '__main__':
    unittest.main()
