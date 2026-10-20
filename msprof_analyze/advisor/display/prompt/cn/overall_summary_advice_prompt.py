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
        "计算时长": "如果你想了解更多详细建议请使用 msprof-analyze advisor computation.",
        "未被掩盖的通信时长": "如果你想了解更多详细建议请使用 msprof-analyze advisor schedule.",
        "空闲时长": "如果你想了解更多详细建议请使用 msprof-analyze advisor schedule.",
    }
    TIME_NAME_MAP = {
        "计算时长": "computing",
        "未被掩盖的通信时长": "communication",
        "空闲时长": "free",
        'Cube算子时长(数量)': 'Cube Time',
        'Vector算子时长(数量)': 'Vector Time',
        'Flash Attention算子时长(前向)(数量)': 'Flash Attention Time(Forward)',
        'Flash Attention算子时长(反向)(数量)': 'Flash Attention Time(Backward)',
        '其它时长': "Other Computing Time",
        'SDMA时长(数量)': 'SDMA Time',
    }
    PERFORMANCE_TIME_DICT = {
        "计算时长": [
            'Cube时长(数量)',
            'Vector时长(数量)',
            'Flash Attention时长(前向)(数量)',
            'Flash Attention时长(反向)(数量)',
            '其它时长',
        ],
        "未被掩盖的通信时长(等待时长)": [],
        "空闲时长": ['SDMA Time(Num)'],
    }
