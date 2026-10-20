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

import logging
import unittest
from io import StringIO
from unittest import mock

from msprof_analyze.advisor.analyzer.graph_fusion.graph_fusion_checker import GraphFusionRules


class TestGraphFusionChecker(unittest.TestCase):
    def setUp(self):
        logging.basicConfig(level=logging.INFO)
        self.logger = logging.getLogger()
        self.logger.addHandler(logging.StreamHandler(StringIO()))

        self.fusion_rules = "test_fusion_rules"
        self.graph_fusion_rules = GraphFusionRules(self.fusion_rules)

    def tearDown(self):
        self.logger.handlers.clear()

    def test_get_attr_shape(self):
        """测试静态方法get_attr_shape"""

        class MockAttr:
            def __init__(self, shape):
                self.shape = shape

        class MockNode:
            def __init__(self, attrs):
                self.input = attrs

        attrs = [MockAttr(["2", "4", "6"]), MockAttr(["8", "10"])]
        node = MockNode(attrs)
        result = GraphFusionRules.get_attr_shape(node, "input", "shape")
        self.assertEqual(result, "2,4,6;8,10")

        node = MockNode([])
        result = GraphFusionRules.get_attr_shape(node, "input", "shape")
        self.assertEqual(result, "")

        node = MockNode(attrs)
        result = GraphFusionRules.get_attr_shape(node, "nonexistent", "shape")
        self.assertEqual(result, "")

    def test_get_attr_type(self):
        """测试静态方法get_attr_type"""

        class MockAttr:
            def __init__(self, dtype):
                self.dtype = dtype

        class MockNode:
            def __init__(self, attrs):
                self.output = attrs

        attrs = [MockAttr("float32"), MockAttr("int64")]
        node = MockNode(attrs)
        result = GraphFusionRules.get_attr_type(node, "output", "dtype")
        self.assertEqual(result, "float32;int64")

        node = MockNode([])
        result = GraphFusionRules.get_attr_type(node, "output", "dtype")
        self.assertEqual(result, "")

        node = MockNode(attrs)
        result = GraphFusionRules.get_attr_type(node, "nonexistent", "dtype")
        self.assertEqual(result, "")

    @mock.patch('msprof_analyze.advisor.analyzer.graph_fusion.graph_fusion_checker.QueryGraphParser')
    @mock.patch('msprof_analyze.advisor.analyzer.graph_fusion.graph_fusion_checker.find_isomorphisms')
    @mock.patch('msprof_analyze.advisor.analyzer.graph_fusion.graph_fusion_checker.GraphFusionRules.build_query_graph')
    def test_find_fusion_matched_issues(self, mock_build_query_graph, mock_find_isomorphisms, mock_query_graph_parser):
        """测试find_fusion_matched_issues方法"""
        mock_query_graph = mock.MagicMock()
        mock_query_graph_parser.return_value = mock_query_graph
        mock_query_graph.num_rules = 2

        mock_graph1 = mock.MagicMock()
        mock_graph2 = mock.MagicMock()
        mock_build_query_graph.return_value = [mock_graph1, mock_graph2]

        mock_find_isomorphisms.side_effect = [
            [{"node1": "match1"}],  # 第一个图的匹配结果
            []  # 第二个图无匹配
        ]

        mock_graph_dataset = mock.MagicMock()
        mock_graph_dataset.graphs = [mock.MagicMock()]
        mock_graph_dataset.graphs[0].graph = "target_graph"

        self.graph_fusion_rules.find_fusion_matched_issues([mock_graph_dataset])
        self.assertEqual(len(self.graph_fusion_rules.candidates), 1)
        self.assertEqual(self.graph_fusion_rules.candidates[0], [{"node1": "match1"}])
        mock_query_graph_parser.assert_called_once_with(self.fusion_rules)
        mock_find_isomorphisms.assert_any_call(mock_graph1.graph, "target_graph")
        mock_find_isomorphisms.assert_any_call(mock_graph2.graph, "target_graph")

    @mock.patch(
        'msprof_analyze.advisor.analyzer.graph_fusion.graph_fusion_checker.GraphFusionRules.find_fusion_matched_issues')
    def test_find_fusion_matched_issues_with_times_from_summary(self, mock_find_matched):
        """测试从op_summary获取时间信息"""
        mock_find_matched.return_value = None
        self.graph_fusion_rules.candidates = [
            [
                {"node1": mock.MagicMock(op_name="op1", op_type="Add"),
                 "node2": mock.MagicMock(op_name="op2", op_type="Mul")}
            ]
        ]

        class MockOp:
            def __init__(self, op_type, task_duration):
                self.op_type = op_type
                self.task_duration = task_duration

        mock_op_summary = mock.MagicMock()
        mock_op_summary.task_dict = {
            "op1": [MockOp("Add", "1.5")],
            "op2": [MockOp("Mul", "2.5")]
        }

        mock_profiling = [mock.MagicMock(op_summary=mock_op_summary)]
        self.graph_fusion_rules.find_fusion_matched_issues_with_times([mock.MagicMock()], mock_profiling)

        self.assertEqual(len(self.graph_fusion_rules.task_duration_list), 1)
        self.assertEqual(self.graph_fusion_rules.task_duration_list[0][0], [1.5, 2.5])

    @mock.patch(
        'msprof_analyze.advisor.analyzer.graph_fusion.graph_fusion_checker.GraphFusionRules.find_fusion_matched_issues')
    def test_find_fusion_matched_issues_with_times_from_msprof(self, mock_find_matched):
        """测试从msprof获取时间信息"""
        mock_find_matched.return_value = None
        self.graph_fusion_rules.candidates = [
            [
                {"node1": mock.MagicMock(op_name="op1"),
                 "node2": mock.MagicMock(op_name="op2")}
            ]
        ]

        mock_task1 = mock.MagicMock()
        mock_task1.args = {"item_id": "op1"}
        mock_task1.dur = "3.0"

        mock_task2 = mock.MagicMock()
        mock_task2.args = {"item_id": "op2"}
        mock_task2.dur = "4.0"

        mock_msprof = mock.MagicMock()
        mock_msprof.tasks = [mock_task1, mock_task2]
        mock_profiling = [mock.MagicMock(op_summary=None, msprof=mock_msprof)]

        self.graph_fusion_rules.find_fusion_matched_issues_with_times([mock.MagicMock()], mock_profiling)
        self.assertEqual(len(self.graph_fusion_rules.task_duration_list), 1)
        self.assertEqual(self.graph_fusion_rules.task_duration_list[0][0], [3.0, 4.0])

    def test_match_time_from_summary_missing_op(self):
        """测试从summary匹配时间 - 操作符缺失"""
        self.graph_fusion_rules.candidates = [
            [
                {"node1": mock.MagicMock(op_name="missing_op", op_type="Add")}
            ]
        ]

        mock_op_summary = mock.MagicMock()
        mock_op_summary.task_dict = {}

        with mock.patch('msprof_analyze.advisor.analyzer.graph_fusion.graph_fusion_checker.logger') as mock_logger:
            self.graph_fusion_rules.match_time_from_summary(mock_op_summary)
            mock_logger.warning.assert_called_once()

        self.assertEqual(len(self.graph_fusion_rules.task_duration_list), 1)
        self.assertEqual(self.graph_fusion_rules.task_duration_list[0][0], [0.0])

    def test_make_render_empty_candidates(self):
        """测试make_render方法 - 无候选结果"""
        self.graph_fusion_rules.candidates = []
        mock_html_render = mock.MagicMock()

        self.graph_fusion_rules.make_render(mock_html_render)
        mock_html_render.render_template.assert_not_called()

    def test_make_render_with_candidates(self):
        """测试make_render方法 - 有候选结果"""
        self.graph_fusion_rules.candidates = [
            [
                {mock.MagicMock(op_pass="test_pass", op_type="Add"):
                     mock.MagicMock(op_name="op1", op_type="Add")}
            ]
        ]
        self.graph_fusion_rules.task_duration_list = [[[1.0]]]
        mock_html_render = mock.MagicMock()
        self.graph_fusion_rules.make_render(mock_html_render)

        mock_html_render.render_template.assert_called_once()
        args, kwargs = mock_html_render.render_template.call_args
        self.assertEqual(kwargs['key'], "computation")
        self.assertEqual(kwargs['template_name'], "fusion.html")

    def test_make_record_empty_candidates(self):
        """测试make_record方法 - 无候选结果"""
        self.graph_fusion_rules.candidates = []
        mock_result = mock.MagicMock()

        self.graph_fusion_rules.make_record(mock_result)
        mock_result.add.assert_not_called()

    @mock.patch('msprof_analyze.advisor.analyzer.graph_fusion.graph_fusion_checker.BasePrompt')
    def test_make_record_with_candidates(self, mock_base_prompt):
        """测试make_record方法 - 有候选结果"""
        mock_prompt_class = mock.MagicMock()
        mock_prompt_class.PROBLEM = "test_problem"
        mock_prompt_class.DESCRIPTION = "test_description {}"
        mock_prompt_class.SUGGESTION = "test_suggestion"
        mock_base_prompt.get_prompt_class.return_value = mock_prompt_class

        self.graph_fusion_rules.candidates = [
            [
                {mock.MagicMock(op_pass="test_pass", op_type="Add"):
                     mock.MagicMock(graph_name="graph1", op_name="op1", op_type="Add")}
            ]
        ]
        self.graph_fusion_rules.task_duration_list = [[[1.0]]]
        mock_result = mock.MagicMock()

        with mock.patch.object(GraphFusionRules, 'get_attr_shape', return_value="shape1") as mock_get_shape, \
                mock.patch.object(GraphFusionRules, 'get_attr_type', return_value="type1") as mock_get_type:
            self.graph_fusion_rules.make_record(mock_result)

            mock_result.add.assert_called_once()
            mock_result.add_detail.assert_any_call('fusion issues', headers=mock.ANY)
            mock_result.add_detail.assert_any_call('fusion issues', detail=mock.ANY)

            self.assertEqual(mock_get_shape.call_count, 2)  # 输入和输出各一次
            self.assertEqual(mock_get_type.call_count, 4)  # 输入format/dtype和输出format/dtype各一次


if __name__ == '__main__':
    unittest.main()
