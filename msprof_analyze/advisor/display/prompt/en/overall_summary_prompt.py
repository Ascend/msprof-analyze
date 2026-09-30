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


class OverallSummaryPrompt:
    OVERALL_SUMMARY_ANALYZER = "Overall Summary"
    ADVICE_MAP = {
        "Computing Time": "if you want more detailed advice please go to mstt_advisor_*.html",
        "Uncovered Communication Time": "if you want more detailed advice please go to mstt_advisor_*.html",
        "Free Time": "if you want more detailed advice please go to mstt_advisor_*.html",
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
        "Computing Time": "computing_time_ms",
        "    -- Flash Attention": "fa_time_ms",
        "    -- Conv": "conv_time_ms",
        "    -- Matmul": "matmul_time_ms",
        "    -- Vector": "vector_time_ms",
        "    -- SDMA(Tensor Move)": "tensor_move_time_ms",
        "    -- Other Cube": "other_cube_time_ms",
        "Uncovered Communication Time": "uncovered_communication_time_ms",
        "    -- Wait": "wait_time_ms",
        "    -- Transmit": "transmit_time_ms",
        "Free Time": "free_time_ms",
        "    -- SDMA": "sdma_time_ms",
        "    -- Free": "free_ms",
        "E2E Time": "e2e_time_ms",
    }
