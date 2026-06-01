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

from msprof_analyze.cluster_analyse.recipes.module_statistic.tree_build import (
    KernelNode as ModuleStatisticKernelNode,
    ModuleNode,
    NodeType,
    TreeBuilder,
    TreeNode,
)


class KernelNode(ModuleStatisticKernelNode):
    """Keep the operator MFU kernel node API while reusing the shared tree node."""

    def __init__(self, start, end, name, mfu):
        super().__init__(start, end, name)
        self.mfu = mfu


__all__ = ['KernelNode', 'ModuleNode', 'NodeType', 'TreeBuilder', 'TreeNode']
