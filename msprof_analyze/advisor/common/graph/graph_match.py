#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# Copyright (C) 2024-2024. Huawei Technologies Co., Ltd. All rights reserved.
# Licensed under the Apache License, Version 2.0 (the "License");
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

import itertools
from functools import lru_cache
from collections import deque
from typing import Dict, Generator, List, Callable, Hashable, Tuple

import networkx as nx
from msprof_analyze.prof_common.logger import get_logger

logger = get_logger()


class IsomorphismsIterArgsConfig:
    def __init__(self,
                 query_graph: nx.Graph,
                 host_graph: nx.Graph,
                 *args,
                 directed: bool = None,
                 _node_attr_fun: Callable = None,
                 _node_struct_fun: Callable = None,
                 _edge_attr_fun: Callable = None,
                 **kwargs
                 ):
        self.query_graph = query_graph
        self.host_graph = host_graph
        self.directed = directed
        self.node_attr_fun = _node_attr_fun
        self.node_struct_fun = _node_struct_fun
        self.edge_attr_fun = _edge_attr_fun
        self.args = args
        self.kwargs = kwargs


class CandidateArgsConfig:
    def __init__(self,
                 backbone: Dict,
                 query_graph: nx.Graph,
                 host_graph: nx.Graph,
                 next_node: Hashable = None,
                 directed: bool = True,
                 _node_attr_fun: Callable = None,
                 _node_struct_fun: Callable = None,
                 _edge_attr_fun: Callable = None):
        self.backbone = backbone
        self.query_graph = query_graph
        self.host_graph = host_graph
        self.next_node = next_node
        self.directed = directed
        self.node_attr_fun = _node_attr_fun
        self.node_struct_fun = _node_struct_fun
        self.edge_attr_fun = _edge_attr_fun


@lru_cache()
def match_node_attr_fun(query_node: Hashable,
                        host_node: Hashable,
                        query_graph: nx.Graph,
                        host_graph: nx.Graph
                        ) -> bool:
    """
    Check query node matches the attributes in host graph

    :param query_node: Query graph node
    :param host_node: Host graph node
    :param query_graph: Query Graph
    :param host_graph: Host graph
    :return: bool, match or not
    """
    # get node attr
    if query_node not in query_graph.nodes or host_node not in host_graph.nodes:
        return False

    query_node = query_graph.nodes[query_node]
    host_node = host_graph.nodes[host_node]
    for attr, val in query_node.items():
        if attr not in host_node:
            return False
        if isinstance(host_node[attr], str) and isinstance(val, str):
            if host_node[attr].lower() != val.lower():
                return False
        else:
            if host_node[attr] != val:
                return False
    return True


@lru_cache()
def match_node_struct_fun(query_node: Hashable,
                          host_node: Hashable,
                          query_graph: nx.Graph,
                          host_graph: nx.Graph
                          ) -> bool:
    """
    Check query node matches the structure in host graph

    :param query_node: Query graph node
    :param host_node: Host graph node
    :param query_graph: Query Graph
    :param host_graph: Host graph
    :return: bool, match or not
    """
    if query_node not in query_graph.nodes or host_node not in host_graph.nodes:
        return False

    return host_graph.degree(host_node) >= query_graph.degree(query_node)


@lru_cache()
def match_edge_attr_fun(query_edge: Tuple[Hashable, Hashable],
                        host_edge: Tuple[Hashable, Hashable],
                        query_graph: nx.Graph,
                        host_graph: nx.Graph
                        ) -> bool:
    """
    Check query edge matches the attr in host graph

    :param query_edge: Query graph edge
    :param host_edge: Host graph edge
    :param query_graph: Query Graph
    :param host_graph: Host graph
    :return: bool, match or not
    """
    # get edge attr
    if query_edge not in query_graph.edges or host_edge not in host_graph.edges:
        return False

    query_edge = query_graph.edges[query_edge]
    host_edge = host_graph.edges[host_edge]
    for attr, val in query_edge.items():
        if attr not in host_edge:
            return False
        if isinstance(host_edge[attr], str) and isinstance(val, str):
            if host_edge[attr].lower() != val.lower():
                return False
        else:
            if host_edge[attr] != val:
                return False
    return True


def find_isomorphisms(query_graph: nx.Graph,
                      host_graph: nx.Graph,
                      *args,
                      _node_attr_fun: Callable = match_node_attr_fun,
                      _node_struct_fun: Callable = match_node_struct_fun,
                      _edge_attr_fun: Callable = match_edge_attr_fun,
                      limit: int = None,
                      **kwargs) -> List[Dict[Hashable, Hashable]]:
    """
    Find all the sub graphs that are isomorphic to query_graph in host_graph .

    :param query_graph: The graph object to query
    :param host_graph: The graph object to be queried
    :param args: Position args
    :param _node_attr_fun: The function to match node attr
    :param _node_struct_fun: The function to match node structural
    :param _edge_attr_fun: The function to match edge attr
    :param limit: The limitation for the number of returned mappings
    :param kwargs: Keyword args
    :return: Matched node mapping list
    ```
    [{query_id: host_id, ...}, ...]
    ```
    """
    candidates = []
    for query_result in find_isomorphisms_iter(IsomorphismsIterArgsConfig(
            query_graph,
            host_graph,
            *args,
            _node_attr_fun=_node_attr_fun,
            _node_struct_fun=_node_struct_fun,
            _edge_attr_fun=_edge_attr_fun,
            **kwargs
    )):
        candidates.append(query_result)
        if limit and len(candidates) >= limit:
            return candidates
    return candidates


def find_isomorphisms_iter(config: IsomorphismsIterArgsConfig) -> Generator[Dict[Hashable, Hashable], None, None]:
    """
    A generation to find one isomorphic subgraph in host_graph for query_graph.

    :param config: An instance of IsomorphismsIterArgsConfig containing the following attributes:
        - query_graph: The graph object to query
        - host_graph: The graph object to be queried
        - directed: Whether direction should be considered during search
        - node_attr_fun: The function to match node attr
        - node_struct_fun: The function to match node structural
        - edge_attr_fun: The function to match edge attr

    :return: Yield mappings from query node IDs to host graph IDs: {query_id: host_id, ...}
    """
    query_graph: nx.Graph = config.query_graph
    host_graph: nx.Graph = config.host_graph
    directed: bool = config.directed
    _node_attr_fun: Callable = config.node_attr_fun
    _node_struct_fun: Callable = config.node_struct_fun
    _edge_attr_fun: Callable = config.edge_attr_fun

    if directed is None:
        # query graph and host graph should consider directions.
        if isinstance(query_graph, nx.DiGraph) and \
                isinstance(host_graph, nx.DiGraph):
            directed = True
        else:
            directed = False

    # Initialize queue
    dq = deque()
    dq.appendleft({})

    while len(dq) > 0:
        backbone = dq.pop()
        next_candidate_backbones = get_next_candidates(CandidateArgsConfig(
            backbone=backbone,
            query_graph=query_graph,
            host_graph=host_graph,
            directed=directed,
            _node_attr_fun=_node_attr_fun,
            _node_struct_fun=_node_struct_fun,
            _edge_attr_fun=_edge_attr_fun,
        ))
        for candidate in next_candidate_backbones:
            # find a legal isomorphism
            if len(candidate) == len(query_graph):
                yield candidate
            else:
                # continue to search
                dq.appendleft(candidate)


def get_next_candidates(config: CandidateArgsConfig) -> List[Dict[Hashable, Hashable]]:
    """
    Get a list of candidate node assignments for the next "step" of this map.

    :param config: An instance of CandidateArgsConfig containing the following attributes:
        - backbone: Dict, a mapping of query node IDs to one set of host graph node IDs.
        - query_graph: nx.Graph, the query graph whose nodes are being mapped.
        - host_graph: nx.Graph, the host graph where query nodes are being assigned.
        - next_node: Hashable, an optional suggestion for the next node to assign from the query graph.

    :return: List[Dict[Hashable, Hashable]]: A new list of node mappings with one additional element mapped
    """
    backbone: Dict = config.backbone
    query_graph: nx.Graph = config.query_graph
    host_graph: nx.Graph = config.host_graph
    next_node: Hashable = config.next_node
    directed: bool = config.directed
    _node_attr_fun: Callable = config.node_attr_fun
    _node_struct_fun: Callable = config.node_struct_fun
    _edge_attr_fun: Callable = config.edge_attr_fun

    node_priority = {n: 1 for n in query_graph.nodes}
    candidate_nodes = []

    if next_node is None and len(backbone) == 0:
        # Start case
        next_node = max(node_priority.keys(),
                        key=lambda x: node_priority.get(x, 0))

        for node in host_graph.nodes:
            if _node_attr_fun(next_node, node, query_graph, host_graph) and \
                    _node_struct_fun(next_node, node, query_graph, host_graph):
                candidate_nodes.append({next_node: node})
        return candidate_nodes

    nodes_with_maximum_backbone = []
    for query_node_id in query_graph.nodes:
        if query_node_id in backbone:
            continue

        backbone_neighbors = []
        if not directed:
            backbone_neighbors = query_graph.adj[query_node_id]
        else:
            # nx.DiGraph.pred: A <- B: find previous node from B to A
            # nx.DiGraph.adj: A -> B : find next node from A to B
            backbone_neighbors = list(set(query_graph.adj[query_node_id]).union(set(query_graph.pred[query_node_id])))

        query_backbone_node_count = sum([1 for _node in backbone_neighbors if _node in backbone])
        if query_backbone_node_count > 0:
            # Find a longer backbone node
            nodes_with_maximum_backbone.append(query_node_id)

    if not nodes_with_maximum_backbone:
        return []
    # next_node is connected to the current backbone.
    next_node = max(nodes_with_maximum_backbone, key=lambda x: node_priority.get(x, 0))

    # verify all edges between `next_node` and nodes in the backbone are exist in host graph
    # Step1: find all edges between `next_node` and nodes in the backbone
    next_edge_edges = []
    for _node in query_graph.adj[next_node]:
        if _node in backbone:
            # `next_node` -> `_node`
            next_edge_edges.append((None, next_node, _node))

    if directed:
        for _node in query_graph.pred[next_node]:
            if _node in backbone:
                # `_node` -> `next_node`
                next_edge_edges.append((_node, next_node, None))

    if len(next_edge_edges) == 0:
        logger.warning("Find node without any edge, which is invalid.")
        return []
    # Step2: verify candidate nodes that have such edges in the host graph
    candidate_nodes = []
    if len(next_edge_edges) == 1:
        source, _, target = next_edge_edges[0]
        if not directed:
            candidate_nodes = list(host_graph.adj[backbone[target]])
        else:
            if source is not None:
                # means `source` is a `from` edge
                candidate_nodes = list(host_graph.adj[backbone[source]])
            elif target is not None:
                # means `target` is a `from` edge
                candidate_nodes = list(host_graph.pred[backbone[target]])

    elif len(next_edge_edges) > 1:
        candidate_nodes_set = set()
        for (source, _, target) in candidate_nodes:
            if not directed:
                candidate_nodes_from_this_edge = host_graph.adj[backbone[target]]
            else:
                if source is not None:
                    candidate_nodes_from_this_edge = host_graph.adj[backbone[source]]
                else:  # target is not None:
                    candidate_nodes_from_this_edge = host_graph.pred[backbone[target]]

            if len(candidate_nodes_set) > 0:
                candidate_nodes_set = candidate_nodes_set.intersection(candidate_nodes_from_this_edge)
            else:
                # Initialize candidate_nodes_set
                candidate_nodes_set.update(candidate_nodes_from_this_edge)
        candidate_nodes = list(candidate_nodes_set)

    tentative_results = []
    for _node in candidate_nodes:
        if all([_node not in backbone.values(),
                _node_attr_fun(next_node, _node, query_graph, host_graph),
                _node_struct_fun(next_node, _node, query_graph, host_graph)]
               ):
            tentative_results.append({**backbone,
                                      next_node: _node})

    final_candidates = check_edges_mapping(tentative_results,
                                           query_graph=query_graph,
                                           host_graph=host_graph,
                                           _edge_attr_fun=_edge_attr_fun)
    return final_candidates


def check_edges_mapping(candidates: List[Dict[Hashable, Hashable]],
                        query_graph: nx.Graph,
                        host_graph: nx.Graph,
                        _edge_attr_fun: Callable = None
                        ) -> List[Dict[Hashable, Hashable]]:
    """
    Check that all edges between the assigned nodes exist in the host graph.

    :param candidates:  mapping nodes candidates
    :param query_graph: The graph object to query
    :param host_graph: The graph object to be queried
    :param _edge_attr_fun: The function to match edge attr
    :return:
    """
    monomorphism_candidates = []

    for candidate in candidates:
        if len(candidate) != len(query_graph):
            monomorphism_candidates.append(candidate)
            continue

        all_pass_flag = True
        for edge_start, edge_end in query_graph.edges:
            # check edge in host graph
            if not host_graph.has_edge(candidate[edge_start], candidate[edge_end]):
                all_pass_flag = False
                break

            # check edge attr
            if _edge_attr_fun is None or not _edge_attr_fun(
                    (edge_start, edge_end),
                    (candidate[edge_start], candidate[edge_end]),
                    query_graph,
                    host_graph
            ):
                all_pass_flag = False
                break

        if all_pass_flag:
            monomorphism_candidates.append(candidate)

    # Isomorphisms check
    final_candidates = []
    for candidate in monomorphism_candidates:
        all_product = itertools.product(candidate.keys(), candidate.keys())
        for edge_start, edge_end in all_product:
            if not query_graph.has_edge(edge_start, edge_end) and \
                    host_graph.has_edge(candidate[edge_start], candidate[edge_end]):
                break
        else:
            final_candidates.append(candidate)
    return final_candidates
