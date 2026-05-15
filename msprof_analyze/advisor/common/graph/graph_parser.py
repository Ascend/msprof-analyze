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

import os
from msprof_analyze.prof_common.logger import get_logger
import itertools
from collections import deque
from dataclasses import dataclass
from typing import List, Tuple, Dict

from msprof_analyze.prof_common.file_manager import FileManager
from msprof_analyze.advisor.utils.file import FileOpen

logger = get_logger()


@dataclass
class Tensor:
    def __init__(self):
        super().__init__()
        self.shape = []
        self.origin_shape = []
        self.shape_range = []
        self.origin_shape_range = []
        self.dtype = ""
        self.origin_data_type = ""
        self.format = ""
        self.origin_format = []


@dataclass
class Attr:

    def __init__(self):
        super().__init__()
        self.key = str()
        self.value = []


class HostGraphNode:
    def __init__(self):
        super().__init__()
        self.graph_name = str()
        self.op_name = str()
        self.op_type = str()
        self.inputs = []
        self.input = []
        self.outputs = []
        self.output = []
        self.strides = []
        self.pads = []
        self.groups = ""
        self.dilations = []
        self.kernelname = ""
        self._attrs = []

    def __repr__(self):
        return f"<node {self.op_name}>"


@dataclass
class HostGraph:
    def __init__(self):
        super().__init__()
        self.name = ""
        self.nodes = {}
        self.inputs = []
        self.edges = []
        self.model_name = None
        self.file_path = None

    def build(self):
        """build a graph"""
        for name, node in self.nodes.items():
            for input_node in node.inputs:
                if input_node not in self.nodes:
                    continue
                self.nodes[input_node].outputs.append(name)


class HostGraphParser:
    """
    Parse graph metadata from text file
    """
    def __init__(self, file_path):
        self.buffer = deque(maxlen=100)
        self.line_no = 0
        self._file_path = file_path
        self.edges: List[Tuple[HostGraphNode, HostGraphNode]] = []
        self.nodes: Dict[str, HostGraphNode] = {}
        self.graphs = self._parse(self._file_path)
        self._get_node_dict()
        self._get_edges_list()
        del self.graphs[0]

    @staticmethod
    def _get_key_value(line):
        res = line.split(':', 1)
        return res[0].strip(), res[1].strip().strip('"')

    @staticmethod
    def _parse_attr(key, value, obj):
        if not isinstance(obj, list) and not obj:
            return
        if key == "dim" and hasattr(obj, "shape"):
            obj.shape.append(value)
        elif key == "name" and hasattr(obj, "op_name"):
            obj.op_name = value
        elif key == "name" and hasattr(obj, "name"):
            obj.name = value
        elif key == "dtype" and hasattr(obj, "dtype"):
            obj.dtype = value
        elif key == "layout" and hasattr(obj, "format"):
            obj.format = value
        elif key == "type" and hasattr(obj, "op_type"):
            obj.op_type = value
        elif key == "input" and hasattr(obj, "input"):
            obj.inputs.append(value.strip('"').split(':')[0])
        elif key == "key" and hasattr(obj, "key"):
            obj.key = value
        elif hasattr(obj, key):
            setattr(obj, key, value)
        elif isinstance(obj, list) and key != "val_type":
            obj.append(value)

    def _parse_struct(self, in_file, key, in_obj):

        def parse_shape(file, obj):
            obj = self._parse_line(file, obj)

        def parse_input_desc(file, obj):
            tensor = self._parse_line(file, Tensor())
            if obj and hasattr(obj, "input"):
                obj.input.append(tensor)

        def parse_out_desc(file, obj):
            tensor = self._parse_line(file, Tensor())
            if obj and hasattr(obj, "output"):
                obj.output.append(tensor)

        def parse_op(file, obj: HostGraph):
            node = self._parse_line(file, HostGraphNode())
            if hasattr(obj, "name"):
                node.graph_name = obj.name
            if obj and hasattr(obj, "nodes") and node.op_name:
                obj.nodes[node.op_name] = node

        def parse_graph(file, obj):
            graph = self._parse_line(file, HostGraph())
            obj.append(graph)

        def parse_attr(file, obj):
            attr = self._parse_line(file, Attr())
            if hasattr(obj, attr.key):
                if attr.key not in ['format']:
                    setattr(obj, attr.key, attr.value)
            elif attr.key.endswith("_kernelname"):
                setattr(obj, "kernelname", attr.value)
            if obj and hasattr(obj, "get_attrs"):
                obj.get_attrs().append(attr)

        def parse_list(file, obj):
            value = []
            self._parse_line(file, value)
            if isinstance(obj, list):
                obj.append(value)
            else:
                obj = value

        def parse_value(file, obj):
            if hasattr(obj, "value"):
                obj.value = self._parse_line(file, obj.value)

        def parse_default(file, _obj=None):
            """function with unused argument"""
            self._parse_line(file, None)

        parse_methods = {
            "shape": parse_shape,
            "input_desc": parse_input_desc,
            "output_desc": parse_out_desc,
            "op": parse_op,
            "graph": parse_graph,
            "attr": parse_attr,
            "list_list_int": parse_list,
            "list_list_i": parse_list,
            "list": parse_list,
            "value": parse_value,
        }
        parse_methods.get(key, parse_default)(in_file, in_obj)

    def _read_line(self, file):
        self.line_no += 1
        line = file.readline()
        if line.strip().endswith('}'):
            end_line = ""
            while self.buffer and not end_line.strip().endswith("{"):
                end_line = self.buffer.pop()
        else:
            self.buffer.append(line)
        return line.strip()

    def _parse_line(self, file, obj=None):
        line = self._read_line(file)
        try:
            while line and not line.endswith("}"):
                if line.endswith('{'):
                    key = line.rstrip('{').strip()
                    self._parse_struct(file, key, obj)
                else:
                    key, value = self._get_key_value(line)
                    self._parse_attr(key, value, obj)
                line = self._read_line(file)
        except Exception as exception:
            if self.buffer:
                logger.debug("***********************graph content**************************")
                while self.buffer:
                    line = self.buffer.popleft()
                    logger.debug(line)
                logger.debug("***********************graph content**************************")
            raise exception
        return obj

    def _parse(self, graph_file):
        # pylint:disable=broad-except
        graph_list = []
        with FileOpen(graph_file, "r") as file:
            try:
                graph_list = self._parse_line(file.file_reader, graph_list)
            except Exception:
                logger.error(
                    "Parse line %s of file %s failed, make sure the format is correct.", self.line_no, graph_file
                )
        graphs = []
        for graph in graph_list:
            if isinstance(graph, HostGraph):
                graphs.append(graph)
        for graph in graphs:
            graph.model_name = graphs[0].name
            graph.file_path = self._file_path
            graph.build()
        return graphs

    def _get_edges_list(self) -> None:
        if len(self.graphs) <= 0:
            return

        def is_repeat_edge(edge, edge_collector):
            for _edge in edge_collector:
                if edge[0].op_name == _edge[0].op_name and edge[1].op_name == _edge[1].op_name:
                    return True
            return False

        for node in self.nodes.values():
            for input_node_name in node.inputs:
                if input_node_name not in self.nodes:
                    continue
                input_node = self.nodes[input_node_name]
                if not is_repeat_edge((input_node, node), self.edges):
                    self.edges.append((input_node, node))
            for output_node_name in node.outputs:
                if output_node_name not in self.nodes:
                    continue
                output_node = self.nodes[output_node_name]
                if not is_repeat_edge((node, output_node), self.edges):
                    self.edges.append((node, output_node))

    def _get_node_dict(self) -> None:
        if not self.graphs:
            self.nodes = {}
            return
        self.nodes = {
            node.op_name: node
            for graph in self.graphs
            for node in graph.nodes.values()
        }


class QueryGraphNode:
    """
    Graph Node
    """
    _ID = 0

    def __init__(self, op_type: str, op_pass: str):
        self._op_type = op_type
        self._id = QueryGraphNode._ID
        self._op_pass = op_pass
        QueryGraphNode._ID += 1

    def __eq__(self, other):
        return self._op_type == other._op_type and \
               self._id == other._id

    def __hash__(self):
        return hash(self._op_type + str(self._id))

    @property
    def op_type(self):
        return self._op_type

    @property
    def op_name(self):
        return self._op_type + "_id_" + str(self._id)

    @property
    def op_pass(self):
        return self._op_pass

    @op_type.setter
    def op_type(self, op_type):
        self._op_type = op_type

    @staticmethod
    def trim_string(string: str, length: int = -1):
        """

        Trim string to target length
        :param string: Original string
        :param length: Target length of string, -1 indicates original string.
        :return: Trimmed string
        """
        if string is None or not isinstance(string, str):
            raise TypeError(f"Param string must be a string type but got {type(string)}.")

        if length <= -1 or len(string) <= length:
            return string

        return string[:length]

    def get_property(self, name):
        """
        get property
        """
        return getattr(self, name, lambda: None)


class QueryGraphParser:
    def __init__(self, rule_database_path: str):
        self._fusion_rules: Dict[str, List[Tuple]] = dict()
        self.load_database(rule_database_path)
        self.num_rules = sum([len(v) for v in self._fusion_rules.values()])

    @property
    def fusion_rules(self):
        return self._fusion_rules

    @staticmethod
    def build_query_graph_v0(graph_name: str, graph_struct: List[str]) -> List[Tuple]:
        nodes = dict()
        graphs = []
        edges = []

        pre_node, next_node = None, None
        for node in graph_struct:
            pre_node = next_node
            next_node = QueryGraphNode(node, graph_name)
            nodes[next_node.op_name] = next_node
            if pre_node is None or next_node is None:
                continue
            edges.append((pre_node, next_node,))
        graphs.append((nodes, edges, graph_name,))
        return graphs

    @staticmethod
    def build_query_graph_v1(graph_name: str,
                             nodes_list: List[Dict],
                             edges_list: List[List[str]]) -> List[Tuple]:
        graphs = []
        node_index = dict()
        multi_node_list = []
        for index, node in enumerate(nodes_list):
            (node_name, op_type), = node.items()
            if isinstance(op_type, str):
                op_type = [op_type]
            multi_node_list.append([QueryGraphNode(op, graph_name) for op in op_type])
            node_index[node_name] = index

        multi_node = list(itertools.product(*multi_node_list))

        for index, sub_nodes in enumerate(multi_node):
            sub_graph_name = graph_name if index == 0 else f"{graph_name}#{index}"
            sub_edge = []
            sub_node = dict()
            for node in sub_nodes:
                sub_node[node.op_name] = node
            for edge in edges_list:
                pre_node, next_node = edge
                pre_node_index, next_node_index = node_index.get(pre_node), node_index.get(next_node)
                sub_edge.append((sub_nodes[pre_node_index], sub_nodes[next_node_index]))
            sub_graph = (sub_node, sub_edge, sub_graph_name,)
            graphs.append(sub_graph)
        return graphs

    def load_database(self, rule_database):
        if not os.path.isabs(rule_database):
            rule_database = os.path.join(os.path.dirname(__file__),
                                         "../", "../",
                                         rule_database)

        if not os.path.exists(rule_database):
            raise FileNotFoundError(f"Path {rule_database} does not exist.")

        database = FileManager.read_yaml_file(rule_database)
        self.parse_yaml(database)

    def parse_yaml(self, yaml_database):
        fusion_strategy_list = yaml_database.get("GraphFusion", [])
        if yaml_database.get("UBFusion", []):
            fusion_strategy_list.extend(yaml_database.get("UBFusion", []))
        for fusion_strategy in fusion_strategy_list:
            if not isinstance(fusion_strategy, dict):
                continue
            (fusion_name, strategy), = fusion_strategy.items()
            version = strategy.get("version", 0)
            if version == 0 or version == "0":
                self._fusion_rules[fusion_name] = self.build_query_graph_v0(fusion_name,
                                                                            strategy.get('struct', []))
            elif version == 1 or version == "1":
                self._fusion_rules[fusion_name] = self.build_query_graph_v1(fusion_name,
                                                                            strategy.get('nodes', []),
                                                                            strategy.get('edges', []))
