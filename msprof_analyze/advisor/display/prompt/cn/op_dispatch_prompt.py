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


class OpDispatchPrompt:
    PROBLEM = "算子下发"
    DESCRIPTION = "发现{}个算子编译问题。"
    SUGGESTION = (
        "请在python脚本入口添加以下代码关闭在线编译：\n"
        "'torch_npu.npu.set_compile_mode(jit_compile=False) \n"
        "torch_npu.npu.config.allow_internal_format = False' \n"
    )
