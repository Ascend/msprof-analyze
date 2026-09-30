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
from msprof_analyze.prof_common.constant import Constant


class CellFormatType:
    DEFAULT = {
        "font_name": "Arial",
        'font_size': 11,
        'align': 'left',
        'valign': 'vcenter',
        'border': True,
        'num_format': '#,##0',
    }  # 数字显示整数，无背景色
    DEFAULT_FLOAT = {
        "font_name": "Arial",
        'font_size': 11,
        'align': 'left',
        'valign': 'vcenter',
        'border': True,
        'num_format': '#,##0.00',
    }  # 保留2位小数，无背景色
    DEFAULT_RATIO = {
        "font_name": "Arial",
        'font_size': 11,
        'align': 'left',
        'valign': 'vcenter',
        'border': True,
        'num_format': '0.00%',
    }  # 百分比显示，保留2位小数，无背景色
    RED_RATIO = {
        "font_name": "Arial",
        'font_size': 11,
        'align': 'left',
        'valign': 'vcenter',
        'border': True,
        'num_format': '0.00%',
        "fg_color": Constant.RED_COLOR,
    }  # 百分比显示，保留2位小数，单元格背景色为红色
    BOLD_STR = {
        "font_name": "Arial",
        'font_size': 11,
        'align': 'left',
        'valign': 'vcenter',
        'border': True,
        'bold': True,
    }  # 字符串，无背景色，字体加粗
    BLUE_BOLD = {
        "font_name": "Arial",
        'font_size': 11,
        'fg_color': Constant.BLUE_COLOR,
        'align': 'left',
        'valign': 'vcenter',
        'bold': True,
        'border': True,
    }  # 蓝色背景，加粗
    GREEN_BOLD = {
        "font_name": "Arial",
        'font_size': 11,
        'fg_color': Constant.GREEN_COLOR,
        'align': 'left',
        'valign': 'vcenter',
        'bold': True,
        'border': True,
    }  # 绿色背景，加粗
    YELLOW_BOLD = {
        "font_name": "Arial",
        'font_size': 11,
        'fg_color': Constant.YELLOW_COLOR,
        'align': 'left',
        'valign': 'vcenter',
        'bold': True,
        'border': True,
    }  # 黄色背景，加粗
    BLUE_NORMAL = {'fg_color': Constant.BLUE_COLOR}  # 蓝色背景，主要用于行样式
    LIGHT_BLUE_NORMAL = {'fg_color': Constant.LIGHT_BLUE_COLOR}  # 淡蓝色背景，主要用于行样式


class ExcelConfig:
    ORDER = "Order Id"
    OPERATOR_NAME = "Operator Name"
    INPUT_SHAPE = "Input Shape"
    INPUT_TYPE = "Input Type"
    KERNEL_DETAILS = "Kernel Details"
    MEMORY_DETAILS = "Allocated Details"
    DEVICE_DURATION = "Device Duration(us)"
    DIFF_RATIO = "Diff Ratio"
    DIFF_DUR = "Diff Duration(us)"
    DIFF_SIZE = "Diff Size(KB)"
    SIZE = "Size(KB)"
    TOP = "Top"
    BASE_DEVICE_DURATION = "Base Device Duration(ms)"
    COMPARISON_DEVICE_DURATION = "Comparison Device Duration(ms)"
    BASE_OPERATOR_NUMBER = "Base Operator Number"
    COMPARISON_OPERATOR_NUMBER = "Comparison Operator Number"
    DIFF_TIME = "Diff Duration(ms)"
    BASE_ALLOCATED_TIMES = "Base Allocated Duration(ms)"
    COMPARISON_ALLOCATED_TIMES = "Comparison Allocated Duration(ms)"
    BASE_ALLOCATED_MEMORY = "Base Allocated Memory(MB)"
    COMPARISON_ALLOCATED_MEMORY = "Comparison Allocated Memory(MB)"
    DIFF_MEMORY = "Diff Memory(MB)"
    COMM_OP_NAME = "Communication OP Name"
    TASK_NAME = "Task Name"
    CALLS = "Calls"
    TOTAL_DURATION = "Total Duration(us)"
    AVG_DURATION = "Avg Duration(us)"
    MAX_DURATION = "Max Duration(us)"
    MIN_DURATION = "Min Duration(us)"
    MODULE_CLASS = "Module Class"
    MODULE_NAME = "Module Name"
    DEVICE_SELF_TIME = "Device Self Time(ms)"
    DEVICE_TOTAL_TIME = "Device Total Time(ms)"
    DIFF_SELF_TIME = "Device Self Time Diff(ms)"
    DIFF_TOTAL_RATIO = "Diff Total Ratio"
    DIFF_TOTAL_TIME = "Device Total Time Diff(ms)"
    DEVICE_SELF_TIME_US = "Device Self Time(us)"
    DEVICE_TOTAL_TIME_US = "Device Total Time(us)"
    DIFF_SELF_TIME_US = "Device Self Time Diff(us)"
    DIFF_TOTAL_TIME_US = "Device Total Time Diff(us)"
    NUMBER = "Number"
    MODULE_LEVEL = "Module Level"
    BASE_CALL_STACK = "Base Call Stack"
    COMPARISON_CALL_STACK = "Comparison Call Stack"
    INDEX = "Index"
    DURATION = "Duration(ms)"
    DURATION_RATIO = "Duration Ratio"
    DIFF_DUR_MS = "Diff Duration(ms)"
    API_NAME = "api name"
    TOTAL_DURATION_MS = "Total Duration(ms)"
    AVG_DURATION_MS = "Avg Duration(ms)"
    SELF_TIME_MS = "Self Time(ms)"
    DIFF_SELF_RATIO = "Diff Self Ratio"
    DIFF_AVG_RATIO = "Diff Avg Ratio"
    DIFF_CALLS_RATIO = "Diff Calls Ratio"
    KERNEL = "Kernel"
    KERNEL_TYPE = "Kernel Type"
    CORE_TYPE = "Core Type"

    HEADERS = {
        Constant.OPERATOR_TABLE: [
            {"name": ORDER, "type": CellFormatType.DEFAULT, "width": 10},
            {"name": OPERATOR_NAME, "type": CellFormatType.BOLD_STR, "width": 30},
            {"name": INPUT_SHAPE, "type": CellFormatType.DEFAULT, "width": 20},
            {"name": INPUT_TYPE, "type": CellFormatType.DEFAULT, "width": 20},
            {"name": KERNEL_DETAILS, "type": CellFormatType.DEFAULT, "width": 20},
            {"name": DEVICE_DURATION, "type": CellFormatType.DEFAULT_FLOAT, "width": 20},
            {"name": OPERATOR_NAME, "type": CellFormatType.BOLD_STR, "width": 30},
            {"name": INPUT_SHAPE, "type": CellFormatType.DEFAULT, "width": 20},
            {"name": INPUT_TYPE, "type": CellFormatType.DEFAULT, "width": 20},
            {"name": KERNEL_DETAILS, "type": CellFormatType.DEFAULT, "width": 20},
            {"name": DEVICE_DURATION, "type": CellFormatType.DEFAULT_FLOAT, "width": 20},
            {"name": DIFF_DUR, "type": CellFormatType.DEFAULT_FLOAT, "width": 20},
            {"name": DIFF_RATIO, "type": CellFormatType.DEFAULT_RATIO, "width": 20},
        ],
        Constant.MEMORY_TABLE: [
            {"name": ORDER, "type": CellFormatType.DEFAULT, "width": 10},
            {"name": OPERATOR_NAME, "type": CellFormatType.BOLD_STR, "width": 30},
            {"name": INPUT_SHAPE, "type": CellFormatType.DEFAULT, "width": 20},
            {"name": INPUT_TYPE, "type": CellFormatType.DEFAULT, "width": 20},
            {"name": MEMORY_DETAILS, "type": CellFormatType.DEFAULT, "width": 20},
            {"name": SIZE, "type": CellFormatType.DEFAULT_FLOAT, "width": 20},
            {"name": OPERATOR_NAME, "type": CellFormatType.BOLD_STR, "width": 30},
            {"name": INPUT_SHAPE, "type": CellFormatType.DEFAULT, "width": 20},
            {"name": INPUT_TYPE, "type": CellFormatType.DEFAULT, "width": 20},
            {"name": MEMORY_DETAILS, "type": CellFormatType.DEFAULT, "width": 20},
            {"name": SIZE, "type": CellFormatType.DEFAULT_FLOAT, "width": 20},
            {"name": DIFF_SIZE, "type": CellFormatType.DEFAULT_FLOAT, "width": 20},
            {"name": DIFF_RATIO, "type": CellFormatType.DEFAULT_RATIO, "width": 20},
        ],
        Constant.OPERATOR_TOP_TABLE: [
            {"name": TOP, "type": CellFormatType.DEFAULT, "width": 10},
            {"name": OPERATOR_NAME, "type": CellFormatType.BOLD_STR, "width": 30},
            {"name": BASE_DEVICE_DURATION, "type": CellFormatType.DEFAULT_FLOAT, "width": 25},
            {"name": BASE_OPERATOR_NUMBER, "type": CellFormatType.DEFAULT, "width": 25},
            {"name": COMPARISON_DEVICE_DURATION, "type": CellFormatType.DEFAULT_FLOAT, "width": 30},
            {"name": COMPARISON_OPERATOR_NUMBER, "type": CellFormatType.DEFAULT, "width": 30},
            {"name": DIFF_TIME, "type": CellFormatType.DEFAULT_FLOAT, "width": 20},
            {"name": DIFF_RATIO, "type": CellFormatType.DEFAULT_RATIO, "width": 20},
        ],
        Constant.MEMORY_TOP_TABLE: [
            {"name": TOP, "type": CellFormatType.DEFAULT, "width": 10},
            {"name": OPERATOR_NAME, "type": CellFormatType.BOLD_STR, "width": 30},
            {"name": BASE_ALLOCATED_TIMES, "type": CellFormatType.DEFAULT_FLOAT, "width": 25},
            {"name": BASE_ALLOCATED_MEMORY, "type": CellFormatType.DEFAULT_FLOAT, "width": 30},
            {"name": BASE_OPERATOR_NUMBER, "type": CellFormatType.DEFAULT, "width": 25},
            {"name": COMPARISON_ALLOCATED_TIMES, "type": CellFormatType.DEFAULT_FLOAT, "width": 27},
            {"name": COMPARISON_ALLOCATED_MEMORY, "type": CellFormatType.DEFAULT_FLOAT, "width": 33},
            {"name": COMPARISON_OPERATOR_NUMBER, "type": CellFormatType.DEFAULT, "width": 25},
            {"name": DIFF_MEMORY, "type": CellFormatType.DEFAULT_FLOAT, "width": 20},
            {"name": DIFF_RATIO, "type": CellFormatType.DEFAULT_RATIO, "width": 20},
        ],
        Constant.COMMUNICATION_TABLE: [
            {"name": ORDER, "type": CellFormatType.DEFAULT, "width": 10},
            {"name": COMM_OP_NAME, "type": CellFormatType.BOLD_STR, "width": 25},
            {"name": TASK_NAME, "type": CellFormatType.DEFAULT, "width": 20},
            {"name": CALLS, "type": CellFormatType.DEFAULT, "width": 10},
            {"name": TOTAL_DURATION, "type": CellFormatType.DEFAULT_FLOAT, "width": 17},
            {"name": AVG_DURATION, "type": CellFormatType.DEFAULT_FLOAT, "width": 17},
            {"name": MAX_DURATION, "type": CellFormatType.DEFAULT_FLOAT, "width": 17},
            {"name": MIN_DURATION, "type": CellFormatType.DEFAULT_FLOAT, "width": 17},
            {"name": COMM_OP_NAME, "type": CellFormatType.BOLD_STR, "width": 25},
            {"name": TASK_NAME, "type": CellFormatType.DEFAULT, "width": 20},
            {"name": CALLS, "type": CellFormatType.DEFAULT, "width": 10},
            {"name": TOTAL_DURATION, "type": CellFormatType.DEFAULT_FLOAT, "width": 17},
            {"name": AVG_DURATION, "type": CellFormatType.DEFAULT_FLOAT, "width": 17},
            {"name": MAX_DURATION, "type": CellFormatType.DEFAULT_FLOAT, "width": 17},
            {"name": MIN_DURATION, "type": CellFormatType.DEFAULT_FLOAT, "width": 17},
            {"name": DIFF_DUR, "type": CellFormatType.DEFAULT_FLOAT, "width": 20},
            {"name": DIFF_RATIO, "type": CellFormatType.DEFAULT_RATIO, "width": 20},
        ],
        Constant.MODULE_TOP_TABLE: [
            {"name": ORDER, "type": CellFormatType.DEFAULT, "width": 10},
            {"name": MODULE_CLASS, "type": CellFormatType.DEFAULT, "width": 20},
            {"name": MODULE_LEVEL, "type": CellFormatType.DEFAULT, "width": 15},
            {"name": MODULE_NAME, "type": CellFormatType.DEFAULT, "width": 35},
            {"name": OPERATOR_NAME, "type": CellFormatType.DEFAULT, "width": 25},
            {"name": KERNEL_DETAILS, "type": CellFormatType.DEFAULT, "width": 20},
            {"name": DEVICE_SELF_TIME, "type": CellFormatType.DEFAULT_FLOAT, "width": 20},
            {"name": NUMBER, "type": CellFormatType.DEFAULT, "width": 10},
            {"name": DEVICE_TOTAL_TIME, "type": CellFormatType.DEFAULT_FLOAT, "width": 20},
            {"name": KERNEL_DETAILS, "type": CellFormatType.DEFAULT, "width": 20},
            {"name": DEVICE_SELF_TIME, "type": CellFormatType.DEFAULT_FLOAT, "width": 20},
            {"name": NUMBER, "type": CellFormatType.DEFAULT, "width": 10},
            {"name": DEVICE_TOTAL_TIME, "type": CellFormatType.DEFAULT_FLOAT, "width": 20},
            {"name": DIFF_TOTAL_TIME, "type": CellFormatType.DEFAULT_FLOAT, "width": 20},
            {"name": DIFF_SELF_TIME, "type": CellFormatType.DEFAULT_FLOAT, "width": 20},
            {"name": DIFF_TOTAL_RATIO, "type": CellFormatType.DEFAULT_RATIO, "width": 15},
            {"name": BASE_CALL_STACK, "type": CellFormatType.DEFAULT, "width": 30},
            {"name": COMPARISON_CALL_STACK, "type": CellFormatType.DEFAULT, "width": 30},
        ],
        Constant.MODULE_TABLE: [
            {"name": ORDER, "type": CellFormatType.DEFAULT, "width": 10},
            {"name": MODULE_CLASS, "type": CellFormatType.DEFAULT, "width": 20},
            {"name": MODULE_LEVEL, "type": CellFormatType.DEFAULT, "width": 15},
            {"name": MODULE_NAME, "type": CellFormatType.DEFAULT, "width": 35},
            {"name": OPERATOR_NAME, "type": CellFormatType.DEFAULT, "width": 25},
            {"name": KERNEL_DETAILS, "type": CellFormatType.DEFAULT, "width": 20},
            {"name": DEVICE_SELF_TIME_US, "type": CellFormatType.DEFAULT_FLOAT, "width": 20},
            {"name": DEVICE_TOTAL_TIME_US, "type": CellFormatType.DEFAULT_FLOAT, "width": 20},
            {"name": OPERATOR_NAME, "type": CellFormatType.DEFAULT, "width": 25},
            {"name": KERNEL_DETAILS, "type": CellFormatType.DEFAULT, "width": 20},
            {"name": DEVICE_SELF_TIME_US, "type": CellFormatType.DEFAULT_FLOAT, "width": 20},
            {"name": DEVICE_TOTAL_TIME_US, "type": CellFormatType.DEFAULT_FLOAT, "width": 20},
            {"name": DIFF_TOTAL_TIME_US, "type": CellFormatType.DEFAULT_FLOAT, "width": 20},
            {"name": DIFF_SELF_TIME_US, "type": CellFormatType.DEFAULT_FLOAT, "width": 20},
            {"name": DIFF_TOTAL_RATIO, "type": CellFormatType.DEFAULT_RATIO, "width": 15},
            {"name": BASE_CALL_STACK, "type": CellFormatType.DEFAULT, "width": 30},
            {"name": COMPARISON_CALL_STACK, "type": CellFormatType.DEFAULT, "width": 30},
        ],
        Constant.OVERALL_METRICS_TABLE: [
            {"name": INDEX, "type": CellFormatType.DEFAULT, "width": 40},
            {"name": DURATION, "type": CellFormatType.DEFAULT_FLOAT, "width": 20},
            {"name": DURATION_RATIO, "type": CellFormatType.DEFAULT_RATIO, "width": 20},
            {"name": NUMBER, "type": CellFormatType.DEFAULT, "width": 10},
            {"name": DURATION, "type": CellFormatType.DEFAULT_FLOAT, "width": 20},
            {"name": DURATION_RATIO, "type": CellFormatType.DEFAULT_RATIO, "width": 20},
            {"name": NUMBER, "type": CellFormatType.DEFAULT, "width": 10},
            {"name": DIFF_DUR_MS, "type": CellFormatType.DEFAULT_FLOAT, "width": 20},
            {"name": DIFF_RATIO, "type": CellFormatType.DEFAULT_RATIO, "width": 10},
        ],
        Constant.API_TABLE: [
            {"name": ORDER, "type": CellFormatType.DEFAULT, "width": 10},
            {"name": API_NAME, "type": CellFormatType.BOLD_STR, "width": 30},
            {"name": TOTAL_DURATION_MS, "type": CellFormatType.DEFAULT_FLOAT, "width": 20},
            {"name": SELF_TIME_MS, "type": CellFormatType.DEFAULT_FLOAT, "width": 20},
            {"name": AVG_DURATION_MS, "type": CellFormatType.DEFAULT_FLOAT, "width": 20},
            {"name": CALLS, "type": CellFormatType.DEFAULT, "width": 20},
            {"name": TOTAL_DURATION_MS, "type": CellFormatType.DEFAULT_FLOAT, "width": 20},
            {"name": SELF_TIME_MS, "type": CellFormatType.DEFAULT_FLOAT, "width": 20},
            {"name": AVG_DURATION_MS, "type": CellFormatType.DEFAULT_FLOAT, "width": 20},
            {"name": CALLS, "type": CellFormatType.DEFAULT, "width": 20},
            {"name": DIFF_TOTAL_RATIO, "type": CellFormatType.DEFAULT_FLOAT, "width": 20},
            {"name": DIFF_SELF_RATIO, "type": CellFormatType.DEFAULT_FLOAT, "width": 20},
            {"name": DIFF_AVG_RATIO, "type": CellFormatType.DEFAULT_FLOAT, "width": 20},
            {"name": DIFF_CALLS_RATIO, "type": CellFormatType.DEFAULT_FLOAT, "width": 20},
        ],
        Constant.KERNEL_TABLE: [
            {"name": ORDER, "type": CellFormatType.DEFAULT, "width": 10},
            {"name": KERNEL, "type": CellFormatType.BOLD_STR, "width": 30},
            {"name": INPUT_SHAPE, "type": CellFormatType.DEFAULT, "width": 20},
            {"name": TOTAL_DURATION, "type": CellFormatType.DEFAULT_FLOAT, "width": 20},
            {"name": AVG_DURATION, "type": CellFormatType.DEFAULT_FLOAT, "width": 20},
            {"name": MAX_DURATION, "type": CellFormatType.DEFAULT_FLOAT, "width": 20},
            {"name": MIN_DURATION, "type": CellFormatType.DEFAULT_FLOAT, "width": 20},
            {"name": CALLS, "type": CellFormatType.DEFAULT, "width": 20},
            {"name": TOTAL_DURATION, "type": CellFormatType.DEFAULT_FLOAT, "width": 20},
            {"name": AVG_DURATION, "type": CellFormatType.DEFAULT_FLOAT, "width": 20},
            {"name": MAX_DURATION, "type": CellFormatType.DEFAULT_FLOAT, "width": 20},
            {"name": MIN_DURATION, "type": CellFormatType.DEFAULT_FLOAT, "width": 20},
            {"name": CALLS, "type": CellFormatType.DEFAULT, "width": 20},
            {"name": DIFF_TOTAL_RATIO, "type": CellFormatType.DEFAULT_FLOAT, "width": 20},
            {"name": DIFF_AVG_RATIO, "type": CellFormatType.DEFAULT_FLOAT, "width": 20},
        ],
        Constant.KERNEL_TYPE_TABLE: [
            {"name": ORDER, "type": CellFormatType.DEFAULT, "width": 10},
            {"name": KERNEL_TYPE, "type": CellFormatType.BOLD_STR, "width": 30},
            {"name": CORE_TYPE, "type": CellFormatType.DEFAULT, "width": 20},
            {"name": TOTAL_DURATION, "type": CellFormatType.DEFAULT_FLOAT, "width": 20},
            {"name": AVG_DURATION, "type": CellFormatType.DEFAULT_FLOAT, "width": 20},
            {"name": MAX_DURATION, "type": CellFormatType.DEFAULT_FLOAT, "width": 20},
            {"name": MIN_DURATION, "type": CellFormatType.DEFAULT_FLOAT, "width": 20},
            {"name": CALLS, "type": CellFormatType.DEFAULT, "width": 20},
            {"name": TOTAL_DURATION, "type": CellFormatType.DEFAULT_FLOAT, "width": 20},
            {"name": AVG_DURATION, "type": CellFormatType.DEFAULT_FLOAT, "width": 20},
            {"name": MAX_DURATION, "type": CellFormatType.DEFAULT_FLOAT, "width": 20},
            {"name": MIN_DURATION, "type": CellFormatType.DEFAULT_FLOAT, "width": 20},
            {"name": CALLS, "type": CellFormatType.DEFAULT, "width": 20},
            {"name": DIFF_TOTAL_RATIO, "type": CellFormatType.DEFAULT_FLOAT, "width": 20},
            {"name": DIFF_AVG_RATIO, "type": CellFormatType.DEFAULT_FLOAT, "width": 20},
        ],
    }

    OVERHEAD = {
        Constant.OPERATOR_TABLE: ["B1:F1", "G1:K1"],
        Constant.MEMORY_TABLE: ["B1:F1", "G1:K1"],
        Constant.COMMUNICATION_TABLE: ["B1:H1", "I1:O1"],
        Constant.OPERATOR_TOP_TABLE: ["C1:D1", "E1:F1"],
        Constant.MEMORY_TOP_TABLE: ["C1:E1", "F1:H1"],
        Constant.MODULE_TOP_TABLE: ["F1:I1", "J1:M1"],
        Constant.MODULE_TABLE: ["E1:H1", "I1:L1"],
        Constant.OVERALL_METRICS_TABLE: ["B1:D1", "E1:G1"],
        Constant.API_TABLE: ["C1:F1", "G1:J1"],
        Constant.KERNEL_TABLE: ["D1:H1", "I1:M1"],
        Constant.KERNEL_TYPE_TABLE: ["D1:H1", "I1:M1"],
    }

    # overall metrics index
    # computing time
    COMPUTING = "Computing Time"

    MC2_COMMUNICATION_TIME = "\t\tCommunication"
    MC2_COMPUTING_TIME = "\t\tComputing"

    FA_FWD = "\tFlash Attention (Forward)"
    FA_FWD_CUBE = "\t\tFlash Attention (Forward) (Cube)"
    FA_FWD_VECTOR = "\t\tFlash Attention (Forward) (Vector)"
    FA_BWD = "\tFlash Attention (Backward)"
    FA_BWD_CUBE = "\t\tFlash Attention (Backward) (Cube)"
    FA_BWD_VECTOR = "\t\tFlash Attention (Backward) (Vector)"

    CONV_FWD = "\tConv (Forward)"
    CONV_FWD_CUBE = "\t\tConv (Forward) (Cube)"
    CONV_FWD_VECTOR = "\t\tConv (Forward) (Vector)"
    CONV_BWD = "\tConv (Backward)"
    CONV_BWD_CUBE = "\t\tConv (Backward) (Cube)"
    CONV_BWD_VECTOR = "\t\tConv (Backward) (Vector)"

    MM = "\tMatmul"
    MM_CUBE = "\t\tMatmul (Cube)"
    MM_VECTOR = "\t\tMatmul (Vector)"

    PA = "\tPage Attention"

    VECTOR = "\tVector"
    VECTOR_TRANS = "\t\tVector (Trans)"
    VECTOR_NO_TRANS = "\t\tVector (No Trans)"

    CUBE = "\tCube"
    SDMA_TM = "\tSDMA (Tensor Move)"
    OTHER = "\tOther"

    # communication time
    COMMUNICATION_TIME = "Uncovered Communication Time"
    WAIT = "\t\tWait"
    TRANSMIT = "\t\tTransmit"
    UNCOVERED_COMM_OVERLAP = "\tUncovered Communication Overlapped"

    # free time
    FREE_TIME = "Free Time"
    SDMA = "\tSDMA"
    FREE = "\tFree"

    # e2e time
    E2E_TIME = "E2E Time"

    ROW_STYLE_MAP = {
        COMPUTING: CellFormatType.BLUE_NORMAL,
        COMMUNICATION_TIME: CellFormatType.BLUE_NORMAL,
        FREE_TIME: CellFormatType.BLUE_NORMAL,
        E2E_TIME: CellFormatType.BLUE_NORMAL,
        FA_FWD: CellFormatType.LIGHT_BLUE_NORMAL,
        FA_BWD: CellFormatType.LIGHT_BLUE_NORMAL,
        CONV_FWD: CellFormatType.LIGHT_BLUE_NORMAL,
        CONV_BWD: CellFormatType.LIGHT_BLUE_NORMAL,
        MM: CellFormatType.LIGHT_BLUE_NORMAL,
        PA: CellFormatType.LIGHT_BLUE_NORMAL,
        VECTOR: CellFormatType.LIGHT_BLUE_NORMAL,
        CUBE: CellFormatType.LIGHT_BLUE_NORMAL,
        SDMA_TM: CellFormatType.LIGHT_BLUE_NORMAL,
        OTHER: CellFormatType.LIGHT_BLUE_NORMAL,
    }
