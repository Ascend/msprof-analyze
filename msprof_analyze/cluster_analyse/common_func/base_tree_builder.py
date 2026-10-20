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
