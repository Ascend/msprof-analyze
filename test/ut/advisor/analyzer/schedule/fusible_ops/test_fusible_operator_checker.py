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
from collections import OrderedDict
from unittest.mock import MagicMock, patch

from msprof_analyze.advisor.analyzer.schedule.fusible_ops.fusible_operator_checker import FusibleOperatorChecker
from msprof_analyze.advisor.result.result import OptimizeResult


class TestFusibleOperatorChecker(unittest.TestCase):
    @staticmethod
    def get_mock_task():
        task = MagicMock()
        task.task_start_time = '1726054679556790.226'
        task.task_duration = '120.0'
        task.aicore_time = '50'
        task.aic_mte2_time = '10'
        task.aiv_mte2_time = '20'
        task.aic_fixpipe_time = '30'
        task.aiv_mte3_time = '40'
        task.op_name = 'aclnnReduceSum_ReduceSumOpAiCore_ReduceSum'
        task.task_type = 'MIX_AIC'
        task.input_shapes = '"41;1"'
        task.output_shapes = '""'
        return task

    def setUp(self):
        self.checker = FusibleOperatorChecker()

    def test_get_mte_time(self):
        task = MagicMock()
        task.aic_mte2_time = '10'
        task.aiv_mte2_time = '20'
        task.aic_fixpipe_time = '30'
        task.aiv_mte3_time = '40'
        result = FusibleOperatorChecker.get_mte_time(task)
        self.assertEqual(result, 60.0)

    def test_check_hccl(self):
        task1 = MagicMock(task_type='COMMUNICATION', op_name='hcom_op')
        task2 = MagicMock(task_type='OTHER', op_name='normal_op')
        self.assertTrue(FusibleOperatorChecker.check_hccl(task1))
        self.assertFalse(FusibleOperatorChecker.check_hccl(task2))

    def test_calculate_total_time(self):
        pre_timestamp = '10'
        timestamp = '20'
        duration = '5'
        result, flag = FusibleOperatorChecker.calculate_total_time(pre_timestamp, timestamp, duration)
        self.assertEqual(result, 15)
        self.assertTrue(flag)

    def test_check_sequence_ratio(self):
        detail = [100, 0, 0, 0, False, False]
        self.checker.step_duration = 50
        self.checker.sequence_duration_threshold = 0.1
        result = self.checker.check_sequence_ratio(detail)
        self.assertTrue(result)

    def test_check_sequence_num(self):
        detail = [0, 0, 0, 10, False, False]
        self.checker.sequence_count_threshold = 5
        result = self.checker.check_sequence_num(detail)
        self.assertTrue(result)

    def test_check_bound(self):
        detail1 = [100, 0, 0, 0, True, False]
        detail2 = [10, 0, 0, 0, False, False]
        self.checker.step_duration = 50
        self.checker.sequence_duration_threshold = 0.3
        self.assertTrue(self.checker.check_bound(detail1))
        self.assertFalse(self.checker.check_bound(detail2))

    def test_add_detail(self):
        task_name = 'test_task'
        details = []
        detail = [100, 50, 30, 2, True, False]
        self.checker.index_dict[task_name] = (0, 1)
        self.checker.add_detail(task_name, details, detail)
        self.assertEqual(len(details), 1)

    def test_generate_key(self):
        task = MagicMock(op_name='test_op', input_shapes='[1,2]', output_shapes='[2,3]')
        result = self.checker.generate_key(task)
        self.assertEqual(result, 'test_op-[1,2]-[2,3]')

    def test_compute_priority(self):
        self.checker.host_details = [[100, 0, 0, 0, False, False]]
        self.checker.mte_details = []
        self.checker.step_duration = 50
        result = self.checker.compute_priority()
        from msprof_analyze.advisor.display.html.priority_background_color import PriorityBackgroundColor
        self.assertEqual(result, PriorityBackgroundColor.high)

    def test_check_tasks(self):
        profiling_dataset = MagicMock()
        profiling_dataset.op_summary.op_list = [MagicMock()]
        with patch('msprof_analyze.advisor.analyzer.schedule.fusible_ops.fusible_operator_checker.' \
                   'FusibleOperatorChecker.calculate_total_time') as mock_calculate:
            mock_calculate.return_value = (100, True)
            result = self.checker.check_tasks(profiling_dataset)
            self.assertTrue(result)

    def test_make_record(self):
        result = OptimizeResult()
        self.checker.problem = 'test_problem'
        self.checker.desc = 'test_desc'
        self.checker.suggestions = ['test_suggestion']
        self.checker.host_details = [[1, 2, 100, 50, 30, 2, True, False]]
        self.checker.mte_details = [[3, 4, 200, 100, 60, 3, False, True]]
        self.checker.make_record(result)
        self.assertTrue(result.page_dict)


    def test_check_fusible_operator_should_return_when_check_tasks_failed(self):
        profiling_dataset = MagicMock()
        self.checker.check_fusible_operator(profiling_dataset)

    @patch("msprof_analyze.advisor.analyzer.schedule.fusible_ops.fusible_operator_checker."
           "FusibleOperatorChecker.post_processing")
    def test_check_fusible_operator_should_return_when_check_tasks_succeeded(self, mock_post_processing):
        profiling_dataset = MagicMock()
        task1 = self.get_mock_task()
        task2 = self.get_mock_task()
        task3 = self.get_mock_task()
        task2.task_start_time = '1726054679557300.226'
        task3.task_start_time = '1726054679557500.226'
        profiling_dataset.op_summary.op_list = [task1, task2, task3]
        self.checker.check_fusible_operator(profiling_dataset)
        args, kwargs = mock_post_processing.call_args
        self.assertEqual(len(args[0]), 1)

    def test_post_processing_should_set_fusion_issues_to_true_when_result_not_empty(self):
        result_dict = OrderedDict()
        result_dict['test_task1'] = (100, 50, 30, 6, True, True)
        result_dict['test_task2'] = (100, 50, 30, 6, False, True)
        self.checker.step_duration = 150
        self.checker.post_processing(result_dict)
        self.assertTrue(self.checker.fusion_issues)


if __name__ == '__main__':
    unittest.main()
