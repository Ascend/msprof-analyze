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
    PROBLEM = "亲和API接口"
    DESCRIPTION = "目前运行环境版本为cann-{}和torch-{}，发现有{}个api接口可以替换。"
    SUGGESTION = "请根据子表'Affinity training api'替换训练api接口"
    EMPTY_STACK_DESCRIPTION = ",但没有堆栈"
    EMPTY_STACKS_SUGGESTION = (
        "这些API接口没有代码堆栈。如果采集profiling时参数为'with_stack=False'，"
        "请参考{}设置'with_stack=True'。"
        "另外，由于反向传播没有堆栈，请忽略以下亲和APIs。"
    )
