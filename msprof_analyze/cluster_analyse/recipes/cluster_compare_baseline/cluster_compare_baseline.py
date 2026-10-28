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

    Pipeline:
        - Three-stage coarse-grained comparison in ``run()``:
          DP-domain check, CP/TP-domain check, unexplained-idle detection.
        - When the DP-domain check (Stage 1) is triggered, ``get_dp_domain``
          runs the four-phase per-step diagnosis and records operator-level
          findings into ``operator_reports``.
        - Stage 2 and Stage 3 still run after Stage 1.

    Step alignment:
        Both current and baseline linearity are filtered by ``current_min_step``
        (legacy behavior), so the two sides are aligned on the same step id.

    Report layout:
        ``text_reports`` is reordered at the end of each rank so the .txt
        follows header -> four_phase -> stage2 -> stage3, independent of the
        execution order. The .txt itself is still a plain join of
        ``text_reports``.
    """

    step_columns = ["id", "startNs", "endNs"]
    parallel_types = [("ep1",), ("ep2",), ("dp",), ("dp_cp",), ("pp",), ("tp",), ("ep_dp",), ("tp_cp",), ("cp",)]
    PARALLEL_COL_NAME = "parallelType"
    Computational_Operator_Linearity_Columns = LinearityUtils.COMPUTATIONAL_OPERATOR_LINEARITY_COLUMNS

    SMALL_OP_COUNT_THRESHOLD = 100

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

    def save_operator_report(self):
        """Dump the accumulated operator-level findings into the DB table."""
        if not self.operator_reports:
            return
        self.dump_data(
            data=pd.DataFrame(self.operator_reports),
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

        logger.info("Report output path: %s", self.output_path)

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
                self._record_text("当前 rank 缺少可对比的线性度数据，跳过后续诊断。")
                self._save_text_report(rank_id)
                continue

            dp_related = ["dp", "dp_cp", "ep_dp"]
            dp_mask = comparison["parallelType"].isin(dp_related)
            non_dp_mask = ~dp_mask

            # Stage 1: DP-domain check. Stage 2/3 still run afterwards.
            if comparison.loc[dp_mask, "diff_percent"].sum() > 70:
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

            # Stage 2: CP / TP-domain check.
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

            # Stage 3 (idle): unexplained-idle detection.
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
            elif self._safe_divide(comparison["diff"].sum() - step_time_diff, step_time_diff) > 0.1:
                self._record_text("【空闲分析】: 该空闲未被任何通信域的净开销模型捕获。")
                self._record_text(
                    "【建议】: 常见原因包括:流水线并行气泡、调度间隙、框架层同步等待等。虽然这些空闲通常由DP域问题间接引发"
                    "(如DP通信阻塞导致流水线失衡),但其表现形式不是通信净开销的增加,而是全时空泡。先按照DP问题排查,"
                    "排除步骤2 3 4之后应输出告警,重点关注调度间隙。"
                )

            # Re-insert the four-phase block before the Stage 2/3 text so the
            # .txt order is header -> four_phase -> stage2 -> stage3.
            self.text_reports[four_phase_start:four_phase_start] = four_phase_lines

            self._save_text_report(rank_id)

        self.save_operator_report()

    @staticmethod
    def _get_domains(current_value, baseline_value, parallel_type):
        """Return (current_domain, baseline_domain); either may be None."""
        return (
            current_value.get(f"max_{parallel_type}_rank"),
            baseline_value.get(f"max_{parallel_type}_rank"),
        )

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

    def get_dp_domain(
        self,
        current_linearity,
        baseline_linearity,
        current_data_map,
        baseline_data_map,
        current_min_step,
        analysis_class,
    ):
        """Run the four-phase diagnosis for each comparable step."""
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
        self._record_text("[四阶段-1] forward：")
        operator_rows = []
        for row_value in current_value["forward_ret"].itertuples():
            parallel_type = row_value.parallelType
            current_opType = row_value.opType.replace("hcom_", "").rstrip("_")
            current_domain, baseline_domain = self._get_domains(current_value, baseline_value, parallel_type)
            if current_domain is None or baseline_domain is None:
                continue

            baseline_forward = baseline_value["forward_ret"]
            match = baseline_forward.loc[
                (baseline_forward["group_rank"] == row_value.group_rank)
                & (baseline_forward["parallelType"].isin([parallel_type]))
                & (baseline_forward["count"] * baseline_domain == row_value.count * current_domain)
                & (baseline_forward["opType"].str.contains(current_opType, na=False)),
            ].reset_index(drop=True)
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
            is_abnormal = actual_ratio >= 2 * ratio_dict["ratio"]
            operator_rows.append(
                self._record_phase_operator(
                    step_id=step_id,
                    phase="阶段一",
                    row_value=row_value,
                    current_domain=current_domain,
                    baseline_domain=baseline_domain,
                    current_duration=current_duration,
                    baseline_duration=baseline_duration,
                    actual_ratio=actual_ratio,
                    theoretical_ratio=ratio_dict["ratio"],
                    is_abnormal=is_abnormal,
                    conclusion="通信算法选择不当, 或参数面链路冲突" if is_abnormal else "",
                    suggestion=(
                        "按拓扑自适应选择通信算法; 降低DP域大小; 优化部署亲和性; "
                        "确认是否开启 TACO-ranktable 及 routeplan"
                    )
                    if is_abnormal
                    else "",
                )
            )
            if is_abnormal:
                self._record_text("【异常原因（当前版本）】: 通信算法选择不当, 或参数面链路冲突.")
                self._record_text(
                    "【优化建议】: 按拓扑自适应选择通信算法 (如 Hierarchical AllGather); "
                    "降低DP域大小, 减少跨亲和组流量; "
                    "优化部署亲和性, 确保同节点/同框内通信优先; "
                    "确认是否开启 TACO-ranktable 及 routeplan"
                )
        self._record_operator_table("阶段一算子评估表：", operator_rows)

    def _analyze_forward_backward_phase(
        self, step_id, current_value, baseline_value, current_mask_df, baseline_mask_df, step_duration
    ):
        self._record_text("[四阶段-2] forward-backward：")
        forward_ret = current_value.get("forward_ret")
        if forward_ret is None or forward_ret.empty:
            self._record_text("未找到前向阶段算子数据，跳过阶段二分析。")
            return

        operator_rows = []
        phase_forward_end = forward_ret["endNs"].max()
        backward_starts = []
        for key in ("backward_gradient_ret", "backward_optimizer_ret"):
            df = current_value.get(key)
            if df is not None and not df.empty:
                backward_starts.append(df["startNs"].min())

        if not backward_starts:
            self._record_text("没有找到 Backward 阶段开始时间！")
            self._record_operator_table("阶段二算子评估表：", operator_rows)
            return

        current_forward_backward_duration = min(backward_starts) - phase_forward_end
        if self._safe_divide(current_forward_backward_duration, step_duration) <= 0.02:
            self._record_operator_table("阶段二算子评估表：", operator_rows)
            return

        current_fb_df = current_value["forward_backward_ret"]
        operator_dp_df = current_fb_df[
            (current_fb_df["parallelType"].isin(["dp"])) & (current_fb_df["opType"].str.contains("allReduce", na=False))
        ]

        tp_delta = self._linearity_ratio(current_mask_df, step_id, "tp") - self._linearity_ratio(
            baseline_mask_df, step_id, "tp"
        )
        tp_cp_delta = self._linearity_ratio(current_mask_df, step_id, "tp_cp") - self._linearity_ratio(
            baseline_mask_df, step_id, "tp_cp"
        )
        if tp_delta >= 0.03 and tp_cp_delta >= 0.03:
            self._record_text(f"tp 未掩盖率差值: {tp_delta}, tp_cp 未掩盖率差值: {tp_cp_delta}")
            self._record_text("【判定】:预取阻塞计算 (Prefetch-Compute Overlap劣化)。")
            self._record_text("【建议】:增大 Micro Batch Size ; 调整参数预取深度 (Prefetch Depth)。")

        for row_value in operator_dp_df.itertuples():
            parallel_type = row_value.parallelType
            current_opType = row_value.opType.replace("hcom_", "").rstrip("_")
            current_domain, baseline_domain = self._get_domains(current_value, baseline_value, parallel_type)
            if current_domain is None or baseline_domain is None:
                continue

            baseline_fb_df = baseline_value["forward_backward_ret"]
            match = baseline_fb_df.loc[
                (baseline_fb_df["group_rank"] == row_value.group_rank)
                & (baseline_fb_df["parallelType"].isin([parallel_type]))
                & (baseline_fb_df["opType"].str.contains(current_opType, na=False))
            ].reset_index(drop=True)
            if match.empty or row_value.count >= self.SMALL_OP_COUNT_THRESHOLD:
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
            is_abnormal = actual_ratio >= 2 * ratio_dict["ratio"]
            operator_rows.append(
                self._record_phase_operator(
                    step_id=step_id,
                    phase="阶段二",
                    row_value=row_value,
                    current_domain=current_domain,
                    baseline_domain=baseline_domain,
                    current_duration=current_duration,
                    baseline_duration=baseline_duration,
                    actual_ratio=actual_ratio,
                    theoretical_ratio=ratio_dict["ratio"],
                    is_abnormal=is_abnormal,
                    conclusion="出现强制阻塞 (Cross-Group Synchronization Barrier)" if is_abnormal else "",
                    suggestion="修改并行策略，减少跨域强制同步（例如拆分 CP 和 DP 的同步边界）" if is_abnormal else "",
                )
            )
            if is_abnormal:
                self._record_text("【判定】：出现强制阻塞 (Cross-Group Synchronization Barrier)。")
                self._record_text("【建议】：修改并行策略，减少跨域强制同步（例如拆分 CP 和 DP 的同步边界）。")
        self._record_operator_table("阶段二算子评估表：", operator_rows)

    def _analyze_backward_gradient_phase(self, step_id, current_value, baseline_value):
        self._record_text("[四阶段-3] backward gradient：")
        operator_rows = []
        backward_gradient_df = current_value["backward_gradient_ret"]
        if backward_gradient_df is None or backward_gradient_df.empty:
            return

        operator_bp_df = backward_gradient_df[
            (backward_gradient_df["parallelType"].isin(["dp", "dp_cp", "ep_dp"]))
            & (backward_gradient_df["opType"].str.contains("reduceScatter", na=False))
        ]
        for row_value in operator_bp_df.itertuples():
            parallel_type = row_value.parallelType
            current_opType = row_value.opType.replace("hcom_", "").rstrip("_")
            current_domain, baseline_domain = self._get_domains(current_value, baseline_value, parallel_type)
            if current_domain is None or baseline_domain is None:
                continue

            baseline_gradient = baseline_value["backward_gradient_ret"]
            if baseline_gradient.empty:
                continue
            match = baseline_gradient.loc[
                (baseline_gradient["group_rank"] == row_value.group_rank)
                & (baseline_gradient["parallelType"].isin([parallel_type]))
                & (baseline_gradient["count"] * baseline_domain == row_value.count * current_domain)
                & (baseline_gradient["opType"].str.contains(current_opType, na=False))
            ].reset_index(drop=True)
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
            is_abnormal = actual_ratio >= 2 * ratio_dict["ratio"]
            operator_rows.append(
                self._record_phase_operator(
                    step_id=step_id,
                    phase="阶段三",
                    row_value=row_value,
                    current_domain=current_domain,
                    baseline_domain=baseline_domain,
                    current_duration=current_duration,
                    baseline_duration=baseline_duration,
                    actual_ratio=actual_ratio,
                    theoretical_ratio=ratio_dict["ratio"],
                    is_abnormal=is_abnormal,
                    conclusion="通信算法选择不当，或者参数面链路冲突" if is_abnormal else "",
                    suggestion=(
                        "按拓扑自适应选择通信算法; 降低DP域大小; 优化部署的亲和性; "
                        "确认是否开启 TACO-ranktable 及 routeplan"
                    )
                    if is_abnormal
                    else "",
                )
            )
            if is_abnormal:
                self._record_text("【异常原因（当前版本）】：通信算法选择不当，或者参数面链路冲突。")
                self._record_text(
                    "【优化建议】: 按拓扑自适应选择通信算法(如 Herarchical AllGather); "
                    "降低DP域大小, 减少跨亲和组流量; "
                    "优化部署的亲和性，确保同节点/同框内通信优先; "
                    "确认是否开启 TACO-ranktable 及 routeplan。"
                )
        self._record_operator_table("阶段三算子评估表：", operator_rows)

    def _analyze_optimizer_phase(self, step_id, current_value, baseline_value, step_duration):
        self._record_text("[四阶段-4] optimizer：")
        operator_rows = []
        current_optimizer_df = current_value["backward_optimizer_ret"]
        if current_optimizer_df is None or current_optimizer_df.empty:
            return

        current_optimizer_df = current_optimizer_df.copy()
        current_optimizer_df["duration"] = current_optimizer_df["endNs"] - current_optimizer_df["startNs"]
        if self._safe_divide(current_optimizer_df["duration"].sum(), step_duration) <= 0.02:
            return

        self._record_text("【判定】：优化器通信过重（ Optimizer State Sharding Overhead ）。")
        self._record_text(
            "【建议】：切换为更轻量的优化器分片策略 (如 ZeRO-2 替代 ZeRO-3); 或使用分片优化器 (Sharded Optimizer) 。"
        )
        operator_optimizer_df = current_optimizer_df[
            (current_optimizer_df["parallelType"].isin(["dp"]))
            & (current_optimizer_df["opType"].str.contains("allReduce", na=False))
        ]
        for row_value in operator_optimizer_df.itertuples():
            parallel_type = row_value.parallelType
            current_opType = row_value.opType.replace("hcom_", "").rstrip("_")
            current_domain, baseline_domain = self._get_domains(current_value, baseline_value, parallel_type)
            if current_domain is None or baseline_domain is None:
                continue

            baseline_optimizer = baseline_value["backward_optimizer_ret"]
            match = baseline_optimizer.loc[
                (baseline_optimizer["group_rank"] == row_value.group_rank)
                & (baseline_optimizer["parallelType"].isin([parallel_type]))
                & (baseline_optimizer["opType"].str.contains(current_opType, na=False))
            ].reset_index(drop=True)
            if match.empty or row_value.count >= self.SMALL_OP_COUNT_THRESHOLD:
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
            is_abnormal = actual_ratio >= 2 * ratio_dict["ratio"]
            operator_rows.append(
                self._record_phase_operator(
                    step_id=step_id,
                    phase="阶段四",
                    row_value=row_value,
                    current_domain=current_domain,
                    baseline_domain=baseline_domain,
                    current_duration=current_duration,
                    baseline_duration=baseline_duration,
                    actual_ratio=actual_ratio,
                    theoretical_ratio=ratio_dict["ratio"],
                    is_abnormal=is_abnormal,
                    conclusion="出现强制阻塞 (Cross-Group Synchronization Barrier)" if is_abnormal else "",
                    suggestion="修改并行策略，减少跨域强制同步（例如拆分 CP 与 DP 的同步时间）" if is_abnormal else "",
                )
            )
            if is_abnormal:
                self._record_text("【判定】：出现强制阻塞 (Cross-Group Synchronization Barrier)。")
                self._record_text("【建议】：修改并行策略，减少跨域强制同步（例如拆分 CP 与 DP 的同步时间）。")
        self._record_operator_table("阶段四算子评估表：", operator_rows)
