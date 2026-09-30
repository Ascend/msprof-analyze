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

from msprof_analyze.advisor.common.timeline.fusion_ops_rule import OpRule


class TestOpRule(unittest.TestCase):
    """Test cases for OpRule class"""

    def setUp(self):
        """Set up test fixtures before each test method."""
        self.mock_timeline_op_rule_handler = MagicMock()
        self.mock_timeline_op_rule_handler.get_tmp_timeline_op_rule_with_unique_id.return_value = {
            'aten': {'add': [{'torch_npu.fast_gelu': 'gelu'}]}
        }

    def test_when_initialized_without_params_then_create_empty_rule(self):
        """Test OpRule initialization without parameters"""
        op_rule = OpRule()

        self.assertEqual(op_rule.tmp_rule, {})
        self.assertEqual(op_rule.timeline_op_rule_handler, {})
        self.assertEqual(op_rule._rule, {})

    def test_when_initialized_with_rule_then_set_rule_correctly(self):
        """Test OpRule initialization with rule parameter"""
        test_rule = {'aten': {'add': [{'torch_npu.fast_gelu': 'gelu'}]}}
        op_rule = OpRule(rule=test_rule)

        self.assertEqual(op_rule.tmp_rule, test_rule)

    def test_when_initialized_with_handler_then_sets_handler_correctly(self):
        """Test OpRule initialization with timeline_op_rule_handler parameter"""
        op_rule = OpRule(timeline_op_rule_handler=self.mock_timeline_op_rule_handler)

        self.assertEqual(op_rule.timeline_op_rule_handler, self.mock_timeline_op_rule_handler)

    def test_when_format_rule_with_mixed_values_then_formats_correctly(self):
        """Test _format_rule static method with mixed string and list values"""
        rule = {
            'Conv2D': 'torch.nn.functional.conv2d',
            'BatchNorm': ['torch.nn.functional.batch_norm']
        }
        formatted_rule = OpRule._format_rule(rule)

        expected = {
            'Conv2D': ['torch.nn.functional.conv2d'],
            'BatchNorm': ['torch.nn.functional.batch_norm']
        }
        self.assertEqual(formatted_rule, expected)

    def test_when_merge_with_valid_function_then_calls_correct_method(self):
        """Test merge method with valid function name"""
        op_rule = OpRule()
        extra_rule = {
            'aten': {
                'add': {'torch_npu.fast_gelu': ['gelu']}
            }
        }
        op_rule.merge(extra_rule)
        self.assertEqual(op_rule.tmp_rule['aten']['torch_npu.fast_gelu'], ['gelu'])

    @patch('msprof_analyze.advisor.common.timeline.fusion_ops_rule.logger')
    def test_when_merge_with_invalid_function_then_logs_error(self, mock_logger):
        """Test merge method with invalid function name"""
        op_rule = OpRule()
        extra_rule = {
            'aten': {
                'invalid_function': {'torch_npu.fast_gelu': ['gelu']}
            }
        }
        op_rule.merge(extra_rule)
        mock_logger.error.assert_called_once()

    def test_when_get_final_rules_then_returns_formatted_rules(self):
        """Test get_final_rules method returns correctly formatted rules"""
        op_rule = OpRule()
        op_rule._tmp_rule = {
            'aten': {
                'npu_swiglu': ['(slice)-silu-mul'],
                'addmm': ['mul-mul-add']
            }
        }

        result = op_rule.get_final_rules()

        expected = [
            {'npu_swiglu': ['(slice)-silu-mul']},
            {'addmm': ['mul-mul-add']}
        ]
        self.assertEqual(result['aten'], expected)

    def test_when_add_with_none_rules_then_does_nothing(self):
        """Test add method with None rules"""
        op_rule = OpRule()
        initial_rule = op_rule.tmp_rule.copy()

        op_rule.add('aten', None)

        self.assertEqual(op_rule.tmp_rule, initial_rule)

    def test_when_add_existing_key_then_updates_existing_entry(self):
        """Test add method with existing key"""
        op_rule = OpRule()
        op_rule._tmp_rule = {'aten': {'torch_npu.npu_gelu': ['(slice)-gelu-mul', '(chunk)-gelu-mul']}}
        add_rules = {'torch_npu.npu_gelu': ['(slice)-mul-gelu', '(chunk)-mul-gelu']}

        op_rule.add('aten', add_rules)

        expected = ['(slice)-mul-gelu', '(chunk)-mul-gelu']
        self.assertEqual(op_rule.tmp_rule['aten']['torch_npu.npu_gelu'], expected)

    def test_when_overwrite_with_none_rules_then_does_nothing(self):
        """Test overwrite method with None rules"""
        op_rule = OpRule()
        initial_rule = op_rule.tmp_rule.copy()
        op_rule.overwrite('aten', None)
        self.assertEqual(op_rule.tmp_rule, initial_rule)

    @patch('msprof_analyze.advisor.common.timeline.fusion_ops_rule.logger')
    def test_when_overwrite_new_key_then_logs_warning(self, mock_logger):
        """Test overwrite method with new key logs warning"""
        op_rule = OpRule()
        overwrite_rules = {'api': ['torch.nn.functional.conv2d']}

        op_rule.overwrite('aten', overwrite_rules)
        self.assertEqual(op_rule.tmp_rule['aten']['api'], ['torch.nn.functional.conv2d'])
        mock_logger.warning.assert_called_once()

    def test_when_overwrite_existing_key_then_updates_existing_entry(self):
        """Test overwrite method with existing key"""
        op_rule = OpRule()
        op_rule._tmp_rule = {'aten': {'torch_npu.npu_gelu': ['(slice)-gelu-mul', '(chunk)-gelu-mul']}}
        add_rules = {'torch_npu.npu_gelu': ['(slice)-mul-gelu', '(chunk)-mul-gelu']}

        op_rule.overwrite('aten', add_rules)

        expected = ['(slice)-mul-gelu', '(chunk)-mul-gelu']
        self.assertEqual(op_rule.tmp_rule['aten']['torch_npu.npu_gelu'], expected)

    def test_when_exclude_with_none_rules_then_does_nothing(self):
        """Test exclude method with None rules"""
        op_rule = OpRule()
        op_rule._tmp_rule = {'aten': {'addmm': ['mul-mul-add']}}
        initial_rule = op_rule.tmp_rule.copy()
        op_rule.exclude('aten', None)
        self.assertEqual(op_rule.tmp_rule, initial_rule)

    def test_when_exclude_existing_key_then_removes_key(self):
        """Test exclude method with existing key"""
        op_rule = OpRule()
        op_rule._tmp_rule = {
            'aten': {
                'npu_swiglu': ['(slice)-silu-mul'],
                'addmm': ['mul-mul-add']
            }
        }
        exclude_rules = ['addmm']
        op_rule.exclude('aten', exclude_rules)
        self.assertNotIn('addmm', op_rule.tmp_rule['aten'])
        self.assertIn('npu_swiglu', op_rule.tmp_rule['aten'])

    @patch('msprof_analyze.advisor.common.timeline.fusion_ops_rule.logger')
    def test_when_exclude_nonexistent_key_then_logs_warning(self, mock_logger):
        """Test exclude method with nonexistent key logs warning"""
        op_rule = OpRule()
        op_rule._tmp_rule = {'aten': {'addmm': ['mul-mul-add']}}
        exclude_rules = ['nonexistent']
        op_rule.exclude('aten', exclude_rules)
        mock_logger.warning.assert_called_once()

    @patch('msprof_analyze.advisor.common.timeline.fusion_ops_rule.logger')
    def test_when_exclude_invalid_type_then_logs_warning(self, mock_logger):
        """Test exclude method with invalid type logs warning"""
        op_rule = OpRule()
        op_rule._tmp_rule = {'aten': {'addmm': ['mul-mul-add']}}
        exclude_rules = [123]  # Invalid type
        op_rule.exclude('aten', exclude_rules)
        mock_logger.warning.assert_called_once()

    def test_when_inherit_unique_id_with_valid_handler_then_inherits_rule(self):
        """Test inherit_unique_id method with valid handler"""
        op_rule = OpRule(timeline_op_rule_handler=self.mock_timeline_op_rule_handler)

        op_rule.inherit_unique_id('aten', 2)

        expected = {'add': [{'torch_npu.fast_gelu': 'gelu'}]}
        self.assertEqual(op_rule.tmp_rule['aten'], expected)

    def test_when_inherit_unique_id_with_none_result_then_does_nothing(self):
        """Test inherit_unique_id method with None result from handler"""
        mock_handler = MagicMock()
        mock_handler.get_tmp_timeline_op_rule_with_unique_id.return_value = None
        op_rule = OpRule(timeline_op_rule_handler=mock_handler)
        op_rule.inherit_unique_id('aten', 1)
        self.assertEqual(op_rule.tmp_rule, {})


if __name__ == '__main__':
    unittest.main()
