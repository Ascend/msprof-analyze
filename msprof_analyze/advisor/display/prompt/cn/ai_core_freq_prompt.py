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


class AICoreFreqPrompt:
    RANK_ID = "{}号卡"
    PROBLEM = "AIcore频率"
    DESCRIPTION = "在降频期间发现{}个算子，频率降低比例超过了{}。"
    RANK_DESCRIPTION = "对于{}号卡，"
    SUGGESTION = "请检查您的机器温度或最大功率。"
