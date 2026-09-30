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

from msprof_analyze.prof_common.logger import get_logger
from typing import List

from msprof_analyze.advisor.dataset.dataset import Dataset
from msprof_analyze.advisor.common.graph.graph_parser import HostGraphParser
from msprof_analyze.advisor.common.graph.graph import Graph
from msprof_analyze.advisor.utils.utils import load_parameter, lazy_property, get_file_path_from_directory

logger = get_logger()


class GraphDataset(Dataset):
    """
    data directory dataset
    """

    FILE_PATTERN = "ATT_ADVISOR_GRAPH_FILE"

    def __init__(self, collection_path, data: dict = None, **kwargs) -> None:
        self.graph_files: List[HostGraphParser] = []
        super().__init__(collection_path, data)

    @lazy_property
    def graphs(self) -> List[Graph]:
        """
        get a list of graphs
        return: List[Graph]
        """
        graphs = []
        for parser in self.graph_files:
            graph = Graph(nodes=parser.nodes, edges=parser.edges, name="Default")
            graph.build()
            graphs.append(graph)
        graphs.sort(key=lambda g: g.name)
        if len(self.graph_files) >= 1:
            del self.graph_files[0]  # remove previous useless data
        return graphs

    def is_empty(self) -> bool:
        """check empty graph dataset"""
        return len(self.graph_files) == 0

    def _parse(self):
        def is_matching_file(file):
            return file.endswith(load_parameter(self.FILE_PATTERN, "Build.txt"))

        graph_list = get_file_path_from_directory(self.collection_path, is_matching_file)
        for graph_file_path in graph_list[-1:]:
            logger.info("Prepare to parse %s as default graph.", graph_file_path)
            graph_file = HostGraphParser(graph_file_path)
            self.graph_files.append(graph_file)
        return self.graph_files
