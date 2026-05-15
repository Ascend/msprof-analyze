# Copyright (c) 2024, Huawei Technologies Co., Ltd.
# All rights reserved.
#
# Licensed under the Apache License, Version 2.0  (the "License");
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
from typing import List

from tqdm import tqdm

from msprof_analyze.advisor.display.prompt.base_prompt import BasePrompt
from msprof_analyze.advisor.result.result import OptimizeResult
from msprof_analyze.advisor.result.item import OptimizeItem, OptimizeRecord, StatisticsItem
from msprof_analyze.advisor.common.graph.graph import Graph
from msprof_analyze.advisor.common.graph.graph_parser import QueryGraphParser
from msprof_analyze.advisor.dataset.graph_dataset import GraphDataset
from msprof_analyze.advisor.common.graph.graph_match import find_isomorphisms

logger = get_logger()


class GraphFusionRules:
    def __init__(self, fusion_rules: str):
        self.fusion_rules = fusion_rules
        self.candidates = []
        self.task_duration_list = []

    @staticmethod
    def build_query_graph(query_graphs) -> List[Graph]:
        for _, query_graph in query_graphs.fusion_rules.items():
            for sub_graph in query_graph:
                graph = Graph(*sub_graph)
                graph.build()
                yield graph

    @staticmethod
    def get_attr_shape(node, type_name: str, attr_name: str) -> str:
        attr_shape = []
        node_attrs = getattr(node, type_name, [])
        for attrs in node_attrs:
            attr = getattr(attrs, attr_name, [])
            attr_shape.append(",".join(attr))
        return ";".join(attr_shape)

    @staticmethod
    def get_attr_type(node, type_name: str, attr_name: str) -> str:
        attr_type = []
        node_attrs = getattr(node, type_name, [])
        for attr in node_attrs:
            attr_type.append(getattr(attr, attr_name, ""))
        return ";".join(attr_type)

    def find_fusion_matched_issues(self, graphs: List[GraphDataset]):
        query_graphs = QueryGraphParser(self.fusion_rules)
        with tqdm(total=query_graphs.num_rules, leave=False, ncols=100, unit=" rules") as pbar:
            pbar.set_description(f"Searching Isomorphic Subgraph")
            for query_graph in self.build_query_graph(query_graphs):
                query_candidates = find_isomorphisms(query_graph.graph, graphs[0].graphs[-1].graph)
                pbar.update(1)
                if len(query_candidates) > 0:
                    self.candidates.append(query_candidates)

    def find_fusion_matched_issues_with_times(self, graphs: List[GraphDataset], profiling):
        self.find_fusion_matched_issues(graphs)
        if len(self.candidates) == 0 or len(profiling) == 0:
            return

        if not hasattr(profiling[0], 'op_summary') or profiling[0].op_summary is None:
            if hasattr(profiling[0], 'msprof'):
                self.match_time_from_msprof(profiling[0].msprof)
                return
            else:
                logger.warning("Skip analyze operator because of not containing op summary.")
                return

        self.match_time_from_summary(profiling[0].op_summary)
        time_duration_sum = []
        for task_duration in self.task_duration_list:
            time_duration_sum.append(sum([sum(duration) for duration in task_duration]))
        time_duration_index = sorted(range(len(time_duration_sum)),
                                     key=time_duration_sum.__getitem__,
                                     reverse=True)
        self.task_duration_list = [self.task_duration_list[i] for i in time_duration_index]
        self.candidates = [self.candidates[i] for i in time_duration_index]

    def match_time_from_summary(self, op_summary):
        op_dict = op_summary.task_dict
        for candidates in self.candidates:
            candidate_duration = []
            for candidate in candidates:
                duration_list = []
                for node in candidate.values():
                    if node.op_name not in op_dict or op_dict[node.op_name][0].op_type.lower() != node.op_type.lower():
                        logger.warning("Operator %s is missing in op summary, which will be set to 0.", node.op_name)
                        duration_list.append(0.0)
                        continue
                    duration_list.append(float(op_dict[node.op_name][0].task_duration))
                candidate_duration.append(duration_list)
            self.task_duration_list.append(candidate_duration)

    def match_time_from_msprof(self, msprof):
        op_dict = dict()
        for task in msprof.tasks:
            if "item_id" not in task.args:
                continue
            op_dict[task.args["item_id"]] = {"task_duration": task.dur}
        for candidates in self.candidates:
            candidate_duration = []
            for candidate in candidates:
                duration_list = []
                for node in candidate.values():
                    if node.op_name not in op_dict:
                        logger.warning("Operator %s is missing in msprof, which will be set to 0.", node.op_name)
                        duration_list.append(0.0)
                        continue
                    duration_list.append(float(op_dict[node.op_name].get("task_duration")))
                candidate_duration.append(duration_list)
            self.task_duration_list.append(candidate_duration)

    def make_render(self, html_render):
        if not self.candidates:
            return

        candidates_list = []
        for case_id, nodes in enumerate(self.candidates):
            candidate_dict = dict()
            candidate_dict['counts'] = len(nodes)
            candidate_dict['matches'] = []
            has_time_info = False
            if self.task_duration_list:
                has_time_info = True
                candidate_dict['total_duration'] = round(
                    sum(
                        sum(duration)
                        for duration in self.task_duration_list[case_id]
                    ), 2)
            for node_index, refer_node in enumerate(nodes):
                match = []
                index = 0
                pass_name = ','.join(item.op_type for item in refer_node.keys())
                for query_node, host_node in refer_node.items():
                    fusion_pattern = query_node.op_pass

                    if 'op_pass' not in candidate_dict:
                        candidate_dict['op_pass'] = fusion_pattern
                    if 'fusion_pattern' not in candidate_dict:
                        candidate_dict['fusion_pattern'] = pass_name
                    match_attr = dict()
                    match_attr['op_name'] = host_node.op_name
                    match_attr['dtype'] = query_node.op_type
                    if has_time_info:
                        match_attr['duration'] = round(self.task_duration_list[case_id][node_index][index], 2)
                    index += 1
                    match.append(match_attr)
                match_attr = dict()
                match_attr['op_name'] = "-"
                match_attr['dtype'] = "-"
                if has_time_info:
                    match_attr['duration'] = round(sum(self.task_duration_list[case_id][node_index]), 2)
                match.append(match_attr)
                candidate_dict['matches'].append(match)
            candidates_list.append(candidate_dict)
        html_render.render_template(key="computation",
                                    template_dir="templates",
                                    template_name="fusion.html",
                                    candidates=candidates_list)

    def make_record(self, result: OptimizeResult):
        """
        make record for what and how to optimize
        """
        if not self.candidates:
            return

        prompt_class = BasePrompt.get_prompt_class(self.__class__.__name__)
        optimization_item = OptimizeItem(
            prompt_class.PROBLEM,
            prompt_class.DESCRIPTION.format(len(self.candidates)),
            [prompt_class.SUGGESTION]
        )
        total_time = 0.0
        for candidate in self.task_duration_list:
            for duration in candidate:
                total_time += sum(duration)
        statistics_item = StatisticsItem(0,
                                         total_time,
                                         sum([len(candidate) for candidate in self.candidates])
                                         )
        result.add(OptimizeRecord(optimization_item, statistics_item))

        record_title = [
            "issue_id", "graph_name", "op_name", "fusion_structure", "fusion_pattern",
            "op_type", "input_shape", "input_format",
            "input_dtype", "output_shape", "output_format", "output_dtype"
        ]
        result.add_detail('fusion issues', headers=record_title)

        for case_id, nodes in enumerate(self.candidates):
            for _, refer_node in enumerate(nodes):
                pass_name = ','.join(item.op_type for item in refer_node.keys())
                for query_node, host_node in refer_node.items():
                    fusion_pattern = query_node.op_pass
                    detail = [
                        case_id,
                        host_node.graph_name,
                        host_node.op_name,
                        pass_name,
                        fusion_pattern,
                        query_node.op_type,
                        self.get_attr_shape(host_node, "input", "shape"),
                        self.get_attr_type(host_node, "input", "format"),
                        self.get_attr_type(host_node, "input", "dtype"),
                        self.get_attr_shape(host_node, "output", "shape"),
                        self.get_attr_type(host_node, "output", "format"),
                        self.get_attr_type(host_node, "output", "dtype"),
                    ]
                    result.add_detail('fusion issues', detail=detail)
