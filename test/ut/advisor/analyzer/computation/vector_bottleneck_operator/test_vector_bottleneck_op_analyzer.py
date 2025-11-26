# Copyright (c) 2025-2026, Huawei Technologies Co., Ltd.
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
from unittest.mock import MagicMock, patch

from msprof_analyze.advisor.analyzer.computation.vector_bottleneck_operator.vector_bottleneck_op_analyzer import \
    VectorBottleneckOPAnalyzer, OperatorPriority
from msprof_analyze.advisor.result.result import OptimizeResult
from msprof_analyze.advisor.display.html.priority_background_color import PriorityBackgroundColor


class TestVectorBottleneckOPAnalyzer(unittest.TestCase):
    def setUp(self):
        self.collection_path = "/path/to/collection"
        self.analyzer = VectorBottleneckOPAnalyzer(self.collection_path)


    @patch('msprof_analyze.advisor.analyzer.computation.'
           'vector_bottleneck_operator.vector_bottleneck_op_analyzer.ProfilingDataset')
    @patch('msprof_analyze.advisor.analyzer.computation.'
           'vector_bottleneck_operator.vector_bottleneck_op_analyzer.VectorBottleneckOPChecker')
    def test_optimize(self, mock_checker, mock_dataset):
        mock_checker_instance = MagicMock()
        mock_checker.return_value = mock_checker_instance
        mock_dataset_instance = MagicMock()
        mock_dataset.return_value = mock_dataset_instance

        mock_checker_instance.pre_check_value = True
        mock_checker_instance.check.return_value = True
        mock_checker_instance.make_render.return_value = "html_content"
        mock_checker_instance.get_details.return_value = [['Header1', 'Header2'], ['Detail1', 'Detail2']]
        mock_checker_instance.get_name.return_value = 'CheckerName'
        mock_checker_instance.get_tune_op_list.return_value = ["TyneOp1", 'TuneOp2']

        mock_result = MagicMock(sepc=OptimizeResult)
        self.analyzer.result = mock_result
        result = self.analyzer.optimize(rank=1, add_render_list=True)
        self.assertEqual(result, mock_result)

    def test_get_priority(self):
        mock_checker = MagicMock()
        mock_checker.priority = OperatorPriority.HIGH
        self.assertEqual(self.analyzer.get_priority(mock_checker), PriorityBackgroundColor.high)

        mock_checker.priority = OperatorPriority.MEDIUM_LOW
        self.assertEqual(self.analyzer.get_priority(mock_checker), PriorityBackgroundColor.medium)

        mock_checker.priority = OperatorPriority.LOW
        self.assertEqual(self.analyzer.get_priority(mock_checker), PriorityBackgroundColor.low)

if __name__ == '__main__':
    unittest.main()