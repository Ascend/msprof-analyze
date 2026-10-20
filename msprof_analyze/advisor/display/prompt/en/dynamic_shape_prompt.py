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
    RANK_ID = "RANK {} "
    PROBLEM = "Operator Dynamic Shape Issues"
    DESCRIPTION = "Found all operators are dynamic shape"
    ENABLE_COMPILED_SUGGESTION = (
        "Please place the following code at the entrance of the python script to disable jit compile.\n "
        "Code: `torch_npu.npu.set_compile_mode(jit_compile=False) \n "
        "torch_npu.npu.config.allow_internal_format = False`.\n"
    )
    RELEASE_SUGGESTION = "for details please refer to link : <a href={} target='_blank'>LINK</a>"
