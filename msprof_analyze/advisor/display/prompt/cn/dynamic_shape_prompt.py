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

class DynamicShapePrompt(object):
    RANK_ID = "{}号卡"
    PROBLEM = "动态shape算子"
    DESCRIPTION = f"找到所有是动态shape的算子"
    ENABLE_COMPILED_SUGGESTION = "在python脚本入口加入以下代码关闭在线编译：\n" \
                                 "'torch_npu.npu.set_compile_mode(jit_compile=False) \n " \
                                 "torch_npu.npu.config.allow_internal_format = False' \n"
    RELEASE_SUGGESTION = "详细信息请参考：<a href=\"{}\" title='按住 Ctrl（Windows/Linux）或 Cmd（Mac）并点击以在新标签页中打开'>链接</a>"
