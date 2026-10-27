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
          forward-backward, backward-gradient, optimizer) is NOT yet wired in.
          It is planned to be wired into the Stage 1 DP-domain branch in a
          follow-up change; the data-classification helper
          ``_analyze_data_by_step`` in ``ClusterCompareDataMixin`` is currently
          unreferenced and kept for that follow-up.
    """

    step_columns = ["id", "startNs", "endNs"]
    parallel_types = [("ep1",), ("ep2",), ("dp",), ("dp_cp",), ("pp",), ("tp",), ("ep_dp",), ("tp_cp",), ("cp",)]
    PARALLEL_COL_NAME = "parallelType"
    Computational_Operator_Linearity_Columns = LinearityUtils.COMPUTATIONAL_OPERATOR_LINEARITY_COLUMNS

    @classmethod
    def add_parser_argument(cls, parser):
        """
        Add command-line arguments.

        Baseline data can be supplied via ``--baseline_profiling_path``.
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
        self.text_reports = []

        # Load baseline data from --baseline_profiling_path when provided.
        self._baseline_data_map = {}
        baseline_profiling_path = self._extra_args.get('baseline_profiling_path', '')
        if baseline_profiling_path and os.path.exists(baseline_profiling_path):
            logger.info("Loading baseline data from: %s", baseline_profiling_path)
            self._baseline_data_map = self._load_baseline_data(baseline_profiling_path)
        elif baseline_profiling_path:
            logger.warning("Baseline profiling path does not exist: %s", baseline_profiling_path)

        # Collect the current and baseline DB paths.
        self.db_paths = self._get_rank_db()
        self.baseline_db_paths = self._get_baseline_rank_db() if self._baseline_data_map else []

        # Build the rank -> data map from the intersection of both sides.
        self.rank_data_map = self._build_rank_data_map()

    def _build_rank_data_map(self):
        """
        Build ``rank_id -> {"current": ..., "baseline": ...}`` for ranks that
        exist on both the current and the baseline side.
        """
        current_ranks = {db.get(Constant.RANK_ID) for db in self.db_paths if db.get(Constant.RANK_ID) is not None}
        baseline_ranks = {
            db.get(Constant.RANK_ID) for db in self.baseline_db_paths if db.get(Constant.RANK_ID) is not None
        }

        if self._rank_list == "all":
            target_ranks = current_ranks & baseline_ranks
        else:
            target_ranks = set(self._rank_list) & current_ranks & baseline_ranks

        rank_data_map = {rank_id: {} for rank_id in target_ranks}

        for db_path in self.db_paths:
            rank_id = db_path.get(Constant.RANK_ID)
            if rank_id is not None and rank_id in rank_data_map:
                rank_data_map[rank_id]["current"] = db_path

        for db_path in self.baseline_db_paths:
            rank_id = db_path.get(Constant.RANK_ID)
            if rank_id is not None and rank_id in rank_data_map:
                rank_data_map[rank_id]["baseline"] = db_path

        return rank_data_map

    def _load_baseline_data(self, baseline_path):
        """
        Load baseline profiling data from ``baseline_path`` using
        ``ProfDataAllocate``.
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

        if not data_map:
            logger.warning("Failed to load baseline data, continuing without baseline comparison")
            return {}

        if prof_type != self._prof_type:
            logger.warning(
                "Baseline profiling type (%s) does not match current (%s), comparison may not work properly",
                prof_type,
                self._prof_type,
            )

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
        """Whether baseline data is available."""
        return len(self.baseline_db_paths) > 0

    def _get_baseline_rank_db(self):
        """
        Return the DB paths of the baseline side by reusing ``_get_rank_db``
        with the baseline data map.
        """
        if not self._baseline_data_map:
            return []

        original_data_map = self._data_map
        try:
            self._data_map = self._baseline_data_map
            baseline_db_paths = self._get_rank_db()
            for db_path in baseline_db_paths:
                db_path['is_baseline'] = True
            return baseline_db_paths
        finally:
            self._data_map = original_data_map

    def _text_report_path(self, rank_id=None):
        if rank_id is None:
            return os.path.join(self.output_path, "cluster_compare_baseline.txt")
        return os.path.join(self.output_path, f"cluster_compare_baseline_rank_{rank_id}.txt")

    def _save_text_report(self, rank_id=None):
        """
        Write the accumulated text report to disk.

        Any write error is propagated to the caller so that a failed report is
        not silently swallowed.
        """
        if not self.text_reports:
            return
        text_path = self._text_report_path(rank_id)
        content = "\n".join(self.text_reports) + "\n"
        FileManager.create_common_file(text_path, content)
        logger.info("Cluster compare baseline text report saved to %s", text_path)

    def run(self, context):
        if not self.has_baseline:
            logger.warning("No baseline data available, skipping comparison analysis.")
            self._record_text("未提供或无法加载基线数据（--baseline_profiling_path），本次未执行对比。")
            self._save_text_report()
            return

        logger.info("Report output path: %s", self.output_path)

        for rank_id, data in self.rank_data_map.items():
            self._reset_reports(rank_id)
            current = data.get("current")
            baseline = data.get("baseline")
            current_step_time, current_min_step = self.get_total_step_duration(current)
            baseline_step_time, baseline_min_step = self.get_total_step_duration(baseline)

            # Each side is filtered by its own shortest step id; the ids are not
            # guaranteed to be equal across the two runs.
            baseline_linearity = self.get_linearity_df(baseline, self._recipe_name, baseline_min_step)
            current_linearity = self.get_linearity_df(current, self._recipe_name, current_min_step)

            baseline_result = self.sum_by_columns(
                baseline_linearity, group_cols=["parallelType"], sum_col="totalTimeWithoutCommunicationBlackout"
            )
            current_result = self.sum_by_columns(
                current_linearity, group_cols=["parallelType"], sum_col="totalTimeWithoutCommunicationBlackout"
            )
            comparison = self.compare_by_parallel_type(current_result, baseline_result)
            if comparison.empty or current_linearity.empty or baseline_linearity.empty:
                self._record_text("当前 rank 缺少可对比的线性度数据，跳过后续诊断。")
                self._save_text_report(rank_id)
                continue

            # ``how="outer"`` in compare_by_parallel_type can leave NaN
            # parallelType values; always use na=False / isin to stay safe.
            dp_related = ["dp", "dp_cp", "ep_dp"]
            dp_mask = comparison["parallelType"].isin(dp_related)
            non_dp_mask = ~dp_mask

            # ---------------------------------------------------------------
            # Stage 1: coarse-grained DP-domain check.
            # If the summed degradation (diff_percent) of dp / dp_cp / ep_dp
            # exceeds 70%, record a placeholder conclusion. The per-step
            # four-phase diagnosis is planned for a follow-up change.
            # ---------------------------------------------------------------
            if comparison.loc[dp_mask, "diff_percent"].sum() > 70:
                self._record_text("【判定】: DP 相关域（dp/dp_cp/ep_dp）劣化显著，四阶段逐 step 诊断将在后续版本接入。")

            # ---------------------------------------------------------------
            # Stage 2: CP / TP-domain check.
            # ---------------------------------------------------------------
            current_unmask = current_linearity[~current_linearity["parallelType"].str.contains("dp", na=False)][
                "ratioOfUnmaskedCommunication"
            ].sum()
            base_unmask = baseline_linearity[~baseline_linearity["parallelType"].str.contains("dp", na=False)][
                "ratioOfUnmaskedCommunication"
            ].sum()

            reaction_condition_one = comparison.loc[non_dp_mask, "diff"].sum()
            reaction_condition_two = current_unmask - base_unmask

            if comparison.loc[non_dp_mask, "diff_percent"].sum() > 70:
                if reaction_condition_one > 0 and reaction_condition_two > 0.1:
                    bad = comparison[non_dp_mask & (comparison["diff_percent"] > 0)]
                    for _, row in bad.iterrows():
                        self._record_text(
                            f"通信域 {row['parallelType']} 劣化 {row['diff_percent']:.1f}% (diff={row['diff']:.3f})。"
                        )
                    self._record_text(
                        "可能波及 PP/EP/TP 域，请结合上述劣化域与数值排查；"
                        "PP 域对流水线延迟最敏感，EP 域的 AllToAll 对负载不均和网络拥塞敏感。"
                    )

            # ---------------------------------------------------------------
            # Stage 3: unexplained-idle detection.
            # A non-positive step-time difference makes the ratio physically
            # meaningless, so skip explicitly instead of masking it as "none".
            # ---------------------------------------------------------------
            step_time_diff = current_step_time - baseline_step_time
            if step_time_diff <= 0:
                self._record_text("当前 step 时长不大于基线，跳过未解释空闲分析。")
            else:
                unexplained = comparison["diff"].sum() - step_time_diff
                if self._safe_divide(unexplained, step_time_diff) > 0.1:
                    self._record_text("【问题】: 该空闲未被任何通信域的净开销模型捕获。")
                    self._record_text(
                        "【建议】: 常见原因包括:流水线并行气泡、调度间隙、框架层同步等待等。虽然这些空闲通常由DP域问题间接引发"
                        "(如DP通信阻塞导致流水线失衡),但其表现形式不是通信净开销的增加,而是全时空泡。先按照DP问题排查,"
                        "排除步骤2 3 4之后应输出告警,重点关注调度间隙。"
                    )

            # Save per rank so that multi-rank runs do not overwrite each other.
            self._save_text_report(rank_id)
