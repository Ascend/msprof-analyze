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
from unittest.mock import MagicMock, patch

from msprof_analyze.advisor.analyzer.computation.operator_checker import OperatorChecker
from msprof_analyze.advisor.dataset.profiling.info_collection import OpInfo
from msprof_analyze.advisor.dataset.profiling.profiling_dataset import ProfilingDataset
from msprof_analyze.advisor.result.item import OptimizeRecord


class TestOperatorChecker(unittest.TestCase):
    def setUp(self):
        self.cann_version = "8.0.RC1"
        self.checker = OperatorChecker(self.cann_version)
        self.profiling_data = MagicMock(spec=ProfilingDataset)
        self.op_info = MagicMock(spec=OpInfo)
        self.op_info.has_attr.return_value = True
        self.op_info.get_attr.return_value = "10"
        self.op_info.task_duration = "10"
        self.op_info.op_name = ""

    def test_init(self):
        self.assertEqual(self.checker.cann_version, self.cann_version)
        self.assertEqual(len(self.checker._op_list), 0)
        self.assertEqual(len(self.checker._tune_op_list), 0)

    def test_get_ratio(self):
        result = OperatorChecker.get_ratio(self.op_info, "attr")
        self.assertEqual(result, 10)

        self.op_info.has_attr.return_value = False
        result = OperatorChecker.get_ratio(self.op_info, "attr")
        self.assertEqual(result, 0)

        self.op_info.has_attr.return_value = True
        self.op_info.get_attr.return_value = None
        result = OperatorChecker.get_ratio(self.op_info, "attr")
        self.assertEqual(result, 0)

    def test_get_name(self):
        self.checker._problem = "Test Problem"
        result = self.checker.get_name()
        self.assertEqual(result, "Test Problem")

    @patch.object(OperatorChecker, '_check_data')
    @patch.object(OperatorChecker, '_check_operator')
    def test_check(self, mock_check_operator, mock_check_data):
        mock_check_data.return_value = True
        mock_check_operator.return_value = True
        self.profiling_data.op_summary = MagicMock()
        self.profiling_data.op_summary.op_list = [self.op_info]
        self.profiling_data.op_summary.get_total_task_duration.return_value = 100

        result = self.checker.check(self.profiling_data)
        self.assertTrue(result)

    @patch.object(OperatorChecker, 'get_incomes')
    @patch.object(OperatorChecker, 'get_op_type_list')
    @patch.object(OperatorChecker, '_get_description')
    def test_make_record(self, mock_get_description, mock_get_op_type_list, mock_get_incomes):
        mock_get_incomes.return_value = 100
        mock_get_op_type_list.return_value = ["OpType1"]
        mock_get_description.return_value = "Test Description"
        self.profiling_data.op_summary = MagicMock()
        self.profiling_data.op_summary.get_total_task_duration.return_value = 1000

        record = self.checker.make_record(self.profiling_data)
        self.assertIsInstance(record, OptimizeRecord)

    def test_pre_check(self):
        result = self.checker.pre_check(self.profiling_data)
        self.assertTrue(result)

    @patch('msprof_analyze.advisor.analyzer.computation.operator_checker.EnumParamsParser.get_options')
    def test_is_dynamic_shape(self, mock_get_options):
        mock_get_options.return_value = ["7.0.RC1"]
        self.checker.cann_version = "7.0.RC1"
        self.profiling_data.ge_info = MagicMock()
        self.profiling_data.ge_info.get_static_shape_operators.return_value = []

        result = self.checker.is_dynamic_shape(self.profiling_data)
        self.assertTrue(result)

    @patch.object(OperatorChecker, 'group_by')
    def test_format_operator_result(self, mock_group_by):
        mock_record = MagicMock()
        mock_record.optimization_item.suggestion = [self.checker.pytorch_op_tune_suggestion]
        mock_group_by.return_value = []

        result = self.checker.format_operator_result(mock_record, 10)
        self.assertIsInstance(result, dict)

    def test_group_by(self):
        op_list = [self.op_info]
        result = self.checker.group_by(op_list)
        self.assertIsInstance(result, list)

    def test_get_tune_op_list(self):
        self.checker._tune_op_list = ["Op1", "Op2"]
        result = self.checker.get_tune_op_list()
        self.assertEqual(result, ["Op1", "Op2"])

    def test_get_views(self):
        result = self.checker.get_views(None)
        self.assertEqual(result, [])

    @patch.object(OperatorChecker, '_get_income')
    def test_get_incomes(self, mock_get_income):
        mock_get_income.return_value = 10
        self.checker._op_list = [self.op_info]
        result = self.checker.get_incomes()
        self.assertEqual(result, 10)

    def test_get_op_type_list(self):
        self.op_info.op_type = "OpType1"
        op_list = [self.op_info]
        result = self.checker.get_op_type_list(op_list)
        self.assertEqual(result, ["OpType1"])

    def test_get_details(self):
        self.checker._op_list = [self.op_info]
        self.checker._ITEMS = ["attr"]
        self.checker.STACK_INFO_ITEMS = ""
        result = self.checker.get_details()
        self.assertIsInstance(result, list)

    @patch('msprof_analyze.advisor.analyzer.computation.operator_checker.EnumParamsParser')
    def test_format_suggestion_content(self, mock_enum_parser):
        mock_enum_parser().profiling_type.ascend_pytorch_profiler = "pytorch"
        self.profiling_data.prof_type = "pytorch"

        self.checker.format_suggestion_content(self.profiling_data)
        self.assertIn(self.checker.pytorch_op_tune_suggestion, self.checker._suggestion)

    def test__check_data(self):
        result = self.checker._check_data(self.profiling_data)
        self.assertTrue(result)

    def test__check_operator(self):
        result = self.checker._check_operator(self.op_info)
        self.assertFalse(result)

    def test__get_income(self):
        result = self.checker._get_income(self.op_info)
        self.assertEqual(result, 0)

    def test__check_summary(self):
        self.profiling_data.op_summary = None
        result = self.checker._check_summary(self.profiling_data)
        self.assertTrue(result)

        self.profiling_data.op_summary = MagicMock()
        result = self.checker._check_summary(self.profiling_data)
        self.assertTrue(result)

    def test__get_description(self):
        description = "Test Description"
        op_type_list = ["OpType1", "OpType2", "OpType3"]
        result = self.checker._get_description(description, op_type_list)
        self.assertIn("OpType1", result)


if __name__ == '__main__':
    unittest.main()
