# Copyright (c) 2025, Huawei Technologies Co., Ltd.
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

from abc import ABC, abstractmethod


class BaseTreeNode(ABC):
    """Establish an abstract base tree node class"""
    def __init__(self, start, end, name, node_type):
        self.start = start
        self.end = end
        self.name = name
        self.node_type = node_type
        self.children = []

    @abstractmethod
    def create_from_df(self, df, start_col, end_col, name_col, node_type):
        """Abstract method: create from df"""
        pass

    def add_child(self, node):
        self.children.append(node)


class BaseTreeBuilder(ABC):
    """Establish an abstract base tree builder class"""
    def __init__(self):
        pass

    @abstractmethod
    def build_tree(self, start_col, end_col, name_col, node_type):
        """Abstract method: build tree"""
        pass