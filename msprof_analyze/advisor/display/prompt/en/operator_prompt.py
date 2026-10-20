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


class OperatorPrompt:
    RANK_ID = "RANK {} "
    PYTORCH_OPERATOR_TUNE_SUGGESTION = (
        "Optimize operator by AOE, such as:\n'aoe --job_type=2 --model_path=$user_dump_path --tune_ops_file={}'\n"
    )
    MSLITE_OPERATOR_TUNE_SUGGESTION = (
        "Optimize operator by AOE in MindSpore lite framework, such as:\n"
        "converter_lite --fmk=ONNX --optimize=ascend_oriented --saveType=MINDIR "
        "--modelFile=$user_model.onnx --outputFile=user_model "
        "--configFile=./config.txt\n"
    )
    PYTORCH_RELEASE_SUGGESTION = "for details please refer to link : <a href=\"{}\" target='_blank'>LINK</a>"
    MSLITE_RELEASE_SUGGESTION = (
        "\nThe config file for MSLite AOE usage is as follows:\n"
        "[ascend_context]\n"
        "aoe_mode=\"operator tuning\"\n"
        "--tune_ops_file={}\n"
        "\nFor details please refer to link : <a href="
        "\"{}\" target='_blank'>LINK</a>"
    )
