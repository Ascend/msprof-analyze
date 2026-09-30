# -------------------------------------------------------------------------
# This file is part of the MindStudio project.
# Copyright (c) 2023 Huawei Technologies Co.,Ltd.
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
from enum import Enum


class CsvTitle:
    MODEL_NAME = "Model Name"
    MODEL_ID = "Model ID"
    TASK_ID = "Task ID"
    STREAM_ID = "Stream ID"
    INFER_ID = "Infer ID"
    TASK_START_TIME = "Task Start Time(us)"
    TASK_WAIT_TIME = "Task Wait Time(us)"
    BLOCK_DIM = "Block Dim"
    MIX_BLOCK_DIM = "Mix Block Dim"
    HF32_ELIGIBLE = "HF32 Eligible"
    INPUT_SHAPES = "Input Shapes"
    INPUT_DATA_TYPES = "Input Data Types"
    INPUT_FORMATS = "Input Formats"
    OUTPUT_SHAPES = "Output Shapes"
    OUTPUT_DATA_TYPES = "Output Data Types"
    OUTPUT_FORMATS = "Output Formats"
    CONTEXT_ID = "Context ID"
    AICORE_TIME = "aicore_time(us)"
    AIC_TOTAL_CYCLES = "aic_total_cycles"
    AIC_MAC_TIME = "aic_mac_time(us)"
    AIC_MAC_RATIO = "aic_mac_ratio"
    AIC_SCALAR_TIME = "aic_scalar_time(us)"
    AIC_SCALAR_RATIO = "aic_scalar_ratio"
    AIC_MTE1_TIME = "aic_mte1_time(us)"
    AIC_MTE1_RATIO = "aic_mte1_ratio"
    AIC_MTE2_TIME = "aic_mte2_time(us)"
    AIC_MTE2_RATIO = "aic_mte2_ratio"
    AIC_FIXPIPE_TIME = "aic_fixpipe_time(us)"
    AIC_FIXPIPE_RATIO = "aic_fixpipe_ratio"
    AIC_ICACHE_MISS_RATE = "aic_icache_miss_rate"
    AIV_TIME = "aiv_time(us)"
    AIV_TOTAL_CYCLES = "aiv_total_cycles"
    AIV_VEC_TIME = "aiv_vec_time(us)"
    AIV_VEC_RATIO = "aiv_vec_ratio"
    AIV_SCALAR_TIME = "aiv_scalar_time(us)"
    AIV_SCALAR_RATIO = "aiv_scalar_ratio"
    AIV_MTE2_TIME = "aiv_mte2_time(us)"
    AIV_MTE2_RATIO = "aiv_mte2_ratio"
    AIV_MTE3_TIME = "aiv_mte3_time(us)"
    AIV_MTE3_RATIO = "aiv_mte3_ratio"
    AIV_ICACHE_MISS_RATE = "aiv_icache_miss_rate"
    CUBE_UTILIZATION = "cube_utilization( %)"
    TASK_DURATION_SUM = "Task Duration Sum(us)"
    TASK_DURATION_MEAN = "Task Duration Mean(us)"
    TASK_DURATION_STD = "Task Duration Std(us)"
    TASK_DURATION_RATIO = "Task Duration Ratio(100%)"
    SIZE = "size(MB)"
    THROUGHPUT = "throughput(GB/s)"
    COLOR = "color"
    GAP = "Gap(us)"
    DURATION_SUM = "Duration Sum(us)"
    COUNT = "Count"
    MAX_DURATION = "Max Duration(us)"
    MIN_DURATION = "Min Duration(us)"
    AVG_DURATION = "Avg Duration(us)"
    DURATION_RATIO = "Duration Ratio"
    INDEX = "Index"


# 定义CSV_TITILE_V1类，继承自CSV_TITILE类, 适配旧版csv
class CsvTitleV1(CsvTitle):
    OP_NAME = "Op Name"
    OP_TYPE = "OP Type"
    TASK_TYPE = "Task Type"
    TASK_DURATION = "Task Duration(us)"


# 定义CSV_TITILE_V1类，继承自CSV_TITILE类, 适配新版csv
class CsvTitleV2(CsvTitle):
    OP_NAME = "Name"
    OP_TYPE = "Type"
    TASK_TYPE = "Accelerator Core"
    TASK_DURATION = "Duration(us)"


class Constant:
    DTYPE_SIZE_MAP = {
        "int8": 1,
        "uint8": 1,
        "int16": 2,
        "uint16": 2,
        "int32": 4,
        "uint32": 4,
        "int64": 8,
        "uint64": 8,
        "float16": 2,
        "bfloat16": 2,
        "bf16": 2,
        "dt_bf16": 2,
        "float32": 4,
        "float": 4,
        "float64": 8,
        "complex64": 8,
        "complex128": 16,
        "bool": 1,
    }
    TP_THRESHOLD = 1150
    MAX_INPUT_MODE_LEN = 30
    MAX_INPUT_ADVICE_LEN = 30
    SMALL_OP_DUR_RATIO = 0.2
    SMALL_OP_NUM_RATIO = 0.2
    BYTE_UNIT_TRANS = 1024
    UNIT_TRANS = 1000

    # mode list
    COMPUTE = "compute"
    TIMELINE = "timeline"
    CLUSTER = "cluster"
    OVERALL = "overall"
    PIPELINE = "pipeline"

    # advice list
    SLOW_RANK = "slow rank"
    SLOW_LINK = "slow link"
    KERNEL = "kernel"

    # compute
    NPU_FUSED = "npu_fused"
    NPU_SLOW = "npu_slow"

    # timeline
    OPTIM = "optimizer"
    OP_SCHE = "op_schedule"

    # overall
    SUMMARY = "summary"

    PT_PROF_SUFFIX = "ascend_pt"
    ASCEND_PROFILER_OUTPUT = "ASCEND_PROFILER_OUTPUT"
    COLLECTION_PATH = "collection_path"
    CLUSTER_ANALYSIS_OUTPUT = "cluster_analysis_output"
    KERNEL_DETAILS_CSV = "kernel_details.csv"
    CLUSTER_STEP_TIME_CSV = "cluster_step_trace_time.csv"
    CLUSTER_COMM_JSON = "cluster_communication.json"

    # pipline
    OP_NAME = "name"
    OP_TID = "tid"
    PID = "pid"
    TS = "ts"
    DUR = "dur"
    CAT = "cat"
    ARGS = "args"
    PH = "ph"
    ID = "id"
    PH_START = "s"
    PH_BEGIN = "B"
    PH_END = "E"
    PH_META = "M"
    PH_X = "X"
    CNAME = "cname"
    PROCESS_NAME = "process_name"
    FRAMEWORK_NAME = "Python"
    ASCEND_HARDWARE_NAME = "Ascend Hardware"
    ASYNC_NPU = "async_npu"
    STEP_PREFIX = "ProfilerStep#"
    FP_ATEN_OP = "aten"
    FP_C10D_OP = "c10d"
    HCOM_OP_PREFIX = "hcom_"
    BP_AUTOGRAD_OP = "autograd"
    TRACE_VIEW_JSON = "trace_view.json"

    # pattern_dict key: pattern, value: pattern name
    PATTERN_DICT = {
        ("Add", "DropOutDoMask", "Add"): "bias_dropout_add",
        (
            "BatchMatMul",
            "Mul",
            "Cast",
            "Mul",
            "MaskedFill",
            "SoftmaxV2",
            "Cast",
            "DropOutDoMask",
            "AsStrided",
            "BatchMatMul",
            "Transpose",
        ): "FA",
        (
            "Transpose",
            "Transpose",
            "Transpose",
            "Mul",
            "Transpose",
            "BatchMatMulV2",
            "MaskedFill",
            "Cast",
            "SoftmaxV2",
            "Cast",
            "DropOutDoMask",
            "BatchMatMulV2",
            "Transpose",
        ): "FA",
        (
            "Transpose",
            "BatchMatMulV2",
            "Transpose",
            "Transpose",
            "BatchMatMulV2",
            "ZerosLike",
            "DropOutDoMask",
            "Cast",
            "SoftmaxGrad",
            "Cast",
            "MaskedFill",
            "BatchMatMulV2",
            "BatchMatMulV2",
            "Mul",
        ): "FA",
        (
            "Cast",
            "Square",
            "ReduceMeanD",
            "Add",
            "Rsqrt",
            "Cast",
            "Cast",
            "Mul",
            "Cast",
            "Cast",
            "Mul",
            "Cast",
        ): "RMSNORM",
        ("Cast", "LayerNorm", "Cast"): "LayerNorm",
        ("Add", "LayerNorm"): "AddLayerNorm",
        ("Add", "LayerNormV3"): "AddLayerNorm",
        ("Gelu", "Add"): "GeluAdd",
        ("Cast", "Square", "MemSet", "ReduceMean", "Add", "Rsqrt", "Mul", "Cast", "Mul"): "RMSNorm",
        ("BatchMatMul", "RealDiv", "Add", "Maximum", "SoftmaxV2", "Cast", "BatchMatMul"): "FA",
        ("BatchMatMulV2", "RealDiv", "Add", "Cast", "Maximum", "Cast", "SoftmaxV2", "AsStrided", "BatchMatMulV2"): "FA",
        ("BatchMatMulV2", "RealDiv", "Add", "Cast", "SoftmaxV2", "Cast", "BroadcastTo", "BatchMatMulV2"): "FA",
        ("Mul", "Slice", "Neg", "Slice", "ConcatD", "Cast", "Mul", "Add"): "RotaryMul",
        ("Mul", "AsStrided", "Neg", "AsStrided", "ConcatD", "Mul", "Add"): "RotaryMul",
        ("Mul", "Slice", "Neg", "Slice", "ConcatD", "Mul", "Add"): "RotaryMul",
        ("MatMulV2", "Swish", "MatMulV2", "Mul", "MatMulV2"): "FFN",
        ("Transpose", "Transpose", "GatherElement", "Transpose"): "GatherElement",
        ("Slice", "Slice", "Swish", "Mul"): "torch_npu.npu_swiglu",
        ("Cast", "Mul", "MaskedFill", "SoftmaxV2", "Cast"): "torch_npu.npu_scaled_masked_softmax",
        ("Mul", "Slice", "Neg", "Slice", "ConcatD", "Mul"): "torch_npu.npu_rotary_mul",
        ("Cast", "Square", "ReduceMeanD", "Add", "Rsqrt", "Mul", "Cast", "Mul"): "torch_npu.npu_rms_norm",
    }
    TITLE = CsvTitleV2

    @classmethod
    def update_title(cls):
        cls.TITLE = CsvTitleV1


class CoreType:
    AIV = "AI_VECTOR_CORE"
    AIC = "AI_CORE"
    AICPU = "AI_CPU"
    MIX_AIV = "MIX_AIV"
    MIX_AIC = "MIX_AIC"
    HCCL = "COMMUNICATION"


class PerfColor(Enum):
    WHITE = 0
    GREEN = 1
    YELLOW = 2
    RED = 3
