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
from enum import Enum
from dataclasses import dataclass

from msprof_analyze.cluster_analyse.cluster_utils.parallel_algorithm import MegatronAlgorithm


class ParallelAlgorithmType(Enum):
    Megatron = 0


@dataclass
class RankMetrics:
    computing: float = 0.0
    communication: float = 0.0
    free: float = 0.0


class RankNode:
    def __init__(self, index: int, rank_ids: list, category: str, metrics: RankMetrics):
        self.index = index
        self.rank_ids = rank_ids
        self.category = category
        self.metrics = metrics
        self.children = []

    def add_child(self, child_node):
        if isinstance(child_node, RankNode):
            self.children.append(child_node)
        else:
            raise TypeError("Child must be an instance of TreeNode")


class ParallelStrategyCalculator:
    ROOT_LABEL = "ROOT"
    TP_LABEL = "TP"
    PP_LABEL = "PP"
    DP_LABEL = "DP"

    parallel_algorithms = {ParallelAlgorithmType.Megatron: MegatronAlgorithm}

    def __init__(self, algorithm_type: ParallelAlgorithmType = ParallelAlgorithmType.Megatron, **kwargs):
        self.algorithm = self.parallel_algorithms.get(algorithm_type, MegatronAlgorithm)(**kwargs)

        # result of partition rank id to DP Index, PP Index, TP Index
        self.ranks_ptd_map = [None] * self.algorithm.world_size
        self.root_node = None

    def run(self):
        self.algorithm.partition()
        self._build_tree()
        self._dfs(self.root_node)
        return self.ranks_ptd_map

    def _build_tree(self):
        if not self.algorithm.all_model_parallel_group_ranks:
            return

        self.root_node = RankNode(
            -1, self.algorithm.all_model_parallel_group_ranks, ParallelStrategyCalculator.ROOT_LABEL, RankMetrics()
        )

        # DP Level
        for i, dp_group in enumerate(self.algorithm.all_model_parallel_group_ranks):
            dp_node = RankNode(i, dp_group, ParallelStrategyCalculator.DP_LABEL, RankMetrics())

            # PP Level
            for pp_idx, j in enumerate(range(0, len(dp_group), self.algorithm.tensor_model_parallel_size)):
                pp_group = dp_group[j : j + self.algorithm.tensor_model_parallel_size]
                pp_node = RankNode(pp_idx, pp_group, ParallelStrategyCalculator.PP_LABEL, RankMetrics())

                # TP Level
                for k, tp_rank in enumerate(pp_group):
                    tp_node = RankNode(k, [tp_rank], ParallelStrategyCalculator.TP_LABEL, RankMetrics())
                    pp_node.add_child(tp_node)

                dp_node.add_child(pp_node)
            self.root_node.add_child(dp_node)

    def _dfs(self, rank_node: RankNode, parent_node: RankNode = None, grandparent_node: RankNode = None):
        if rank_node is None:
            return

        if not rank_node.children:
            if rank_node.rank_ids:
                self.ranks_ptd_map[rank_node.rank_ids[0]] = (
                    grandparent_node.index,  # DP Index
                    parent_node.index,  # PP Index
                    rank_node.index,  # TP Index
                )

        for child in rank_node.children:
            self._dfs(child, rank_node, parent_node)
