# Copyright (c) Huawei Technologies Co., Ltd. 2024-2025. All rights reserved.
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
class SupportedScopes:

    # used for specify fourth-level commands and define the key of the result dict
    # the key defined bellow must be the same as value
    TIMELINE_FUSION_OPS = "timeline_fusion_ops"
    GRAPH = "graph"
    SLOW_RANK = "slow_rank"
    SLOW_LINK = "slow_link"
    COMMUNICATION_RETRANSMISSION_DETECTION = "communication_retransmission_analysis"
    PACKET = "packet_analysis"
    BANDWIDTH_CONTENTION_DETECTION = "bandwidth_contention_analysis"
    BYTE_ALIGNMENT_DETECTION = "byte_alignment_analysis"
    OVER_ALL = "over_all"
    ENVIRONMENT_VARIABLE_ANALYSIS = "environment_variable_analysis"
    DYNAMIC_SHAPE_ANALYSIS = "dynamic_shape_analysis"
    AICPU_ANALYSIS = "aicpu_analysis"
    BLOCK_DIM_ANALYSIS = "block_dim_analysis"
    OPERATOR_NO_BOUND_ANALYSIS = "operator_no_bound_analysis"
    TIMELINE_OP_DISPATCH = "timeline_op_dispatch"
    DATALOADER = "dataloader"
    SYNCBN = "syncbn"
    SYNCHRONIZE_STREAM = "synchronize_stream"
    FREQ_ANALYSIS = "freq_analysis"
    MEMORY = "memory"
    STAGE_COMPUTE = "stage_compute"
    GC_ANALYSIS = "gc_analysis"
    FUSIBLE_OPERATOR_ANALYSIS = "fusible_operator_analysis"
    CONJECTURED_GC_ANALYSIS = "conjectured_analysis"
    COMPARISON = "comparison"
    AICORE_PERFORMANCE_ANALYSIS = "ai_core_performance_analysis"
    VECTOR_BOTTLENECK_ANALYSIS = "vector_bottleneck_analysis"