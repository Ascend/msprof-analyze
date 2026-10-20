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
from unittest.mock import patch

import networkx as nx

from msprof_analyze.advisor.common.graph.graph_match import IsomorphismsIterArgsConfig, CandidateArgsConfig, \
    match_node_attr_fun, match_node_struct_fun, match_edge_attr_fun, find_isomorphisms, check_edges_mapping, \
    get_next_candidates, find_isomorphisms_iter


class TestGraphMatch(unittest.TestCase):
    def setUp(self):
        self.query_graph = nx.Graph()
        self.host_graph = nx.Graph()
        self.query_graph.add_node(1, attr='value1')
        self.host_graph.add_node(10, attr='value1')
        self.query_graph.add_edge(1, 2)
        self.host_graph.add_edge(10, 20)

    def test_isomorphisms_iter_args_config(self):
        config = IsomorphismsIterArgsConfig(self.query_graph, self.host_graph, directed=True)
        self.assertEqual(config.query_graph, self.query_graph)
        self.assertEqual(config.host_graph, self.host_graph)
        self.assertTrue(config.directed)

    def test_candidate_args_config(self):
        backbone = {1: 10}
        config = CandidateArgsConfig(backbone, self.query_graph, self.host_graph)
        self.assertEqual(config.backbone, backbone)
        self.assertEqual(config.query_graph, self.query_graph)
        self.assertEqual(config.host_graph, self.host_graph)

    def test_match_node_attr_fun(self):
        result = match_node_attr_fun(1, 10, self.query_graph, self.host_graph)
        self.assertTrue(result)

    def test_match_node_struct_fun(self):
        result = match_node_struct_fun(1, 10, self.query_graph, self.host_graph)
        self.assertTrue(result)

    def test_match_edge_attr_fun(self):
        query_edge = (1, 2)
        host_edge = (10, 20)
        result = match_edge_attr_fun(query_edge, host_edge, self.query_graph, self.host_graph)
        self.assertTrue(result)

    @patch('msprof_analyze.advisor.common.graph.graph_match.find_isomorphisms_iter')
    def test_find_isomorphisms(self, mock_iter):
        mock_iter.return_value = [{'1': '10'}]
        result = find_isomorphisms(self.query_graph, self.host_graph)
        self.assertEqual(result, [{'1': '10'}])

    def test_check_edges_mapping(self):
        candidates = [{'1': '10'}]
        result = check_edges_mapping(candidates, self.query_graph, self.host_graph)
        self.assertIsInstance(result, list)

    def test_get_next_candidates_initial(self):
        """测试初始状态下获取下一个候选节点"""
        backbone = {}
        config = CandidateArgsConfig(backbone, self.query_graph, self.host_graph,
                                     _node_struct_fun=match_node_struct_fun, _node_attr_fun=match_node_attr_fun,
                                     _edge_attr_fun=match_edge_attr_fun)
        candidates = get_next_candidates(config)

        # 初始状态应该返回单个节点的映射
        self.assertGreater(len(candidates), 0)
        for candidate in candidates:
            self.assertEqual(len(candidate), 1)

    def test_get_next_candidates_directed(self):
        """测试有向图中获取下一个候选节点"""
        # 构建有向图
        query = nx.DiGraph()
        query.add_nodes_from([1, 2, 3], type='node')
        query.add_edges_from([(1, 2), (2, 3)])

        host = nx.DiGraph()
        host.add_nodes_from([10, 20, 30], type='node')
        host.add_edges_from([(10, 20), (20, 30)])

        backbone = {1: 10}
        config = CandidateArgsConfig(backbone, query, host, directed=True, _node_struct_fun=match_node_struct_fun,
                                     _node_attr_fun=match_node_attr_fun, _edge_attr_fun=match_edge_attr_fun)
        candidates = get_next_candidates(config)

        self.assertGreater(len(candidates), 0)
        for candidate in candidates:
            self.assertEqual(len(candidate), 2)
            self.assertTrue(host.has_edge(candidate[1], candidate[2]))  # 验证有向边

    def test_edge_attribute_checking(self):
        """测试边属性检查功能"""
        self.query_graph.add_edge(1, 2, weight=1.0)
        self.host_graph.add_edge(10, 20, weight=1.0)
        self.query_graph.add_node(2, attr='value2')
        self.host_graph.add_node(20, attr='value2')
        candidates = [{1: 10, 2: 20}]
        result = check_edges_mapping(candidates, self.query_graph, self.host_graph, match_edge_attr_fun)
        self.assertEqual(result, candidates)

    def test_find_isomorphisms_iter_directed(self):
        """测试有向图的isomorphism迭代查找"""
        query = nx.DiGraph()
        query.add_nodes_from([1, 2, 3], type='node')
        query.add_edges_from([(1, 2), (2, 3)])

        host = nx.DiGraph()
        host.add_nodes_from([10, 20, 30, 40], type='node')
        host.add_edges_from([(10, 20), (20, 30), (30, 40)])

        config = IsomorphismsIterArgsConfig(query, host, directed=True, _node_struct_fun=match_node_struct_fun,
                                            _node_attr_fun=match_node_attr_fun, _edge_attr_fun=match_edge_attr_fun)
        results = list(find_isomorphisms_iter(config))
        self.assertGreater(len(results), 0)
        for mapping in results:
            self.assertEqual(len(mapping), 3)
            for u, v in query.edges:
                self.assertTrue(host.has_edge(mapping[u], mapping[v]))


if __name__ == '__main__':
    unittest.main()
