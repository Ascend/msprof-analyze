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
from typing import Container
from unittest.mock import MagicMock, patch

from msprof_analyze.advisor.analyzer.computation.vector_bottleneck_operator.vector_bottleneck_op_checker import \
    VectorBottleneckOPChecker, OperatorPriority
from msprof_analyze.prof_common.constant import Constant


class TestVectorBottleneckOPChecker(unittest.TestCase):

    def setUp(self):
        self.collection_path = "/path/to/collection"
        self.checker = VectorBottleneckOPChecker(self.collection_path)

    @patch('msprof_analyze.advisor.analyzer.computation.'
           'vector_bottleneck_operator.vector_bottleneck_op_checker.FileManager')
    @patch('msprof_analyze.advisor.analyzer.computation.'
           'vector_bottleneck_operator.vector_bottleneck_op_checker.AdditionalArgsManager')
    def test_load_threshold_op_rules(self, mock_lan, mock_filer):
        mock_lan.return_value.language = 'en'
        mock_filer.read_yaml_file.return_value = {
            'problem': 'Problem',
            'description': 'Description',
            'suggestion': 'Suggestion'
        }
        self.checker.load_threshold_op_rules()
        mock_filer.read_yaml_file.assert_called_once()
        self.assertEqual(self.checker._problem, 'Problem')
        self.assertEqual(self.checker._description, 'Description')
        self.assertEqual(self.checker._suggestion, ['Suggestion'])
        self.assertIsNotNone(self.checker.op_checker)

    @patch('msprof_analyze.advisor.analyzer.computation.'
           'vector_bottleneck_operator.vector_bottleneck_op_checker.ProfilingDataset')
    def test_check(self, mock_data):
        mock_data.op_summary.get_total_task_duration.return_value = 100
        mock_data.op_summary.op_list = [
            MagicMock(op_type='op1', task_duration=4, op_name='op1_name'),
            MagicMock(op_type='op2', task_duration=3, op_name='op2_name')
        ]
        self.checker.op_checker.contains = MagicMock(return_value=False)
        self.checker.step_trace_time_avg_step_time = MagicMock(return_value=50)

        result = self.checker.check(mock_data)
        self.assertFalse(result)
        self.assertEqual(self.checker._priority, OperatorPriority.LOW)

    @patch('msprof_analyze.advisor.analyzer.computation.'
           'vector_bottleneck_operator.vector_bottleneck_op_checker.ProfilingDataset')
    def test_get_operator_stack_info(self, mock_data):
        mock_data.data_type = Constant.TEXT
        mock_data.collection_path = '/path/to/collection'

        self.checker.query_stack_from_timeline_json = MagicMock(return_value=[("task1", 'stack1')])
        stack_info = self.checker.get_operator_stack_info(mock_data, {'op1': 'AI_CORE'})

        self.assertEqual(stack_info, [('task1', 'stack1')])


if __name__ == '__main__':
    unittest.main()