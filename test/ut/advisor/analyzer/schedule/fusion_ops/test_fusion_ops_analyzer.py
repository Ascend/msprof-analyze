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

from msprof_analyze.advisor.analyzer.schedule.fusion_ops.fusion_ops_analyzer import TimelineFusionOpsAnalyzer
from msprof_analyze.advisor.dataset.timeline_event_dataset import ScheduleAnalysisDataset
from msprof_analyze.advisor.display.html.priority_background_color import PriorityBackgroundColor
from msprof_analyze.prof_common.constant import Constant


class TestTimelineFusionOpsAnalyzer(unittest.TestCase):
    def setUp(self):
        self.collection_path = 'test_path'
        self.analyzer = TimelineFusionOpsAnalyzer(self.collection_path)
        self.analyzer.dataset_list = [MagicMock()]
        self.analyzer.result = MagicMock()
        self.analyzer.html_render = MagicMock()

    def test_init(self):
        self.assertIsInstance(self.analyzer, TimelineFusionOpsAnalyzer)
        self.assertEqual(len(self.analyzer.dataset_cls_list), 1)
        self.assertEqual(self.analyzer.dataset_cls_list[0], ScheduleAnalysisDataset)

    def test_get_priority(self):
        result = self.analyzer.get_priority()
        self.assertEqual(result, PriorityBackgroundColor.low)

    @patch('os.getenv')
    def test_optimize_skip_affinity_api(self, mock_getenv):
        mock_getenv.return_value = 'true'
        result = self.analyzer.optimize()
        self.assertEqual(result, self.analyzer.result)

    def test_find_fusion_ops_no_regex(self):
        event_dataset = MagicMock()
        ops = 'permute-reshape'
        npu_api = 'torch_npu_api'
        mode = 'aten'

        with patch.object(self.analyzer, '_format_rule_to_pattern') as mock_format, \
                patch.object(self.analyzer, '_match_ops') as mock_match:
            mock_format.return_value = (ops, False)
            self.analyzer.find_fusion_ops(event_dataset, ops, npu_api, mode)

            mock_format.assert_called_once_with(ops)
            mock_match.assert_called_once_with(event_dataset, ops, npu_api, mode)

    def test_find_fusion_ops_with_regex(self):
        event_dataset = MagicMock()
        ops = 'add-mul{0,10}'
        npu_api = 'torch_npu_api'
        mode = 'aten'

        with patch.object(self.analyzer, '_format_rule_to_pattern') as mock_format, \
                patch.object(self.analyzer, '_match_ops_with_regex') as mock_match:
            mock_format.return_value = (ops, True)
            self.analyzer.find_fusion_ops(event_dataset, ops, npu_api, mode)

            mock_format.assert_called_once_with(ops)
            mock_match.assert_called_once_with(event_dataset, ops, npu_api, mode)

    def test_find_fusion_ops_with_regex_exception(self):
        event_dataset = MagicMock()
        ops = 'add-mul{0,10}'
        npu_api = 'torch_npu_api'
        mode = 'aten'

        with patch.object(self.analyzer, '_format_rule_to_pattern') as mock_format, \
                patch.object(self.analyzer, '_match_ops_with_regex') as mock_match:
            mock_format.return_value = (ops, True)
            mock_match.side_effect = Exception('Test exception')
            self.analyzer.find_fusion_ops(event_dataset, ops, npu_api, mode)

            mock_format.assert_called_once_with(ops)
            mock_match.assert_called_once_with(event_dataset, ops, npu_api, mode)

    def test_make_record_no_stacks(self):
        self.analyzer.matched_op_stacks = {}
        self.analyzer.make_record()
        self.analyzer.result.add.assert_not_called()

    @patch('msprof_analyze.advisor.display.prompt.base_prompt.BasePrompt.get_prompt_class')
    def test_make_record_with_stacks(self, mock_get_prompt_class):
        mock_prompt_class = MagicMock()
        mock_prompt_class.DESCRIPTION = 'Description {0} {1} {2}'
        mock_prompt_class.SUGGESTION = 'Suggestion'
        mock_prompt_class.PROBLEM = 'Problem'
        mock_prompt_class.EMPTY_STACK_DESCRIPTION = ''
        mock_prompt_class.EMPTY_STACKS_SUGGESTION = ''
        mock_get_prompt_class.return_value = mock_prompt_class

        self.analyzer.matched_op_stacks = {'api_name': {'stack': 1}}
        self.analyzer.make_record()

        self.analyzer.result.add.assert_called_once()
        self.analyzer.result.add_detail.assert_called()

    def test_make_render(self):
        self.analyzer.matched_op_stacks = {'api_name': {'stack': 1}}
        self.analyzer.make_render(rank=1)

        self.analyzer.html_render.render_template.assert_called_once()

    def test_query_stack_no_matches(self):
        self.analyzer._matched_op_index = {'op_rule': []}
        event_dataset = MagicMock()
        self.analyzer.query_stack(event_dataset)
        event_dataset.parse_data_with_generator.assert_not_called()

    @patch('msprof_analyze.advisor.analyzer.schedule.fusion_ops.fusion_ops_analyzer.DBStackFinder')
    def test_query_stack_from_db(self, mock_db_stack_finder):
        self.analyzer._matched_op_index = {'op_rule': [1]}
        event_dataset = MagicMock()
        event_dataset.data_type = Constant.DB
        event_dataset.timeline_file = 'test.db'

        mock_stack_helper = MagicMock()
        mock_db_stack_finder.return_value = mock_stack_helper
        mock_stack_helper.get_api_stack_by_api_index.return_value = {'stack': 'stack'}

        self.analyzer.query_stack(event_dataset)

        mock_db_stack_finder.assert_called_once_with('test.db')
        mock_stack_helper.get_api_stack_by_api_index.assert_called_once_with([1])

    def test__match_ops(self):
        event_dataset = MagicMock()
        ops = 'permute-reshape'
        npu_api = 'torch_npu_api'
        mode = 'aten'

        with patch.object(self.analyzer, '_replace_op_name_prefix') as mock_replace:
            mock_replace.side_effect = ['permute', 'permute', 'reshape', 'reshape', 'permute', 'reshape']
            event_dataset.aten = [MagicMock(name='permute', dataset_index=1), MagicMock(name='reshape')]
            self.analyzer._match_ops(event_dataset, ops, npu_api, mode)

            self.assertEqual(self.analyzer._matched_op_index[npu_api + f':{ops}'], {1})

    def test__match_ops_with_regex(self):
        event_dataset = MagicMock()
        op_rule_pattern = '(-add-)(-mul-)*'
        npu_api = 'torch_npu_api'
        mode = 'aten'
        event_dataset.aten = [MagicMock(name='-add-'), MagicMock(name='-mul-')]

        with patch("builtins.sorted", return_value=[1]):
            self.analyzer._match_ops_with_regex(event_dataset, op_rule_pattern, npu_api, mode)
            self.assertIn(npu_api + f':{op_rule_pattern}', self.analyzer._matched_op_index)

    def test__query_stack_by_matched_index(self):
        index = 1
        event = {'args': {Constant.CALL_STACKS: 'stack'}}
        self.analyzer._matched_op_index = {'op_rule': {1}}

        result = self.analyzer._query_stack_by_matched_index(index, event)

        self.assertEqual(result, {'op_rule': 'stack'})

    def test__replace_op_name_prefix_dequeue(self):
        event_name = 'Dequeue@op_name'
        mode = Constant.DEQUEUE.lower()
        result = self.analyzer._replace_op_name_prefix(event_name, mode)
        self.assertEqual(result, 'op_name')

    def test__replace_op_name_prefix_aten(self):
        event_name = 'aten::op_name'
        mode = Constant.ATEN
        result = self.analyzer._replace_op_name_prefix(event_name, mode)
        self.assertEqual(result, 'op_name')

    def test__replace_op_name_prefix_optimizer(self):
        event_name = 'Optimizer.step#op_name'
        mode = 'optimizer'
        result = self.analyzer._replace_op_name_prefix(event_name, mode)
        self.assertEqual(result, 'op_name')

    def test__format_rule_to_pattern_no_regex(self):
        op_rule = 'permute-reshape'
        pattern, enable_regex = self.analyzer._format_rule_to_pattern(op_rule)
        self.assertEqual(pattern, op_rule)
        self.assertFalse(enable_regex)

    def test__format_rule_to_pattern_with_regex(self):
        op_rule = '(mul){0,1}-(add|neg){0,2}-dropout-(softmax)*'
        pattern, enable_regex = self.analyzer._format_rule_to_pattern(op_rule)
        self.assertTrue(enable_regex)
        self.assertIn('(-mul-){0,1}', pattern)


if __name__ == '__main__':
    unittest.main()
