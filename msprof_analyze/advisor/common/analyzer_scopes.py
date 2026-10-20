# -------------------------------------------------------------------------
# This file is part of the MindStudio project.
# Copyright (c) 2026 Huawei Technologies Co.,Ltd.
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
