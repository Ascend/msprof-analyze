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
            graph = Graph(nodes=parser.nodes,
                          edges=parser.edges,
                          name="Default")
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
