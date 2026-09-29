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


class OverallSummaryAdvicePrompt:
    ADVICE_MAP = {
        "Computing Time": "if you want more detailed advice please use msprof-analyze advisor computation.",
        "Uncovered Communication Time": "if you want more detailed advice, please use msprof-analyze advisor schedule.",
        "Free Time": "if you want more detailed advice please use msprof-analyze advisor schedule.",
    }
    TIME_NAME_MAP = {
        "Computing Time": "computing",
        "Uncovered Communication Time": "communication",
        "Free Time": "free",
        'Cube Time(Num)': 'Cube Time',
        'Vector Time(Num)': 'Vector Time',
        'Flash Attention Time(Forward)(Num)': 'Flash Attention Time(Forward)',
        'Flash Attention Time(Backward)(Num)': 'Flash Attention Time(Backward)',
        'Other Time': "Other Computing Time",
        'SDMA Time(Num)': 'SDMA Time',
    }
    PERFORMANCE_TIME_DICT = {
        "Computing Time": [
            'Cube Time(Num)',
            'Vector Time(Num)',
            'Flash Attention Time(Forward)(Num)',
            'Flash Attention Time(Backward)(Num)',
            'Other Time',
        ],
        "Uncovered Communication Time(Wait Time)": [],
        "Free Time": ['SDMA Time(Num)'],
    }
