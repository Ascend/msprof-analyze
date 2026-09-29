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


class DynamicShapePrompt:
    RANK_ID = "{}号卡"
    PROBLEM = "动态shape算子"
    DESCRIPTION = "找到所有是动态shape的算子"
    ENABLE_COMPILED_SUGGESTION = (
        "在python脚本入口加入以下代码关闭在线编译：\n"
        "'torch_npu.npu.set_compile_mode(jit_compile=False) \n "
        "torch_npu.npu.config.allow_internal_format = False' \n"
    )
    RELEASE_SUGGESTION = "详细信息请参考：<a href=\"{}\" target='_blank'>链接</a>"
