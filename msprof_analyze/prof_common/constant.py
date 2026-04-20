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
import os
import stat


class Constant(object):
    COLLECTION_PATH = "collection_path"
    ANALYSIS_MODE = "analysis_mode"
    MODE = "mode"
    CONTEXT_SETTINGS = dict(help_option_names=['-H', '-h', '--help'])

    MAX_FILE_SIZE_5_GB = 1024 * 1024 * 1024 * 5

    MODULE_EVENT = "module_event"
    CPU_OP_EVENT = "op_event"
    STEP_EVENT = "step_event"
    TORCH_TO_NPU_FLOW = "torch_to_device"
    KERNEL_EVENT = "kernel_event"
    HCCL_EVENT = "hccl_event"
    OVERLAP_ANALYSIS_EVENT = "overlap_event"
    FWD_BWD_FLOW = "fwd_to_bwd"
    NPU_ROOT_ID = "NPU"
    BACKWARD_MODULE = "nn.Module: BACKWARD"

    FWD_OR_OPT = 0
    BACKWARD = 1
    INVALID_RETURN = -1

    # dir name
    FRAMEWORK_DIR = "FRAMEWORK"
    CLUSTER_ANALYSIS_OUTPUT = "cluster_analysis_output"
    SINGLE_OUTPUT = "ASCEND_PROFILER_OUTPUT"
    ANALYZE_DIR = "analyze"
    COMM_JSON = "communication.json"
    COMM_MATRIX_JSON = "communication_matrix.json"
    STEP_TIME_CSV = "step_trace_time.csv"
    KERNEL_DETAILS_CSV = "kernel_details.csv"

    # file authority
    FILE_AUTHORITY = 0o640
    DIR_AUTHORITY = 0o750
    MAX_JSON_SIZE = 1024 * 1024 * 1024 * 10
    MAX_CSV_SIZE = 1024 * 1024 * 1024 * 5
    MAX_COMMON_SIZE = 1024 * 1024 * 1024
    MAX_TRACE_SIZE = 1024 * 1024 * 1024 * 5
    MAX_PATH_LENGTH = 4096
    MAX_READ_DB_FILE_BYTES = 1024 * 1024 * 1024 * 20

    # communication
    P2P = "p2p"
    COLLECTIVE = "collective"
    TOTAL = "total"
    STEP_ID = "step_id"
    RANK_ID = "rank_id"
    GROUP_NAME = "group_name"
    COMM_OP_TYPE = "comm_op_type"
    COMM_OP_NAME = "comm_op_name"
    COMM_OP_INFO = "comm_op_info"
    TOTAL_OP_INFO = "Total Op Info"
    COMMUNICATION_TIME_INFO = "Communication Time Info"
    START_TIMESTAMP = "Start Timestamp(us)"
    COMMUNICATION_BANDWIDTH_INFO = "Communication Bandwidth Info"
    HCOM_SEND = "hcom_send"
    HCOM_RECEIVE = "hcom_receive"
    SYNCHRONIZATION_TIME_RATIO = "Synchronization Time Ratio"
    SYNCHRONIZATION_TIME_MS = "Synchronization Time(ms)"
    WAIT_TIME_RATIO = "Wait Time Ratio"
    TRANSIT_TIME_MS = "Transit Time(ms)"
    TRANSIT_SIZE_MB = "Transit Size(MB)"
    SIZE_DISTRIBUTION = "Size Distribution"
    WAIT_TIME_MS = "Wait Time(ms)"
    OP_NAME = "Op Name"
    BANDWIDTH_GB_S = "Bandwidth(GB/s)"
    COMMUNICATION = "communication.json"
    ELAPSE_TIME_MS = "Elapse Time(ms)"
    IDLE_TIME_MS = "Idle Time(ms)"
    LARGE_PACKET_RATIO = "Large Packet Ratio"
    TYPE = "type"

    # params
    DATA_MAP = "data_map"
    P2P_GROUP = "p2p_group"
    COLLECTIVE_GROUP = "collective_group"
    COMMUNICATION_OPS = "communication_ops"
    MATRIX_OPS = "matrix_ops"
    CLUSTER_ANALYSIS_OUTPUT_PATH = "output_path"
    COMMUNICATION_GROUP = "communication_group"
    TRANSPORT_TYPE = "Transport Type"
    COMM_DATA_DICT = "comm_data_dict"
    DATA_TYPE = "data_type"
    IS_MSPROF = "is_prof"
    IS_MINDSPORE = "is_mindspore"

    # step time
    RANK = "rank"
    STAGE = "stage"

    # epsilon
    EPS = 1e-15

    # file suffix
    JSON_SUFFIX = ".json"
    CSV_SUFFIX = ".csv"

    # result files type
    TEXT = "text"
    DB = "db"
    NOTEBOOK = "notebook"
    EXCEL = "excel"
    CSV = "csv"
    INVALID = "invalid"

    # db name
    DB_COMMUNICATION_ANALYZER = "analysis.db"
    DB_CLUSTER_COMMUNICATION_ANALYZER = "cluster_analysis.db"
    DB_MS_COMMUNICATION_ANALYZER = "communication_analyzer.db"

    # db tables
    TABLE_COMMUNICATION_GROUP = "CommunicationGroup"
    TABLE_COMM_ANALYZER_BANDWIDTH = "CommAnalyzerBandwidth"
    TABLE_COMM_ANALYZER_TIME = "CommAnalyzerTime"
    TABLE_COMM_ANALYZER_MATRIX = "CommAnalyzerMatrix"
    TABLE_STEP_TRACE = "StepTraceTime"
    TABLE_HOST_INFO = "HostInfo"
    TABLE_RANK_DEVICE_MAP = "RankDeviceMap"
    TABLE_CLUSTER_BASE_INFO = "ClusterBaseInfo"
    TABLE_META_DATA = "META_DATA"
    TABLE_COMMUNICATION_GROUP_MAPPING = "CommunicationGroupMapping"
    TABLE_CLUSTER_COMMUNICATION_MATRIX = "ClusterCommAnalyzerMatrix"
    TABLE_CLUSTER_COMMUNICATION_BANDWIDTH = "ClusterCommAnalyzerBandwidth"
    TABLE_CLUSTER_COMMUNICATION_TIME = "ClusterCommunicationTime"
    TABLE_CLUSTER_TIME_SUMMARY = "ClusterTimeSummary"

    # data config key
    CONFIG = "config"
    EXPER_CONFIG = "experimental_config"
    EXPER_EXPORT_TYPE = "_export_type"
    PROFILER_PARAMETER = "profiler_parameters"

    # metadata key
    DISTRIBUTED_ARGS = "distributed_args"
    PARALLEL_GROUP_INFO = "parallel_group_info"

    # mode
    ALL = "all"
    COMMUNICATION_TIME = "communication_time"
    COMMUNICATION_MATRIX = "communication_matrix"

    STEP = "step"

    DATA_SIMPLIFICATION = "data_simplification"
    FORCE = "force"

    # compare tools

    GPU = "GPU"
    NPU = "NPU"
    NA = 'N/A'
    LIMIT_KERNEL = 3
    MAX_FLOW_CAT_LEN = 20
    MAX_OP_NAME_LEN = 200
    MAX_FILE_SIZE = 1024 * 1024 * 1024 * 5
    BYTE_TO_KB = 1024
    YELLOW_COLOR = "FFFF00"
    GREEN_COLOR = "00FF00"
    RED_COLOR = "FF0000"
    BLUE_COLOR = "00BFFF"
    LIGHT_BLUE_COLOR = "87CEFA"
    US_TO_MS = 1000
    NS_TO_US = 1000
    KB_TO_MB = 1024
    INVALID_VALUE = -1
    MILLISECONDS_TO_SECONDS = 10 ** 3
    MICROSECONDS_TO_SECONDS = 10 ** 6
    MILLISECONDS_TO_MICROSECONDS = 10 ** 3

    PROFILING_TYPE = "profiling type"

    # path
    PROFILING_PATH = "profiling_path"
    TRACE_PATH = "trace_path"
    MEMORY_DATA_PATH = "memory_data_path"
    ASCEND_OUTPUT_PATH = "ascend_output"
    INFO_JSON_PATH = "info_path"

    # excel headers
    BASE_PROFILING = 'Base Profiling: '
    COMPARISON_PROFILING = 'Comparison Profiling: '
    WAIT_TIME = "wait"
    TRANSMIT_TIME = "transmit"

    # compare type
    OPERATOR_COMPARE = "OperatorCompare"
    MEMORY_COMPARE = "MemoryCompare"
    API_COMPARE = "ApiCompare"
    KERNEL_COMPARE = "KernelCompare"
    KERNEL_TYPE_COMPARE = "KernelTypeCompare"

    # sheet name
    OPERATOR_SHEET = "OperatorCompare"
    MEMORY_SHEET = "MemoryCompare"
    OPERATOR_TOP_SHEET = "OperatorCompareStatistic"
    MEMORY_TOP_SHEET = "MemoryCompareStatistic"
    COMMUNICATION_SHEET = "CommunicationCompare"
    API_SHEET = "ApiCompare"
    KERNEL_SHEET = "KernelCompare"

    # table name
    OPERATOR_TABLE = "OperatorCompare"
    MEMORY_TABLE = "MemoryCompare"
    OPERATOR_TOP_TABLE = "OperatorCompareStatistic"
    MEMORY_TOP_TABLE = "MemoryCompareStatistic"
    COMMUNICATION_TABLE = "CommunicationCompare"
    PERFORMANCE_TABLE = "Model Profiling Time Distribution"
    MODULE_TABLE = "ModuleCompare"
    MODULE_TOP_TABLE = "ModuleCompareStatistic"
    OVERALL_METRICS_TABLE = "OverallMetrics"
    API_TABLE = "ApiCompare"
    KERNEL_TABLE = "KernelCompare"
    KERNEL_TYPE_TABLE = "KernelTypeCompare"

    # memory
    SIZE = "Size(KB)"
    TS = "ts"
    ALLOCATION_TIME = "Allocation Time(us)"
    RELEASE_TIME = "Release Time(us)"
    NAME = "Name"

    OP_KEY = "op_name"
    DEVICE_DUR = "dur"

    BASE_DATA = "base_data"
    COMPARISON_DATA = "comparison_data"
    OVERALL_METRICS = "overall_metrics"
    TORCH_OP = "torch_op"
    KERNEL_DICT = "kernel_dict"
    MEMORY_LIST = "memory_list"
    COMMUNICATION_DICT = "comm_dict"

    # compare type
    OVERALL_COMPARE = "overall"

    BWD_LIST = ["bwd", "backward", "back", "grad"]

    CPU_OP_FA_MASK = (
        "flash_attention", "fusion_attention", "flashattn", "xformers_flash", "efficient_attention", "flash2attn"
    )
    CPU_OP_CONV = "aten::conv"
    CPU_OP_MATMUL_MASK = ("aten::addmm", "aten::bmm", "aten::mm", "aten::matmul")
    KERNEL_CUBE_MASK = ("gemm", "conv", "cutlass", "wgrad", "gemvx")
    KERNEL_TRANS_MASK = ("cast", "transdata", "transpose")

    IS_BWD = "is_bwd"
    OPS = "ops"

    VOID_STEP = -1

    # advisor

    # timeline
    DEQUEUE = "Dequeue"
    DEQUEUE_SEP = "@"
    ATEN = "aten"
    NPU_LOWER = "npu"
    ATEN_SEP = "::"
    OPTIMIZER = "Optimizer"
    OPTIMIZER_SEP = "#"
    OPTIMIZER_STEP = "step"
    ENQUEUE = "enqueue"
    TORCH_TO_NPU = "torch_to_npu"
    FREE = "free"
    OP_COMPILE_NAME = "AscendCL@aclopCompileAndExecute"
    OP_COMPILE_ID = "aclopCompileAndExecute"
    SYNC_STREAM = "AscendCL@aclrtSynchronizeStream"
    NODE_LAUNCH = "Node@launch"
    MAX_OP_COMPILE_NUM = 20
    ACL_TO_NPU = "acl_to_npu"
    TASK_TYPE = "Task Type"
    CPU_OP = "cpu_op"
    AI_CORE = "AI_CORE"
    AI_CPU = "AI_CPU"
    MIX_AIC = "MIX_AIC"
    CALL_STACKS = "Call stack"
    INPUT_DIMS = "Input Dims"
    OP_SEP = "-"
    ADVISOR_MAX_PROCESSES = 8
    ADVISOR_ANALYZE_PROCESSES = "ADVISOR_ANALYZE_PROCESSES"
    TIMELINE_OP_STACKS_DATASET = "timeline_op_stacks_dataset"
    TIMELINE_BACKWARD_NO_STACK = "Backward broadcast, without call stacks in profiling."
    TIMELINE_ACL_TO_NPU_NO_STACK = "Incoming flow is 'acl_to_npu', without call stacks in profiling."
    TIMELINE_BACKWARD_NO_STACK_CODE = -1
    TIMELINE_ACL_TO_NPU_NO_STACK_CODE = -2
    TIMELINE_FUSION_OPS_NO_STACK_FLAG = "NO STACK"
    NO_STACK_REASON_MAP = {
        TIMELINE_BACKWARD_NO_STACK_CODE: "Backward broadcast, without call stacks in profiling.",
        TIMELINE_ACL_TO_NPU_NO_STACK_CODE: "Incoming flow is 'acl_to_npu', without call stacks in profiling."
    }
    AFFINITY_TRAINING_API = "Affinity training api"
    TIMELINE_EMPTY_STACKS_PROMPT = "These APIs have no code stack. If parameter 'with_stack=False' while profiling, " \
                                   "please refer to {timeline_profiling_doc_url} to set 'with_stack=True'. " \
                                   "Otherwise, ignore following affinity APIs due to backward broadcast lack of stack."

    CLUSTER_ANALYSIS = "Cluster analysis"
    SLOW_RANK_TIME_RATIO_THRESHOLD = 0.05

    CANN_VERSION = "cann_version"
    TORCH_VERSION = "torch_version"
    PROFILING_TYPE_UNDER_LINE = "profiling_type"
    ANALYSIS_DIMENSIONS = "analysis_dimensions"

    PROFILER_METADATA = "profiler_metadata.json"

    TERMINAL_OUTPUT_HEADERS = ["No.", "Problem", "Description", "Suggestion"]
    SKIP_ANALYZE_PROMPT = "Finish analysis, no optimization suggestions"
    SKIP_QUERY_PROMPT = "Finish query operator stack, no operators"

    # operator output constant
    OPERATOR_OUT_TOPK = 10
    OPERATOR_LIST_UNLIMIT = -1

    DEFAULT_OPERATOR_TYPE = 'None_type'
    DEFAULT_DURATION_ZERO = 0.0

    ADVISOR_LOG_LEVEL = "ADVISOR_LOG_LEVEL"
    DEFAULT_LOG_LEVEL = "INFO"
    MSPROF_ANALYZE_LOG_LEVEL = "MSPROF_ANALYZE_LOG_LEVEL"
    SUPPORTED_LOG_LEVEL = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]

    RULE_BUCKET = "RULE-BUCKET"
    CLOUD_RULE_REGION_CN_NORTH_9 = "cn-north-9"
    CLOUD_RULE_REGION_CN_NORTH_7 = "cn-north-7"
    CLOUD_RULE_REGION_CN_SOUTHWEST_2 = "cn-southwest-2"
    CLOUD_RULE_REGION_LIST = [CLOUD_RULE_REGION_CN_NORTH_7, CLOUD_RULE_REGION_CN_NORTH_9,
                              CLOUD_RULE_REGION_CN_SOUTHWEST_2]
    INNER_REGION_LIST = [CLOUD_RULE_REGION_CN_NORTH_7]
    DEFAULT_CLOUD_RULE_REGION = CLOUD_RULE_REGION_CN_SOUTHWEST_2

    HTTP_PREFIXES = "http://"
    HTTPS_PREFIXES = "https://"
    COMMON_YAML_DIR = "modelarts/solution/ma_advisor_rules/"
    COMMON_ENDPOINT_SUFFIX = "obs.{}.myhuaweicloud.com"
    INNER_ENDPOINT_SUFFIX = "obs.{}.ulanqab.huawei.com"

    AICPU_RULES_YAML_NAME = "aicpu_rules.yaml"
    FUSION_PASS_YAML_NAME = "op_fusion_pass.yaml"
    TIMELINE_FUSION_OPS_YAML_NAME = "timeline_fusion_ops.yaml"
    CLOUD_YAML_NAME_LIST = [AICPU_RULES_YAML_NAME, FUSION_PASS_YAML_NAME, TIMELINE_FUSION_OPS_YAML_NAME]

    MAX_RETRIES = 3
    TIMEOUT = 3
    DEPTH_LIMIT = 20

    ADVISOR_RULE_PATH = "ADVISOR_RULE_PATH"
    CLOUD_RULE_PATH = "rules/cloud/"
    DEFAULT_RULE_PATH = "./rules/"

    TIMELINE_FUSION_OPS_INVALID_UNIQUE_ID = -1

    DEFAULT_TEMPLATE_HEADER = "Performance Optimization Suggestions"

    PT_PROF_SUFFIX = "ascend_pt"
    ASCEND_PROFILER_OUTPUT = "ASCEND_PROFILER_OUTPUT"
    CLUSTER_STEP_TIME_CSV = "cluster_step_trace_time.csv"
    CLUSTER_COMM_JSON = "cluster_communication.json"
    COMMUNICATION_JSON = "communication.json"

    BOTTLENECK = "bottleneck"
    DATA = "data"
    ADVISOR_ANALYSIS_OUTPUT_DIR = "advisor_analysis_result"
    DEFAULT_PROCESSES = 8
    CLUSTER_ANALYSIS_FILE_PATTERN = [
        r'profiler_info_\d+\.json', "step_trace_time.csv", "communication.json", "communication_matrix.json"
    ]
    ANALYSIS_OUTPUT_PATH = "ANALYSIS_OUTPUT_PATH"
    DEFAULT_RANK_FOR_PROFILING_ANALYSIS = 0
    PROFILER_INFO_FILE_PATTERN = r"profiler_info_(\d+)\.json"
    DISABLE_STREAMINIG_READER = "DISABLE_STREAMINIG_READER"
    FRAMEWORK_STACK_BLACK_LIST = ["torch", "torch_npu", "megatron", "deepspeed"]
    DISABLE_STREAMING_READER = "DISABLE_STREAMING_READER"
    MAX_NUM_PROCESSES = 4
    DEFAULT_STEP = "-1"
    STEP_RANK_SEP = "_"

    MAX_READ_LINE_BYTES = 8196 * 1024
    MAX_READ_FILE_BYTES = 64 * 1024 * 1024 * 1024

    # Unit Conversion
    COMMUNICATION_B_TO_GB = 0.001 ** 3
    US_TO_S = 0.001 ** 2
    TIME_UNIT_SCALE = 1000

    WRITE_MODES = stat.S_IWUSR | stat.S_IRUSR | stat.S_IRGRP
    WRITE_FLAGS = os.O_WRONLY | os.O_CREAT | os.O_TRUNC

    DISABLE_PROFILING_COMPARISON = "DISABLE_PROFILING_COMPARISON"
    FREE_DURATION_FOR_GC_ANALYSIS = "FREE_DURATION_FOR_GC_ANALYSIS"
    DISABLE_AFFINITY_API = "DISABLE_AFFINITY_API"

    MINDSPORE_VERSION = "mindspore_version"
    PYTORCH = "pytorch"
    MINDSPORE = "mindspore"
    MSPROF = "msprof"
    MSMONITOR = "msmonitor"

    # node type
    MODULE_TYPE = 0
    OPERATOR_TYPE = 1
    VIRTUAL_TYPE = 9

    # json trace bar
    NPU_BAR = "Ascend Hardware"
    COMM_BAR = "Communication"
    OVERLAP_BAR = "Overlap Analysis"

    # overlap_analysis event
    COMPUTING_EVENT = "Computing"
    FREE_EVENT = "Free"
    UNCOVERED_COMMUNICATION_EVENT = "Communication(Not Overlapped)"

    MC2_TIME = "mc2"
    MC2_COMPUTING = "mc2_p"
    MC2_COMMUNICATION = "mc2_m"
    MC2_NUMBER = "mc2_num"

    # recipe config
    ANALYSIS = "analysis"
    RECIPE_NAME = "recipe_name"
    RECIPE_CLASS = "recipe_class"
    PARALLEL_MODE = "parallel_mode"
    MSPROF_ANALYZE_PATH = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))
    RECIPES_PATH = os.path.join(MSPROF_ANALYZE_PATH, 'cluster_analyse', 'recipes')

    CONCURRENT_MODE = "concurrent"
    PROFILER_DB_PATH = "profiler_db_path"
    ANALYSIS_DB_PATH = "analysis_db_path"
    RANK_LIST = "rank_list"
    EXPORT_TYPE = "export_type"
    EXTRA_ARGS = "args"
    STEP_RANGE = "step_range"
    START_NS = "startNs"
    END_NS = "endNs"


    # hccl_sum
    UINT32_BITS = 32
    UINT32_MASK = 0xffffffff

    INVALID_RANK_NUM = 4294967295
    MAX_INTEGER = 9223372036854775807  # Default MAX value: 2^63 - 1 for 64-bit integer

    # slow rank
    MAX_DIXON_NUM = 100
    DIXON_THRESHOLD_1 = 7
    DIXON_THRESHOLD_2 = 10
    DIXON_THRESHOLD_3 = 13

    UNKNOWN = "unknown"

    SQL_PLACEHOLDER_PATTERN = r"\?|\%s"

    # cluster_analysis_output
    COMMUNICATION_GROUP_JSON = "communication_group.json"
    CLUSTER_COMMUNICATION_MATRIX_JSON = "cluster_communication_matrix.json"
    KEY_COMM_GROUP_PARALLEL_INFO = "comm_group_parallel_info"

    TABLE_PYTORCH_API = "PYTORCH_API"
    TABLE_CANN_API = "CANN_API"
    TABLE_AICORE_FREQ = "AICORE_FREQ"
    TABLE_STRING_IDS = "STRING_IDS"
    TABLE_ENUM_API_TYPE = "ENUM_API_TYPE"
    TABLE_GC_RECORD = "GC_RECORD"
    TABLE_COMPUTE_TASK_INFO = "COMPUTE_TASK_INFO"
    TABLE_COMMUNICATION_OP = "COMMUNICATION_OP"
    TABLE_COMMUNICATION_TASK_INFO = "COMMUNICATION_TASK_INFO"
    TABLE_TASK = "TASK"
    TABLE_PYTORCH_CALLCHAINS = "PYTORCH_CALLCHAINS"
    TABLE_COMMUNICATION_SCHEDULE_TASK_INFO = "COMMUNICATION_SCHEDULE_TASK_INFO"
    TABLE_TASK_PMU_INFO = "TASK_PMU_INFO"
    TABLE_OP_MEMORY = "OP_MEMORY"
    TABLE_MEMORY_RECORD = "MEMORY_RECORD"
    TABLE_STEP_TIME = "STEP_TIME"
    TABLE_COMPUTATIONAL_OPERATOR_MASKING_LINEARITY = "ComputationalOperatorMaskingLinearity"

    # communication task type
    NOTIFY_RECORD = "Notify_Record"
    NOTIFY_WAIT = "Notify_Wait"

    # group name value
    PP = "pp"

    # --force log
    FORCE_BYPASSES_SECURITY = "You can add the '--force' parameter and retry. " \
                              "This parameter will skip verification of the owner, size, and permissions."

    NA = "N/A"


class ProfilerTableConstant:

    # COMMUNICATION OP
    OP_ID = "opId"
    OP_NAME = "opName"
    START_NS = "startNS"
    END_NS = "endNS"
    CONNECTION_ID = "connectionId"
    GROUP_NAME = "groupName"
    RELAY = "relay"
    RETRY = "retry"
    DATA_TYPE = "dataType"
    ALG_TYPE = "algType"
    COUNT = "count"
    OP_TYPE = "opType"
    WAIT_NS = "waitNS"