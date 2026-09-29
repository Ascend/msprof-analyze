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
from unittest.mock import patch, MagicMock

from msprof_analyze.advisor.common.graph.graph_parser import (
    Tensor, Attr, HostGraphNode, HostGraph, HostGraphParser,
    QueryGraphNode, QueryGraphParser
)
from msprof_analyze.advisor.utils.file import FileOpen
from msprof_analyze.prof_common.file_manager import FileManager


class TestTensor(unittest.TestCase):
    def test_tensor_init(self):
        tensor = Tensor()
        self.assertEqual(tensor.shape, [])
        self.assertEqual(tensor.origin_shape, [])
        self.assertEqual(tensor.shape_range, [])
        self.assertEqual(tensor.origin_shape_range, [])
        self.assertEqual(tensor.dtype, "")
        self.assertEqual(tensor.origin_data_type, "")
        self.assertEqual(tensor.format, "")
        self.assertEqual(tensor.origin_format, [])


class TestAttr(unittest.TestCase):
    def test_attr_init(self):
        attr = Attr()
        self.assertEqual(attr.key, "")
        self.assertEqual(attr.value, [])


class TestHostGraphNode(unittest.TestCase):
    def test_host_graph_node_init(self):
        node = HostGraphNode()
        self.assertEqual(node.graph_name, "")
        self.assertEqual(node.op_name, "")
        self.assertEqual(node.op_type, "")
        self.assertEqual(node.inputs, [])
        self.assertEqual(node.input, [])
        self.assertEqual(node.outputs, [])
        self.assertEqual(node.output, [])
        self.assertEqual(node.strides, [])
        self.assertEqual(node.pads, [])
        self.assertEqual(node.groups, "")
        self.assertEqual(node.dilations, [])
        self.assertEqual(node.kernelname, "")
        self.assertEqual(node._attrs, [])

    def test_host_graph_node_repr(self):
        node = HostGraphNode()
        node.op_name = "test_node"
        self.assertEqual(repr(node), "<node test_node>")


class TestHostGraph(unittest.TestCase):
    def test_host_graph_init(self):
        graph = HostGraph()
        self.assertEqual(graph.name, "")
        self.assertEqual(graph.nodes, {})
        self.assertEqual(graph.inputs, [])
        self.assertEqual(graph.edges, [])
        self.assertEqual(graph.model_name, None)
        self.assertEqual(graph.file_path, None)

    def test_host_graph_build(self):
        graph = HostGraph()
        node1 = HostGraphNode()
        node1.op_name = "node1"
        node1.inputs = ["node2"]
        node2 = HostGraphNode()
        node2.op_name = "node2"
        graph.nodes = {"node1": node1, "node2": node2}
        graph.build()
        self.assertEqual(node2.outputs, ["node1"])


class TestHostGraphParser(unittest.TestCase):
    def test_get_key_value(self):
        line = "key: \"value\""
        key, value = HostGraphParser._get_key_value(line)
        self.assertEqual(key, "key")
        self.assertEqual(value, "value")

    def test_parse_attr(self):
        """测试_parse_attr方法处理不同属性"""
        node = HostGraphNode()
        HostGraphParser._parse_attr("name", "test_node", node)
        self.assertEqual(node.op_name, "test_node")

        HostGraphParser._parse_attr("type", "Conv2D", node)
        self.assertEqual(node.op_type, "Conv2D")

        HostGraphParser._parse_attr("input", "input1", node)
        self.assertEqual(node.inputs, ["input1"])

        tensor = Tensor()
        HostGraphParser._parse_attr("dim", "4", tensor)
        self.assertEqual(tensor.shape, ["4"])

        HostGraphParser._parse_attr("dtype", "float32", tensor)
        self.assertEqual(tensor.dtype, "float32")

        attr_list = []
        HostGraphParser._parse_attr("item", "value", attr_list)
        self.assertEqual(attr_list, ["value"])
        HostGraphParser._parse_attr("nonexistent_attr", "value", node)

    @patch.object(HostGraphParser, '_parse_line')
    def test_parse(self, mock_parse_line):
        mock_file = MagicMock()
        with patch.object(FileOpen, '__enter__', return_value=MagicMock(file_reader=mock_file)):
            mock_parse_line.return_value = [HostGraph()]
            parser = HostGraphParser("test_file.txt")
            self.assertEqual(len(parser.graphs), 0)

    @patch.object(HostGraphParser, '_parse_line')
    def test_parse_struct(self, mock_parse_line):
        in_file = MagicMock()
        in_obj = HostGraph()

        mock_file = MagicMock()
        with patch.object(FileOpen, '__enter__', return_value=MagicMock(file_reader=mock_file)):
            mock_parse_line.side_effect = [[HostGraph()], HostGraphNode()]
            parser = HostGraphParser("test_file.txt")
            # 测试解析 op
            parser._parse_struct(in_file, 'op', in_obj)

    @patch.object(HostGraphParser, '_parse_line')
    def test_read_line(self, mock_parse_line):
        file = MagicMock()
        file.readline.return_value = 'test_line\n'

        mock_file = MagicMock()
        with patch.object(FileOpen, '__enter__', return_value=MagicMock(file_reader=mock_file)):
            mock_parse_line.return_value = [HostGraph()]
            parser = HostGraphParser("test_file.txt")
            result = parser._read_line(file)
            self.assertEqual(result, 'test_line')
            self.assertEqual(parser.line_no, 1)

    def test_get_edges_list(self):
        """测试_get_edges_list方法"""
        parser = HostGraphParser.__new__(HostGraphParser)
        parser.edges = []
        parser.graphs = []
        parser._get_edges_list()
        self.assertEqual(parser.edges, [])

        # 创建节点和图
        node1 = HostGraphNode()
        node1.op_name = "node1"
        node1.inputs = ["node2"]
        node1.outputs = ["node3"]
        node2 = HostGraphNode()
        node2.op_name = "node2"
        node3 = HostGraphNode()
        node3.op_name = "node3"

        parser.nodes = {"node1": node1, "node2": node2, "node3": node3}
        parser.graphs = [HostGraph()]  # 非空图列表
        parser._get_edges_list()
        self.assertEqual(len(parser.edges), 2)
        edge_nodes = [(e[0].op_name, e[1].op_name) for e in parser.edges]
        self.assertIn(("node2", "node1"), edge_nodes)
        self.assertIn(("node1", "node3"), edge_nodes)


class TestQueryGraphNode(unittest.TestCase):
    def test_query_graph_node_init(self):
        node = QueryGraphNode("test_op", "test_pass")
        self.assertEqual(node.op_type, "test_op")
        self.assertEqual(node.op_pass, "test_pass")

    def test_query_graph_node_trim_string(self):
        string = "abcdefg"
        trimmed = QueryGraphNode.trim_string(string, 3)
        self.assertEqual(trimmed, "abc")

    def test_query_graph_node_get_property(self):
        node = QueryGraphNode("test_op", "test_pass")
        self.assertEqual(node.get_property("op_type"), "test_op")


class TestQueryGraphParser(unittest.TestCase):
    @patch.object(FileManager, 'read_yaml_file')
    @patch.object(QueryGraphParser, 'parse_yaml')
    def test_query_graph_parser_init(self, mock_parse_yaml, mock_read_yaml):
        mock_read_yaml.return_value = {}
        with patch("os.path.exists", return_value=True):
            parser = QueryGraphParser("test_rule.yaml")
            self.assertEqual(parser.num_rules, 0)

    def test_build_query_graph_v0(self):
        graph_struct = ["op1", "op2"]
        graphs = QueryGraphParser.build_query_graph_v0("test_graph", graph_struct)
        self.assertEqual(len(graphs), 1)

    def test_build_query_graph_v1(self):
        nodes_list = [{"node1": "op1"}, {"node2": "op2"}]
        edges_list = [["node1", "node2"]]
        graphs = QueryGraphParser.build_query_graph_v1("test_graph", nodes_list, edges_list)
        self.assertEqual(len(graphs), 1)

    def test_parse_yaml(self):
        """测试parse_yaml方法"""
        parser = QueryGraphParser.__new__(QueryGraphParser)
        parser._fusion_rules = {}
        yaml_data = {
            "GraphFusion": [
                {"rule1": {"version": 0, "struct": ["op1", "op2"]}}
            ],
            "UBFusion": [
                {"rule2": {"version": 1, "nodes": [{"n1": "op1"}, {"n2": "op2"}], "edges": [["n1", "n2"]]}}
            ]
        }
        parser.parse_yaml(yaml_data)
        self.assertIn("rule1", parser._fusion_rules)
        self.assertIn("rule2", parser._fusion_rules)


if __name__ == '__main__':
    unittest.main()
