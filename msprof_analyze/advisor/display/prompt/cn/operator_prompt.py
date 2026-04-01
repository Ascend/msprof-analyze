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

class OperatorPrompt(object):
    RANK_ID = "{}号卡"
    PYTORCH_OPERATOR_TUNE_SUGGESTION = "通过AOE优化算子，使用样例如下：\n" \
                                        "'aoe --job_type=2 --model_path=$user_dump_path " \
                                        "--tune_ops_file={}'\n"
    MSLITE_OPERATOR_TUNE_SUGGESTION = f"在MindSpore Lite 框架通过AOE优化算子，使用样例如下：\n" \
                                      f"converter_lite --fmk=ONNX --optimize=ascend_oriented --saveType=MINDIR " \
                                      f"--modelFile=$user_model.onnx --outputFile=user_model " \
                                      f"--configFile=./config.txt\n"
    PYTORCH_RELEASE_SUGGESTION = "详细信息请参考：<a href={} title='按住 Ctrl（Windows/Linux）或 Cmd（Mac）并点击以在新标签页中打开'>链接</a>"
    MSLITE_RELEASE_SUGGESTION = "\nMSLite AOE的配置文件如下usage：\n" \
                                "[ascend_context]\n" \
                                "aoe_mode=\"operator tuning\"\n" \
                                "--tune_ops_file={}\n" \
                                "\n详细信息请参考：<a href=" \
                                "{} title='按住 Ctrl（Windows/Linux）或 Cmd（Mac）并点击以在新标签页中打开'>链接</a>"