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


class TimelineFusionOpsPrompt:
    PROBLEM = "Affinity API Issues"
    DESCRIPTION = "On the runtime env cann-{} and torch-{}, found {} apis to be replaced"
    SUGGESTION = "Please replace training api according to sub table 'Affinity training api'"
    EMPTY_STACK_DESCRIPTION = ", but with no stack"
    EMPTY_STACKS_SUGGESTION = (
        "These APIs have no code stack. If parameter 'with_stack=False' while profiling, "
        "please refer to {} to set 'with_stack=True'. "
        "Otherwise, ignore following affinity APIs due to backward broadcast lack of stack."
    )
