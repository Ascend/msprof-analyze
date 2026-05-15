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

from msprof_analyze.prof_common.logger import get_logger
from typing import Dict, List, Tuple, Callable, Any, Optional, Union

import networkx as nx

from msprof_analyze.advisor.common.graph.graph_parser import HostGraphNode, QueryGraphNode

logger = get_logger()


class Graph:
    """
    Graph Struct
    """

    # pylint: disable=too-many-instance-attributes
    def __init__(self,
                 nodes: Dict[str, Optional[Union[HostGraphNode, QueryGraphNode]]] = None,
                 edges: List[Tuple[Optional[Union[HostGraphNode, QueryGraphNode]],
                                   Optional[Union[HostGraphNode, QueryGraphNode]]]] = None,
                 name: str = None):
        self.name = name
        self.graph = nx.DiGraph(name=name)
        self.nodes = nodes if nodes is not None else {}
        self.edges = edges if edges is not None else list()

    def build(self):
        for _, node in self.nodes.items():
            # add node and mark op_name as tag
            self.add_node(node,
                          op_type=node.op_type
                          )
        for edge in self.edges:
            self.add_edge(*edge)
        return self.graph

    def get_size(self) -> Dict[str, int]:
        if not hasattr(self.graph, "nodes"):
            return {"edges": 0, "nodes": 0}

        return {"edges": len(self.graph.edges),
                "nodes": len(self.graph.nodes)}

    def add_node(self, node: HostGraphNode, **kwargs):
        if node is None:
            return
        self.graph.add_node(node, **kwargs)

    def add_edge(self, pre_node: HostGraphNode, next_node: HostGraphNode):
        if pre_node is None or next_node is None:
            return

        if pre_node not in self.graph or \
                next_node not in self.graph:
            logger.error("Nodes between edge should be both exists.")
            return

        self.graph.add_edge(pre_node, next_node)

    def add_node_with_edge(self, node, adj_nodes: List[HostGraphNode]):
        self.add_node(node)
        for adj in adj_nodes:
            self.add_edge(node, adj)

    def remove_node(self, node: HostGraphNode = None) -> None:
        if node is None:
            return

        self.graph.remove_node(node)

    def remove_edge(self, pre_node: HostGraphNode = None, next_node: HostGraphNode = None) -> None:
        if pre_node is None or next_node is None:
            raise ValueError(f"Invalid edge from {pre_node} to {pre_node}.")

        self.graph.remove_edge(pre_node, next_node)

    def get_subgraph(self, nodes: List[HostGraphNode]) -> nx.DiGraph:
        nodes = list(set(nodes))
        for node in nodes:
            if not self.is_node_exists(node):
                raise ValueError(f"Failed to subtract subgraph because {node.op_name} is not in the graph.")

        return self.graph.subgraph(nodes)

    def highlight_subgraph(self, subgraph: nx.DiGraph = None) -> None:
        pass

    def get_node(self, node: HostGraphNode):
        return self.graph[node] if node in self.graph else None

    def get_node_by_name(self, node_name: str):
        return self.nodes.get(node_name, None)

    def is_node_exists(self, node: HostGraphNode):
        return node in self.graph
