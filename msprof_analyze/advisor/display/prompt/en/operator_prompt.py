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
    RANK_ID = "RANK {} "
    PYTORCH_OPERATOR_TUNE_SUGGESTION = "Optimize operator by AOE, such as:\n" \
                                       "'aoe --job_type=2 --model_path=$user_dump_path " \
                                       "--tune_ops_file={}'\n"
    MSLITE_OPERATOR_TUNE_SUGGESTION = "Optimize operator by AOE in mindspore lite framework, such as:\n" \
                                      "converter_lite --fmk=ONNX --optimize=ascend_oriented --saveType=MINDIR " \
                                      "--modelFile=$user_model.onnx --outputFile=user_model " \
                                      "--configFile=./config.txt\n"
    PYTORCH_RELEASE_SUGGESTION = "for details please refer to link : <a href=\"{}\" title='Hold Ctrl (Windows/Linux) or Cmd (Mac) and click to open in a new tab'>LINK</a>"
    MSLITE_RELEASE_SUGGESTION = "\nThe config file for MSLite AOE usage is as follows:\n" \
                                "[ascend_context]\n" \
                                "aoe_mode=\"operator tuning\"\n" \
                                "--tune_ops_file={}\n" \
                                "\nFor details please refer to link : <a href=" \
                                "\"{}\" title='Hold Ctrl (Windows/Linux) or Cmd (Mac) and click to open in a new tab'>LINK</a>"
