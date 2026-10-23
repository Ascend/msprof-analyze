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

import os
import pandas as pd
from msprof_analyze.prof_common.constant import Constant
from msprof_analyze.prof_common.file_manager import FileManager
from msprof_analyze.prof_common.logger import get_logger
from msprof_analyze.cluster_analyse.recipes.base_recipe_analysis import BaseRecipeAnalysis

from msprof_analyze.cluster_analyse.recipes.cluster_compare_baseline.cluster_compare_data import ClusterCompareDataMixin
from msprof_analyze.cluster_analyse.recipes.cluster_compare_baseline.cluster_compare_metrics import (
    ClusterCompareMetricsMixin,
)
from msprof_analyze.cluster_analyse.recipes.cluster_compare_baseline.cluster_compare_report import (
    ClusterCompareReportMixin,
)
from msprof_analyze.cluster_analyse.common_func.linearity_utils import LinearityUtils

logger = get_logger()


class ClusterCompareBaseline(
    ClusterCompareReportMixin, ClusterCompareMetricsMixin, ClusterCompareDataMixin, BaseRecipeAnalysis
):
    """
    Cluster-level baseline comparison recipe.

    Current status:
        - The high-level three-stage comparison in ``run()`` is implemented:
          DP-domain check, CP/TP-domain check, and unexplained-idle detection.
        - The four-phase per-step fine-grained diagnosis (forward,
          forward-backward, backward-gradient, optimizer) is NOT yet wired
          into ``run()``; only the DP-domain entry point ``get_dp_domain()``
          exists and is triggered from the DP-domain branch.
    """

    step_columns = ["id", "startNs", "endNs"]
    parallel_types = [("ep1",), ("ep2",), ("dp",), ("dp_cp",), ("pp",), ("tp",), ("ep_dp",), ("tp_cp",), ("cp",)]
    PARALLEL_COL_NAME = "parallelType"
    Computational_Operator_Linearity_Columns = LinearityUtils.COMPUTATIONAL_OPERATOR_LINEARITY_COLUMNS

    @classmethod
    def add_parser_argument(cls, parser):
        """
        添加命令行参数。
        支持通过 --baseline_profiling_path 独立加载基线数据，
        也支持通过 params 中的 baseline_data_map 传递基线数据。
        """
        BaseRecipeAnalysis.add_parser_argument(parser)
        parser.add_argument(
            '--baseline_profiling_path',
            type=str,
            required=False,
            help='Path to the baseline profiling data for comparison',
        )

    def __init__(self, params):
        super().__init__(params)
        self.linearity_ret = pd.DataFrame()
        self.params = params
        self.text_reports = []
        self.operator_reports = []
        self._current_report_rank_id = None
        self.report_output_dir = params.get("output_dir", "")

        # 优先使用 params 中的 baseline_data_map（由上层通过 -bp 传入）
        self._baseline_data_map = params.get("baseline_data_map", {})

        # 如果没有 baseline_data_map，尝试从 --baseline_profiling_path 加载
        if not self._baseline_data_map:
            baseline_profiling_path = self._extra_args.get('baseline_profiling_path', '')
            if baseline_profiling_path and os.path.exists(baseline_profiling_path):
                logger.info("Loading baseline data from: %s", baseline_profiling_path)
                self._baseline_data_map = self._load_baseline_data(baseline_profiling_path)
            elif baseline_profiling_path:
                logger.warning("Baseline profiling path does not exist: %s", baseline_profiling_path)

        # 获取原始数据
        self.db_paths = self._get_rank_db()
        # 获取基线数据（自行实现，不依赖基类）
        self.baseline_db_paths = self._get_baseline_rank_db() if self._baseline_data_map else []

        # 提取 rank 集合
        current_ranks = {db.get(Constant.RANK_ID) for db in self.db_paths if db.get(Constant.RANK_ID) is not None}
        baseline_ranks = {
            db.get(Constant.RANK_ID) for db in self.baseline_db_paths if db.get(Constant.RANK_ID) is not None
        }

        # 确定要处理的rank（当前和基线都有的rank）
        if self._rank_list == "all":
            target_ranks = current_ranks & baseline_ranks
        else:
            target_ranks = set(self._rank_list) & current_ranks & baseline_ranks

        # 构建 rank -> 数据的映射
        self.rank_data_map = {}
        for rank_id in target_ranks:
            self.rank_data_map[rank_id] = {}

        # 填充当前数据
        for db_path in self.db_paths:
            rank_id = db_path.get(Constant.RANK_ID)
            if rank_id is not None and rank_id in self.rank_data_map:
                self.rank_data_map[rank_id]["current"] = db_path

        # 填充基线数据
        for db_path in self.baseline_db_paths:
            rank_id = db_path.get(Constant.RANK_ID)
            if rank_id is not None and rank_id in self.rank_data_map:
                self.rank_data_map[rank_id]["baseline"] = db_path

    def _load_baseline_data(self, baseline_path):
        """
        从指定路径加载基线数据
        复用 ProfDataAllocate 的逻辑
        """
        from msprof_analyze.cluster_analyse.cluster_data_preprocess.prof_data_allocate import ProfDataAllocate

        logger.info("Start allocate baseline profiling data from: %s", baseline_path)
        allocator = ProfDataAllocate(baseline_path)
        if not allocator.allocate_prof_data():
            logger.warning("Failed to allocate baseline prof data from: %s", baseline_path)
            return {}

        data_map = allocator.data_map
        prof_type = allocator.prof_type

        logger.info(
            "Finish allocate baseline profiling data: %s ranks, data type: %s, profiling type: %s",
            len(data_map),
            allocator.data_type,
            prof_type,
        )

        # 验证基线数据
        if not data_map:
            logger.warning("Failed to load baseline data, continuing without baseline comparison")
            return {}

        # 验证类型匹配
        if prof_type != self._prof_type:
            logger.warning(
                "Baseline profiling type (%s) does not match current (%s), comparison may not work properly",
                prof_type,
                self._prof_type,
            )

        # 验证 rank 数量
        baseline_ranks = set(data_map.keys())
        current_ranks = set(self._data_map.keys())
        if baseline_ranks != current_ranks:
            logger.warning("Baseline ranks %s do not match current %s", len(baseline_ranks), len(current_ranks))

        return data_map

    @property
    def base_dir(self):
        return os.path.basename(os.path.dirname(__file__))

    @property
    def has_baseline(self):
        """是否有基线数据"""
        return len(self.baseline_db_paths) > 0

    def _get_baseline_rank_db(self):
        """
        获取基线目录的数据库路径列表
        复用 _get_rank_db 的逻辑，但使用基线的 data_map
        """
        if not self._baseline_data_map:
            return []

        # 保存原始的 _data_map
        original_data_map = self._data_map

        try:
            # 临时替换为基线 data_map
            self._data_map = self._baseline_data_map
            # 复用 _get_rank_db 的逻辑
            baseline_db_paths = self._get_rank_db()
            # 为基线 db_paths 添加标识
            for db_path in baseline_db_paths:
                db_path['is_baseline'] = True
            return baseline_db_paths
        finally:
            self._data_map = original_data_map

    def save_reports(self):
        """保存报告：文本 + DB 表"""
        # 1. 文本报告 → .txt（人类可读）
        if self.text_reports:
            text_path = os.path.join(self.output_path, "cluster_compare_baseline.txt")
            content = "\n".join(self.text_reports) + "\n"
            try:
                FileManager.create_common_file(text_path, content)
                logger.info("Cluster compare baseline text report saved to %s", text_path)
            except Exception as e:
                logger.error("Failed to write text report '%s': %s", text_path, e)

        # 2. 算子报告 → DB 表（与 ComputationalOpMasking 共用 cluster_analysis.db）
        if self.operator_reports:
            df = pd.DataFrame(self.operator_reports)
            self.dump_data(
                data=df,
                file_name=Constant.DB_CLUSTER_COMMUNICATION_ANALYZER,
                table_name=Constant.TABLE_CLUSTER_COMPARE_BASELINE_OPERATOR,
                index=False,
            )

    def run(self, context):
        if not self.has_baseline:
            logger.warning("No baseline data available, skipping comparison analysis.")
            return

        logger.info("Report output path: %s", self.output_path)

        for rank_id, data in self.rank_data_map.items():
            self._reset_reports(rank_id)
            current = data.get("current")
            baseline = data.get("baseline")
            current_step_time, current_min_step = self.get_total_step_duration(current)
            baseline_step_time, _ = self.get_total_step_duration(baseline)

            baseline_linearity = self.get_linearity_df(baseline, self._recipe_name, current_min_step)
            current_linearity = self.get_linearity_df(current, self._recipe_name, current_min_step)

            # Aggregate the total time without communication blackout per parallel type.
            baseline_result = self.sum_by_columns(
                baseline_linearity, group_cols=["parallelType"], sum_col="totalTimeWithoutCommunicationBlackout"
            )
            current_result = self.sum_by_columns(
                current_linearity, group_cols=["parallelType"], sum_col="totalTimeWithoutCommunicationBlackout"
            )
            comparison = self.compare_by_parallel_type(current_result, baseline_result)
            if comparison.empty or current_linearity.empty or baseline_linearity.empty:
                self._record_text("当前 rank 缺少可对比的线性度数据，跳过后续诊断。")
                logger.info(
                    "rank %s: text_reports=%s, operator_reports=%s",
                    rank_id,
                    len(self.text_reports),
                    len(self.operator_reports),
                )
                continue

            # ---------------------------------------------------------------
            # Stage 1: coarse-grained DP-domain check.
            # If the summed degradation (diff_percent) of dp / dp_cp / ep_dp
            # exceeds 70%, trigger the per-step DP-domain deep dive.
            # NOTE: The four-phase fine-grained diagnosis (forward,
            # forward-backward, backward-gradient, optimizer) is NOT yet wired
            # into run(); only the DP-domain entry point is invoked here.
            # ---------------------------------------------------------------
            if comparison[comparison["parallelType"].isin(["dp", "dp_cp", "ep_dp"])]["diff_percent"].sum() > 70:
                continue

            # ---------------------------------------------------------------
            # Stage 2: CP / TP-domain check.
            # Compare the unmasked-communication ratio and net overhead of all
            # non-DP parallel types between the current and baseline runs.
            # A degradation above 70% together with a positive net overhead
            # and an unmasked-ratio delta larger than 0.1 indicates that
            # resource contention has spread beyond the DP domain.
            # ---------------------------------------------------------------
            current_unmask = current_linearity[~current_linearity["parallelType"].str.contains("dp")][
                "ratioOfUnmaskedCommunication"
            ].sum()
            base_unmask = baseline_linearity[~baseline_linearity["parallelType"].str.contains("dp")][
                "ratioOfUnmaskedCommunication"
            ].sum()

            reaction_condition_one = comparison[~comparison["parallelType"].str.contains("dp")]["diff"].sum()
            reaction_condition_two = current_unmask - base_unmask

            if comparison[~comparison["parallelType"].str.contains("dp")]["diff_percent"].sum() > 70:
                if reaction_condition_one > 0 and reaction_condition_two > 0.1:
                    self._record_text("PP域对流水线延迟最为敏感, 只要DP域劣化, PP域几乎必然出现净开销增加;")
                    self._record_text("EP域的AllToAll通信对全局负载不均和网络拥塞及其敏感,")
                    self._record_text("若TP域也出现异常,则表明资源竞争已波及所有通信域(CP、TP等)。")

            # ---------------------------------------------------------------
            # Stage 3: unexplained-idle detection.
            # Subtract the net overhead explained by the communication-domain
            # model from the total step-time difference. If more than 10% of
            # the step-time difference remains unexplained, it usually points
            # to pipeline-parallelism bubbles, scheduling gaps, or
            # framework-level synchronization waits.
            # ---------------------------------------------------------------
            step_time_diff = current_step_time - baseline_step_time
            if self._safe_divide(comparison["diff"].sum() - step_time_diff, step_time_diff) > 0.1:
                self._record_text("【问题】: 该空闲未被任何通信域的净开销模型捕获。")
                self._record_text(
                    "【建议】: 常见原因包括:流水线并行气泡、调度间隙、框架层同步等待等。虽然这些空闲通常由DP域问题间接引发"
                    "(如DP通信阻塞导致流水线失衡),但其表现形式不是通信净开销的增加,而是全时空泡。先按照DP问题排查,"
                    "排除步骤2 3 4之后应输出告警,重点关注调度间隙。"
                )

            logger.info(
                "rank %s: text_reports=%s, operator_reports=%s",
                rank_id,
                len(self.text_reports),
                len(self.operator_reports),
            )

        logger.info("Report output path: %s", self.output_path)
        self.save_reports()
