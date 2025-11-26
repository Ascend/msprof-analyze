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
import os
from collections import OrderedDict
import logging

from msprof_analyze.advisor.utils.utils import Timer
from msprof_analyze.advisor.result.result import OptimizeResult
from msprof_analyze.advisor.analyzer.computation.profiling_analyzer import AicpuAnalyzer, BlockDimAnalyzer, \
    DynamicShapeAnalyzer, OperatorBoundAnalyzer
from msprof_analyze.advisor.analyzer.schedule.fusion_ops.fusion_ops_analyzer import TimelineFusionOpsAnalyzer
from msprof_analyze.advisor.analyzer.graph_fusion.graph_fusion_analyzer import FusionOPAnalyzer
from msprof_analyze.advisor.common.analyzer_scopes import SupportedScopes
from msprof_analyze.advisor.analyzer.cluster.slow_rank_analyzer import SlowRankAnalyzer
from msprof_analyze.advisor.analyzer.cluster.slow_link_analyzer import SlowLinkAnalyzer
from msprof_analyze.advisor.analyzer.communication.retransmission.communication_retransmission_analyzer import \
    RDMARetransmissionAnalyzer
from msprof_analyze.advisor.analyzer.overall.overall_summary_analyzer import OverallSummaryAnalyzer
from msprof_analyze.advisor.analyzer.overall.environment_variable_analyzer import EnvironmentVariableAnalyzer
from msprof_analyze.advisor.analyzer.schedule.dispatch.timeline_op_dispatch_analyzer import OpDispatchAnalyzer
from msprof_analyze.advisor.analyzer.schedule.syncbn.syncbn_analyzer import SyncBNAnalyzer
from msprof_analyze.advisor.analyzer.schedule.synchronize_stream.synchronize_stream_analyzer import \
    SynchronizeStreamAnalyzer
from msprof_analyze.advisor.analyzer.dataloader.dataloader_analyzer import DataloaderAnalyzer
from msprof_analyze.advisor.analyzer.computation.ai_core_freq.ai_core_freq_analyzer import AICoreFreqAnalyzer
from msprof_analyze.advisor.analyzer.memory.memory_analyzer import MemoryAnalyzer
from msprof_analyze.advisor.analyzer.communication.packet.packet_analyzer import PacketAnalyzer
from msprof_analyze.advisor.analyzer.communication.contention.bandwidth_contention_analyzer import \
    BandwidthContentionAnalyzer
from msprof_analyze.advisor.analyzer.communication.alignment.byte_alignment_analyzer import ByteAlignmentAnalyzer
from msprof_analyze.advisor.analyzer.schedule.gc.gc_analyzer import GcAnalyzer
from msprof_analyze.advisor.analyzer.schedule.conjectured_gc.conjectured_gc_analyzer import ConjecturedGcAnalyzer
from msprof_analyze.advisor.analyzer.comparison.comparison_analyzer import ComparisonAnalyzer
from msprof_analyze.advisor.analyzer.schedule.fusible_ops.fusible_operator_analyzer import FusibleOperatorAnalyzer
from msprof_analyze.advisor.analyzer.computation.ai_core_performance.ai_core_performance_analyzer import \
    AICorePerformanceAnalyzer
from msprof_analyze.advisor.analyzer.computation.vector_bottleneck_operator.vector_bottleneck_op_analyzer import \
    VectorBottleneckOPAnalyzer

logger = logging.getLogger()


class Interface:
    SCHEDULE = "schedule"
    COMPUTATION = "computation"
    COMMUNICATION = "communication"
    OVERALL = "overall"
    CLUSTER = "cluster"
    MEMORY = "memory"
    COMPARISON = "comparison"

    supported_analyzer = {
        SCHEDULE: OrderedDict({
            SupportedScopes.SYNCBN: SyncBNAnalyzer,
            SupportedScopes.TIMELINE_OP_DISPATCH: OpDispatchAnalyzer,
            SupportedScopes.SYNCHRONIZE_STREAM: SynchronizeStreamAnalyzer,
            SupportedScopes.TIMELINE_FUSION_OPS: TimelineFusionOpsAnalyzer,
            SupportedScopes.DATALOADER: DataloaderAnalyzer,
            SupportedScopes.CONJECTURED_GC_ANALYSIS: ConjecturedGcAnalyzer,
            SupportedScopes.GC_ANALYSIS: GcAnalyzer,
            SupportedScopes.FUSIBLE_OPERATOR_ANALYSIS: FusibleOperatorAnalyzer
        }),
        COMPUTATION: OrderedDict({
            SupportedScopes.DYNAMIC_SHAPE_ANALYSIS: DynamicShapeAnalyzer,
            SupportedScopes.AICPU_ANALYSIS: AicpuAnalyzer,
            SupportedScopes.OPERATOR_NO_BOUND_ANALYSIS: OperatorBoundAnalyzer,
            SupportedScopes.BLOCK_DIM_ANALYSIS: BlockDimAnalyzer,
            SupportedScopes.GRAPH: FusionOPAnalyzer,
            SupportedScopes.FREQ_ANALYSIS: AICoreFreqAnalyzer,
            SupportedScopes.AICORE_PERFORMANCE_ANALYSIS: AICorePerformanceAnalyzer,
            SupportedScopes.VECTOR_BOTTLENECK_ANALYSIS: VectorBottleneckOPAnalyzer
        }),
        COMMUNICATION: OrderedDict({SupportedScopes.PACKET: PacketAnalyzer,
                                    SupportedScopes.COMMUNICATION_RETRANSMISSION_DETECTION: RDMARetransmissionAnalyzer,
                                    SupportedScopes.BANDWIDTH_CONTENTION_DETECTION: BandwidthContentionAnalyzer,
                                    SupportedScopes.BYTE_ALIGNMENT_DETECTION: ByteAlignmentAnalyzer}),
        OVERALL: OrderedDict({SupportedScopes.OVER_ALL: OverallSummaryAnalyzer,
                              SupportedScopes.ENVIRONMENT_VARIABLE_ANALYSIS: EnvironmentVariableAnalyzer}),
        CLUSTER: OrderedDict({
            SupportedScopes.SLOW_RANK: SlowRankAnalyzer,
            SupportedScopes.SLOW_LINK: SlowLinkAnalyzer
        }),
        MEMORY: OrderedDict({SupportedScopes.MEMORY: MemoryAnalyzer}),
        COMPARISON: OrderedDict({SupportedScopes.COMPARISON: ComparisonAnalyzer})
    }

    all_dimension = list(supported_analyzer.keys())

    def __init__(self, **kwargs):
        self.collection_path = os.path.abspath(kwargs.get("profiling_path"))

    @staticmethod
    def get_scope(dimension):
        return list(Interface.supported_analyzer.get(dimension).keys())

    @staticmethod
    def get_analyzer(dimension, scope):
        return Interface.supported_analyzer.get(dimension).get(scope)

    @staticmethod
    def add_analyzer(dimension, scope, analyzer_class):
        if dimension not in Interface.supported_analyzer:
            Interface.supported_analyzer[dimension] = OrderedDict()
        Interface.supported_analyzer[dimension][scope] = analyzer_class

    def get_result(self: any, dimension: str, scope: str, render_html=False, output_dict=True, **kwargs):
        """
        :Param mode: affinity apis, ai cpu and so on.
        """
        if dimension not in self.all_dimension:
            raise ValueError(f"Error dimension {dimension}, supported dimensions are {self.all_dimension}")

        supported_scopes = self.get_scope(dimension)
        if scope not in supported_scopes:
            raise ValueError(f"Error scope {scope}, supported scopes are {supported_scopes}")

        try:
            analyzer = self.get_analyzer(dimension, scope)(collection_path=self.collection_path, **kwargs)
            result = analyzer.optimize(**kwargs)
        except Exception as e:
            logger.error("%s is skipped when an exception is encountered. The exception is as follows: %s", scope, e)
            return OptimizeResult() if not output_dict else dict(OptimizeResult().data)

        if render_html and result.data:
            if hasattr(analyzer, "html_render"):
                analyzer.html_render.render_html()
            analyzer.html_render.save_to_file(f'mstt_advisor_{Timer().strftime}.html')

        return result if not output_dict else dict(result.data)


if __name__ == "__main__":
    Interface()
