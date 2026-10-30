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

# Shared conclusion texts (single source of truth for repeated sentences).
CONCLUSION_ALGO_OR_LINK = "通信算法选择不当, 或参数面链路冲突"
SUGGESTION_ALGO_OR_LINK = (
    "按拓扑自适应选择通信算法 (如 Hierarchical AllGather); "
    "降低DP域大小, 减少跨亲和组流量; "
    "优化部署亲和性, 确保同节点/同框内通信优先; "
    "确认是否开启 TACO-ranktable 及 routeplan"
)
CONCLUSION_BARRIER = "出现强制阻塞 (Cross-Group Synchronization Barrier)"
SUGGESTION_BARRIER = "修改并行策略，减少跨域强制同步（例如拆分 CP 和 DP 的同步边界）"
CONCLUSION_OPTIMIZER_HEAVY = "优化器通信过重（ Optimizer State Sharding Overhead ）"
SUGGESTION_OPTIMIZER_HEAVY = (
    "切换为更轻量的优化器分片策略 (如 ZeRO-2 替代 ZeRO-3); 或使用分片优化器 (Sharded Optimizer) 。"
)


class ClusterCompareBaseline(
    ClusterCompareReportMixin, ClusterCompareMetricsMixin, ClusterCompareDataMixin, BaseRecipeAnalysis
):
    """
    Cluster-level baseline comparison recipe.

    Pipeline:
        - Three-stage coarse-grained comparison in ``run()``:
          DP-domain check, CP/TP-domain check, unexplained-idle detection.
        - When the DP-domain check (Stage 1) is triggered, ``get_dp_domain``
          runs the four-phase diagnosis for the given step and records
          operator-level findings into ``operator_reports``.
        - Stage 2 and Stage 3 still run after Stage 1.

    Step alignment:
        Both current and baseline linearity are filtered by ``current_min_step``
        (legacy behavior). If baseline has no data for that step, the rank is
        skipped with an explicit message.

    Report layout:
        ``text_reports`` is reordered per rank so the .txt follows
        header -> four_phase -> stage2 -> stage3, independent of execution
        order.

    Operator reports:
        Per-rank ``operator_reports`` are accumulated across ranks and dumped
        once after the loop.
    """

    step_columns = ["id", "startNs", "endNs"]
    parallel_types = [("ep1",), ("ep2",), ("dp",), ("dp_cp",), ("pp",), ("tp",), ("ep_dp",), ("tp_cp",), ("cp",)]
    PARALLEL_COL_NAME = "parallelType"
    Computational_Operator_Linearity_Columns = LinearityUtils.COMPUTATIONAL_OPERATOR_LINEARITY_COLUMNS

    # Named thresholds (replaces inline magic numbers).
    DP_DEGRADE_PERCENT_THRESHOLD = 70
    NON_DP_DEGRADE_PERCENT_THRESHOLD = 70
    UNMASK_DELTA_THRESHOLD = 0.1
    IDLE_RATIO_THRESHOLD = 0.1
    FORWARD_BACKWARD_WINDOW_RATIO = 0.02
    LINEARITY_DELTA_THRESHOLD = 0.03
    ABNORMAL_RATIO_MULTIPLIER = 2
    SMALL_OP_COUNT_THRESHOLD = 100
    OPTIMIZER_RATIO_DELTA_THRESHOLD = 0.0

    @classmethod
    def add_parser_argument(cls, parser):
        """Add command-line arguments."""
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
        self.operator_reports = []

        self._baseline_data_map = {}
        baseline_profiling_path = self._extra_args.get('baseline_profiling_path', '')
        if baseline_profiling_path and os.path.exists(baseline_profiling_path):
            logger.info("Loading baseline data from: %s", baseline_profiling_path)
            self._baseline_data_map = self._load_baseline_data(baseline_profiling_path)
        elif baseline_profiling_path:
            logger.warning("Baseline profiling path does not exist: %s", baseline_profiling_path)

        self.db_paths = self._get_rank_db()
        self.baseline_db_paths = self._get_baseline_rank_db() if self._baseline_data_map else []
        self.rank_data_map = self._build_rank_data_map()

    def _build_rank_data_map(self):
        """Build ``rank_id -> {"current": ..., "baseline": ...}`` for shared ranks."""
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
        """Load baseline profiling data from ``baseline_path``."""
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
        """Return the DB paths of the baseline side."""
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
        """Write the accumulated text report to disk; errors propagate."""
        if not self.text_reports:
            return
        text_path = self._text_report_path(rank_id)
        content = "\n".join(self.text_reports) + "\n"
        FileManager.create_common_file(text_path, content)
        logger.info("Cluster compare baseline text report saved to %s", text_path)

    def save_operator_report(self, operator_reports=None):
        """Dump the accumulated operator-level findings into the DB table."""
        reports = self.operator_reports if operator_reports is None else operator_reports
        if not reports:
            return
        self.dump_data(
            data=pd.DataFrame(reports),
            file_name=Constant.DB_CLUSTER_COMMUNICATION_ANALYZER,
            table_name=Constant.TABLE_CLUSTER_COMPARE_BASELINE_OPERATOR,
            index=False,
        )

    def run(self, context):
        if not self.has_baseline:
            logger.warning("No baseline data available, skipping comparison analysis.")
            self._record_text("未提供或无法加载基线数据（--baseline_profiling_path），本次未执行对比。")
            self._save_text_report()
            return

        if not self.rank_data_map:
            logger.warning("Baseline data exists but no shared rank with current data; nothing to compare.")
            self._record_text("基线数据存在，但当前数据与基线没有共同的 rank，未执行对比。")
            self._save_text_report()
            return

        logger.info("Report output path: %s", self.output_path)
        all_operator_reports = []

        for rank_id, data in self.rank_data_map.items():
            self._reset_reports(rank_id)
            current = data.get("current")
            baseline = data.get("baseline")
            current_step_time, current_min_step = self.get_total_step_duration(current)
            baseline_step_time, _ = self.get_total_step_duration(baseline)

            # Legacy behavior: baseline is filtered by current_min_step so both
            # sides align on the same step id.
            baseline_linearity = self.get_linearity_df(baseline, self._recipe_name, current_min_step)
            current_linearity = self.get_linearity_df(current, self._recipe_name, current_min_step)

            baseline_result = self.sum_by_columns(
                baseline_linearity, group_cols=["parallelType"], sum_col="totalTimeWithoutCommunicationBlackout"
            )
            current_result = self.sum_by_columns(
                current_linearity, group_cols=["parallelType"], sum_col="totalTimeWithoutCommunicationBlackout"
            )
            comparison = self.compare_by_parallel_type(current_result, baseline_result)
            if comparison.empty or current_linearity.empty or baseline_linearity.empty:
                if baseline_linearity.empty and not current_linearity.empty:
                    self._record_text(f"baseline 侧没有 step {current_min_step} 的线性度数据，跳过该 rank。")
                else:
                    self._record_text("当前 rank 缺少可对比的线性度数据，跳过后续诊断。")
                self._save_text_report(rank_id)
                all_operator_reports.extend(self.operator_reports)
                continue

            dp_related = ["dp", "dp_cp", "ep_dp"]
            dp_mask = comparison["parallelType"].isin(dp_related)
            non_dp_mask = ~dp_mask

            # Stage 1
            if comparison.loc[dp_mask, "diff_percent"].sum() > self.DP_DEGRADE_PERCENT_THRESHOLD:
                self._record_text("【判定】: DP 相关域（dp/dp_cp/ep_dp）劣化显著，启动四阶段逐 step 诊断。")
                four_phase_start = len(self.text_reports)
                self.get_dp_domain(
                    current_linearity, baseline_linearity, current, baseline, current_min_step, self._recipe_name
                )
                four_phase_lines = self.text_reports[four_phase_start:]
                del self.text_reports[four_phase_start:]
            else:
                four_phase_start = len(self.text_reports)
                four_phase_lines = []

            # Stage 2
            current_unmask = current_linearity[~current_linearity["parallelType"].str.contains("dp", na=False)][
                "ratioOfUnmaskedCommunication"
            ].sum()
            base_unmask = baseline_linearity[~baseline_linearity["parallelType"].str.contains("dp", na=False)][
                "ratioOfUnmaskedCommunication"
            ].sum()
            reaction_condition_one = comparison.loc[non_dp_mask, "diff"].sum()
            reaction_condition_two = current_unmask - base_unmask

            if comparison.loc[non_dp_mask, "diff_percent"].sum() > self.NON_DP_DEGRADE_PERCENT_THRESHOLD:
                if reaction_condition_one > 0 and reaction_condition_two > self.UNMASK_DELTA_THRESHOLD:
                    bad = comparison[non_dp_mask & (comparison["diff_percent"] > 0)]
                    for _, row in bad.iterrows():
                        self._record_text(
                            f"通信域 {row['parallelType']} 劣化 {row['diff_percent']:.1f}% (diff={row['diff']:.3f})。"
                        )
                    self._record_text(
                        "可能波及 PP/EP/TP 域，请结合上述劣化域与数值排查；"
                        "PP 域对流水线延迟最敏感，EP 域的 AllToAll 对负载不均和网络拥塞敏感。"
                    )

            # Stage 3
            step_time_diff = current_step_time - baseline_step_time
            logger.info(
                "Stage3 inputs: current_min_step=%s current_step_time=%s baseline_step_time=%s "
                "diff_sum=%s step_diff=%s ratio=%s",
                current_min_step,
                current_step_time,
                baseline_step_time,
                comparison["diff"].sum(),
                step_time_diff,
                self._safe_divide(comparison["diff"].sum() - step_time_diff, step_time_diff),
            )
            if step_time_diff <= 0:
                self._record_text("当前 step 时长不大于基线，跳过未解释空闲分析。")
            elif (
                self._safe_divide(comparison["diff"].sum() - step_time_diff, step_time_diff) > self.IDLE_RATIO_THRESHOLD
            ):
                self._record_text("【空闲分析】: 该空闲未被任何通信域的净开销模型捕获。")
                self._record_text(
                    "【建议】: 常见原因包括:流水线并行气泡、调度间隙、框架层同步等待等。虽然这些空闲通常由DP域问题间接引发"
                    "(如DP通信阻塞导致流水线失衡),但其表现形式不是通信净开销的增加,而是全时空泡。先按照DP问题排查,"
                    "排除步骤2 3 4之后应输出告警,重点关注调度间隙。"
                )

            self.text_reports[four_phase_start:four_phase_start] = four_phase_lines
            self._save_text_report(rank_id)
            all_operator_reports.extend(self.operator_reports)

        self.save_operator_report(all_operator_reports)

    @staticmethod
    def _get_domains(current_value, baseline_value, parallel_type):
        """Return (current_domain, baseline_domain); zero is normalized to None."""
        current_domain = current_value.get(f"max_{parallel_type}_rank")
        baseline_domain = baseline_value.get(f"max_{parallel_type}_rank")
        if not current_domain:
            current_domain = None
        if not baseline_domain:
            baseline_domain = None
        return current_domain, baseline_domain

    def _record_phase_operator(
        self,
        step_id,
        phase,
        row_value,
        current_domain,
        baseline_domain,
        current_duration,
        baseline_duration,
        actual_ratio,
        theoretical_ratio,
        is_abnormal,
        conclusion,
        suggestion,
    ):
        """Shared operator-row builder for the four phases."""
        return self._record_operator(
            step_id=step_id,
            phase=phase,
            parallel_type=row_value.parallelType,
            op_type=row_value.opType.replace("hcom_", "").rstrip("_"),
            data_type=row_value.dataType,
            count=row_value.count,
            group_rank=row_value.group_rank,
            start_ns=row_value.startNs,
            end_ns=row_value.endNs,
            current_domain=current_domain,
            baseline_domain=baseline_domain,
            current_duration=current_duration,
            baseline_duration=baseline_duration,
            actual_ratio=actual_ratio,
            theoretical_ratio=theoretical_ratio,
            is_abnormal=is_abnormal,
            conclusion=conclusion,
            suggestion=suggestion,
        )

    def _evaluate_phase_operators(
        self,
        step_id,
        phase,
        title,
        current_df,
        baseline_df,
        current_value,
        baseline_value,
        filter_mask,
        conclusion,
        suggestion,
        require_count_domain_match=True,
        count_filter=None,
    ):
        """
        Shared flow for the four phases: iterate current ops, match baseline
        ops, compute ratios, record operator rows, and emit the conclusion
        once (outside the operator loop).

        ``filter_mask`` selects the phase's operators from ``current_df``.
        ``require_count_domain_match`` adds the ``count * domain`` equality to
        the baseline match; use it only for phases whose ``count`` scales with
        the parallel domain (forward / backward gradient), not for the small
        ``dp allReduce`` ops in forward-backward / optimizer.
        ``count_filter`` optionally skips operators by count.
        """
        if title:
            self._record_text(title)
        operator_rows = []

        if current_df is None or current_df.empty or baseline_df is None or baseline_df.empty:
            self._record_operator_table(f"{phase}算子评估表：", operator_rows)
            return operator_rows

        filtered = current_df[filter_mask(current_df)]
        any_abnormal = False

        for row_value in filtered.itertuples():
            parallel_type = row_value.parallelType
            current_opType = row_value.opType.replace("hcom_", "").rstrip("_")
            current_domain, baseline_domain = self._get_domains(current_value, baseline_value, parallel_type)
            if not current_domain or not baseline_domain:
                continue

            if count_filter is not None and not count_filter(row_value.count):
                continue

            match_mask = (
                (baseline_df["group_rank"] == row_value.group_rank)
                & (baseline_df["parallelType"].isin([parallel_type]))
                & (baseline_df["opType"].str.contains(current_opType, na=False))
            )
            if require_count_domain_match:
                match_mask = match_mask & (baseline_df["count"] * baseline_domain == row_value.count * current_domain)
            match = baseline_df.loc[match_mask].reset_index(drop=True)
            if match.empty:
                continue

            current_duration = self._ns_to_ms(row_value.endNs - row_value.startNs)
            baseline_duration = self._ns_to_ms(match["endNs"].values[0] - match["startNs"].values[0])
            ratio_dict = self.comm_lower_bound(
                row_value.count,
                baseline_duration,
                baseline_domain,
                current_domain,
                datatype=row_value.dataType,
                op_type=current_opType,
            )
            actual_ratio = self._safe_divide(current_duration, baseline_duration)
            is_abnormal = actual_ratio >= self.ABNORMAL_RATIO_MULTIPLIER * ratio_dict["ratio"]
            if is_abnormal:
                any_abnormal = True

            operator_rows.append(
                self._record_phase_operator(
                    step_id=step_id,
                    phase=phase,
                    row_value=row_value,
                    current_domain=current_domain,
                    baseline_domain=baseline_domain,
                    current_duration=current_duration,
                    baseline_duration=baseline_duration,
                    actual_ratio=actual_ratio,
                    theoretical_ratio=ratio_dict["ratio"],
                    is_abnormal=is_abnormal,
                    conclusion=conclusion if is_abnormal else "",
                    suggestion=suggestion if is_abnormal else "",
                )
            )

        if any_abnormal:
            self._record_text(f"【异常原因（当前版本）】{phase}: {conclusion}")
            self._record_text(f"【优化建议】{phase}: {suggestion}")

        self._record_operator_table(f"{phase}算子评估表：", operator_rows)
        return operator_rows

    def get_dp_domain(
        self,
        current_linearity,
        baseline_linearity,
        current_data_map,
        baseline_data_map,
        current_min_step,
        analysis_class,
    ):
        """
        Run the four-phase diagnosis for the given step id.

        ``current_min_step`` is a single step id; ``_analyze_data_by_step``
        keeps only that step, so this method processes one step per call.
        """
        current_results = self._analyze_data_by_step(current_data_map, analysis_class, current_min_step)
        baseline_results = self._analyze_data_by_step(baseline_data_map, f"{analysis_class}_baseline", current_min_step)

        for step_id, current_value in current_results.items():
            baseline_value = baseline_results.get(step_id)
            if baseline_value is None:
                self._record_text(f"step_id {step_id} 缺少 baseline 分析结果，跳过该 step。")
                continue
            step_duration = current_value["end_time"] - current_value["start_time"]

            self._analyze_forward_phase(step_id, current_value, baseline_value)
            self._analyze_forward_backward_phase(
                step_id, current_value, baseline_value, current_linearity, baseline_linearity, step_duration
            )
            self._analyze_backward_gradient_phase(step_id, current_value, baseline_value)
            self._analyze_optimizer_phase(step_id, current_value, baseline_value, step_duration)

    def _analyze_forward_phase(self, step_id, current_value, baseline_value):
        self._evaluate_phase_operators(
            step_id=step_id,
            phase="阶段一",
            title="[四阶段-1] forward：",
            current_df=current_value.get("forward_ret"),
            baseline_df=baseline_value.get("forward_ret"),
            current_value=current_value,
            baseline_value=baseline_value,
            filter_mask=lambda df: df["parallelType"].isin(self.PHASE_FILTERS["forward"][0])
            & df["opType"].str.contains("allGather", na=False),
            conclusion=CONCLUSION_ALGO_OR_LINK,
            suggestion=SUGGESTION_ALGO_OR_LINK,
            require_count_domain_match=True,
            count_filter=None,
        )

    def _analyze_forward_backward_phase(
        self, step_id, current_value, baseline_value, current_mask_df, baseline_mask_df, step_duration
    ):
        forward_ret = current_value.get("forward_ret")
        if forward_ret is None or forward_ret.empty:
            self._record_text("[四阶段-2] forward-backward：")
            self._record_text("未找到前向阶段算子数据，跳过阶段二分析。")
            self._record_operator_table("阶段二算子评估表：", [])
            return

        phase_forward_end = forward_ret["endNs"].max()
        backward_starts = []
        for key in ("backward_gradient_ret", "backward_optimizer_ret"):
            df = current_value.get(key)
            if df is not None and not df.empty:
                backward_starts.append(df["startNs"].min())

        if not backward_starts:
            self._record_text("[四阶段-2] forward-backward：")
            self._record_text("没有找到 Backward 阶段开始时间！")
            self._record_operator_table("阶段二算子评估表：", [])
            return

        window = min(backward_starts) - phase_forward_end
        if self._safe_divide(window, step_duration) <= self.FORWARD_BACKWARD_WINDOW_RATIO:
            self._record_text("[四阶段-2] forward-backward：")
            self._record_operator_table("阶段二算子评估表：", [])
            return

        self._record_text("[四阶段-2] forward-backward：")
        tp_delta = self._linearity_ratio(current_mask_df, step_id, "tp") - self._linearity_ratio(
            baseline_mask_df, step_id, "tp"
        )
        tp_cp_delta = self._linearity_ratio(current_mask_df, step_id, "tp_cp") - self._linearity_ratio(
            baseline_mask_df, step_id, "tp_cp"
        )
        if tp_delta >= self.LINEARITY_DELTA_THRESHOLD and tp_cp_delta >= self.LINEARITY_DELTA_THRESHOLD:
            self._record_text(f"tp 未掩盖率差值: {tp_delta}, tp_cp 未掩盖率差值: {tp_cp_delta}")
            self._record_text("【判定】:预取阻塞计算 (Prefetch-Compute Overlap劣化)。")
            self._record_text("【建议】:增大 Micro Batch Size ; 调整参数预取深度 (Prefetch Depth)。")

        # Phase 2 diagnoses dp allReduce only; see PHASE_FILTERS.
        self._evaluate_phase_operators(
            step_id=step_id,
            phase="阶段二",
            title="",
            current_df=current_value.get("forward_backward_ret"),
            baseline_df=baseline_value.get("forward_backward_ret"),
            current_value=current_value,
            baseline_value=baseline_value,
            filter_mask=lambda df: df["parallelType"].isin(self.PHASE_FILTERS["forward_backward"][0])
            & df["opType"].str.contains("allReduce", na=False),
            conclusion=CONCLUSION_BARRIER,
            suggestion=SUGGESTION_BARRIER,
            require_count_domain_match=False,  # dp allReduce count does not scale with domain
            count_filter=lambda c: c < self.SMALL_OP_COUNT_THRESHOLD,
        )

    def _analyze_backward_gradient_phase(self, step_id, current_value, baseline_value):
        self._evaluate_phase_operators(
            step_id=step_id,
            phase="阶段三",
            title="[四阶段-3] backward gradient：",
            current_df=current_value.get("backward_gradient_ret"),
            baseline_df=baseline_value.get("backward_gradient_ret"),
            current_value=current_value,
            baseline_value=baseline_value,
            filter_mask=lambda df: df["parallelType"].isin(self.PHASE_FILTERS["backward_gradient"][0])
            & df["opType"].str.contains("reduceScatter", na=False),
            conclusion=CONCLUSION_ALGO_OR_LINK,
            suggestion=SUGGESTION_ALGO_OR_LINK,
            require_count_domain_match=True,
            count_filter=None,
        )

    def _analyze_optimizer_phase(self, step_id, current_value, baseline_value, step_duration):
        self._record_text("[四阶段-4] optimizer：")
        current_optimizer_df = current_value.get("backward_optimizer_ret")
        baseline_optimizer_df = baseline_value.get("backward_optimizer_ret")

        if current_optimizer_df is None or current_optimizer_df.empty:
            self._record_operator_table("阶段四算子评估表：", [])
            return
        if baseline_optimizer_df is None or baseline_optimizer_df.empty:
            self._record_operator_table("阶段四算子评估表：", [])
            return

        current_df = current_optimizer_df.copy()
        current_df["duration"] = current_df["endNs"] - current_df["startNs"]
        current_ratio = self._safe_divide(current_df["duration"].sum(), step_duration)

        baseline_df = baseline_optimizer_df.copy()
        baseline_df["duration"] = baseline_df["endNs"] - baseline_df["startNs"]
        baseline_ratio = self._safe_divide(baseline_df["duration"].sum(), step_duration)

        if current_ratio - baseline_ratio > self.OPTIMIZER_RATIO_DELTA_THRESHOLD:
            self._record_text(
                f"【判定】：{CONCLUSION_OPTIMIZER_HEAVY} (current={current_ratio:.3f}, baseline={baseline_ratio:.3f})"
            )
            self._record_text(f"【建议】：{SUGGESTION_OPTIMIZER_HEAVY}")

        # Phase 4 diagnoses dp allReduce only; see PHASE_FILTERS.
        self._evaluate_phase_operators(
            step_id=step_id,
            phase="阶段四",
            title="",
            current_df=current_optimizer_df,
            baseline_df=baseline_optimizer_df,
            current_value=current_value,
            baseline_value=baseline_value,
            filter_mask=lambda df: df["parallelType"].isin(self.PHASE_FILTERS["optimizer"][0])
            & df["opType"].str.contains("allReduce", na=False),
            conclusion=CONCLUSION_BARRIER,
            suggestion=SUGGESTION_BARRIER,
            require_count_domain_match=False,
            count_filter=None,
        )
