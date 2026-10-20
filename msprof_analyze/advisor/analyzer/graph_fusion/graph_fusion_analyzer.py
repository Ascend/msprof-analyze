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
from typing import List
from functools import partial

from msprof_analyze.advisor.analyzer.base_analyzer import BaseAnalyzer
from msprof_analyze.advisor.result.result import OptimizeResult
from msprof_analyze.advisor.dataset.graph_dataset import GraphDataset
from msprof_analyze.advisor.analyzer.graph_fusion.graph_fusion_checker import GraphFusionRules
from msprof_analyze.advisor.dataset.profiling.profiling_dataset import ProfilingDataset
from msprof_analyze.advisor.display.html.render import HTMLRender


class FusionOPAnalyzer(BaseAnalyzer):
    """
    fusion optimizer
    """

    RULES = dict(graph_dataset=partial(GraphFusionRules, "rules/op_fusion_pass.yaml"))
    dataset_cls_list = [GraphDataset, ProfilingDataset]

    def __init__(self, collection_path, **kwargs) -> None:
        super().__init__(collection_path, **kwargs)
        self.result = OptimizeResult()
        self.html_render = HTMLRender()
        self.html = None

    @BaseAnalyzer.check_data((GraphDataset.get_key(),))
    def optimize(self, **kwargs):
        """
        :return: result
        """
        self._check(
            self.dataset_list.get("GraphDataset"),
            self.dataset_list.get("ProfilingDataset"),
            kwargs.get("add_render_list"),
        )
        return self.result

    def get_priority(self, max_mem_op_dur=None):
        pass

    def _check(
        self, graph_data: List[GraphDataset], profiling_data: List[ProfilingDataset] = None, add_render_list=True
    ) -> None:
        if len(graph_data) == 0 or graph_data[0].is_empty():
            return
        for _, rule in self.RULES.items():
            checker = rule()
            if profiling_data is None:
                checker.find_fusion_matched_issues(graph_data)
            else:
                checker.find_fusion_matched_issues_with_times(graph_data, profiling_data)
            checker.make_record(self.result)
            self.html = checker.make_render(self.html_render)
