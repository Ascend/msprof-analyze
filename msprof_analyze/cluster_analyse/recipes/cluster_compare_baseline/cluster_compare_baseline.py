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

            # 按 Rank_id 和 stepId 分组，对duration求和
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

            # 第一阶段：直接判断
            if comparison[comparison["parallelType"].isin(["dp", "dp_cp", "ep_dp"])]["diff_percent"].sum() > 70:
                self.get_dp_domain(
                    current_linearity, baseline_linearity, current, baseline, current_min_step, self._recipe_name
                )

            # 第二阶段：判断CP和TP
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

            # 阶段三：判断
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
        同时处理 current 和 baseline 数据, 按 step 输出对比结果

        Returns:
            list of dict: 每个 step 的对比结果
        """
        # 获取掩盖大小
        current_mask_df = current_linearity
        baseline_mask_df = baseline_linearity

        # 获取 current 数据按照 step 的分析结果
        current_results = self._analyze_data_by_step(current_data_map, analysis_class, current_min_step)
        # 获取 baseline 数据按照 step 的分析结果
        baseline_results = self._analyze_data_by_step(baseline_data_map, f"{analysis_class}_baseline", current_min_step)

        for step_id, current_value in current_results.items():
            baseline_value = baseline_results.get(step_id)
            if baseline_value is None:
                self._record_text(f"step_id {step_id} 缺少 baseline 分析结果，跳过该 step。")
                continue
            step_duration = current_value["end_time"] - current_value["start_time"]

            self._analyze_forward_phase(step_id, current_value, baseline_value)
            self._analyze_forward_backward_phase(
                step_id, current_value, baseline_value, current_mask_df, baseline_mask_df, step_duration
            )
            self._analyze_backward_gradient_phase(step_id, current_value, baseline_value)
            self._analyze_optimizer_phase(step_id, current_value, baseline_value, step_duration)

    def _analyze_forward_phase(self, step_id, current_value, baseline_value):
        # 阶段1的判断
        self._record_text("阶段一：")
        operator_rows = []
        current_communication = current_value["forward_ret"]
        for row_index, row_value in enumerate(current_communication.itertuples()):
            parallel_type = row_value.parallelType
            current_opType = row_value.opType.replace("hcom_", "").rstrip("_")
            current_dataType = row_value.dataType
            current_count = row_value.count
            operator_start_time = row_value.startNs
            operator_end_time = row_value.endNs
            operator_group_rank = row_value.group_rank
            current_domain = current_value[f"max_{parallel_type}_rank"]
            baseline_domain = baseline_value[f"max_{parallel_type}_rank"]
            baseline_forward = baseline_value["forward_ret"]
            associate_baseline_forward = baseline_forward.loc[
                (baseline_forward["group_rank"] == operator_group_rank)
                & (baseline_forward["parallelType"].isin([parallel_type]))
                & (baseline_forward["count"] * baseline_domain == current_count * current_domain)
                & (baseline_forward["opType"].str.contains(current_opType)),
            ].reset_index(drop=True)
            if associate_baseline_forward.empty:
                continue

            baseline_forward_start_time = associate_baseline_forward["startNs"].values[0]
            baseline_forward_end_time = associate_baseline_forward["endNs"].values[0]

            current_operator_duration = self._ns_to_ms(operator_end_time - operator_start_time)
            baseline_operator_duration = self._ns_to_ms(baseline_forward_end_time - baseline_forward_start_time)
            ratio_dict = self.comm_lower_bound(
                current_count,
                baseline_operator_duration,
                baseline_domain,
                current_domain,
                datatype=current_dataType,
                op_type=current_opType,
            )
            actual_ratio = self._safe_divide(current_operator_duration, baseline_operator_duration)
            is_abnormal = actual_ratio >= 2 * ratio_dict["ratio"]
            operator_row = self._record_operator(
                step_id=step_id,
                phase="阶段一",
                parallel_type=parallel_type,
                op_type=current_opType,
                data_type=current_dataType,
                count=current_count,
                group_rank=operator_group_rank,
                start_ns=operator_start_time,
                end_ns=operator_end_time,
                current_domain=current_domain,
                baseline_domain=baseline_domain,
                current_duration=current_operator_duration,
                baseline_duration=baseline_operator_duration,
                actual_ratio=actual_ratio,
                theoretical_ratio=ratio_dict["ratio"],
                is_abnormal=is_abnormal,
                conclusion="通信算法选择不当, 或参数面链路冲突" if is_abnormal else "",
                suggestion=(
                    "按拓扑自适应选择通信算法; 降低DP域大小; 优化部署亲和性; 确认是否开启 TACO-ranktable 及 routeplan"
                )
                if is_abnormal
                else "",
            )
            operator_rows.append(operator_row)
            if actual_ratio >= 2 * ratio_dict["ratio"]:
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
        # 阶段2的判断
        self._record_text("阶段二：")

        # 检查 forward_ret 是否存在且非空
        forward_ret = current_value.get("forward_ret")
        if forward_ret is None or forward_ret.empty:
            self._record_text("未找到前向阶段算子数据，跳过阶段二分析。")
            return

        operator_rows = []
        phase_forward_end = forward_ret["endNs"].max()

        # 收集不为空的 backward 开始时间
        backward_starts = []
        if current_value["backward_gradient_ret"] is not None and not current_value["backward_gradient_ret"].empty:
            backward_starts.append(current_value["backward_gradient_ret"]["startNs"].min())

        if current_value["backward_optimizer_ret"] is not None and not current_value["backward_optimizer_ret"].empty:
            backward_starts.append(current_value["backward_optimizer_ret"]["startNs"].min())

        if backward_starts:
            phase_backward_start = min(backward_starts)  # 取最小的开始时间
            current_forward_backward_duration = phase_backward_start - phase_forward_end
            if self._safe_divide(current_forward_backward_duration, step_duration) > 0.02:
                current_fb_df = current_value["forward_backward_ret"]
                operator_dp_df = current_fb_df[
                    (current_fb_df["parallelType"].isin(["dp"])) & (current_fb_df["opType"].str.contains("allReduce"))
                ]

                current_tp_unmasked_ratio = self._linearity_ratio(current_mask_df, step_id, "tp")
                baseline_tp_unmasked_ratio = self._linearity_ratio(baseline_mask_df, step_id, "tp")
                current_tp_cp_unmasked_ratio = self._linearity_ratio(current_mask_df, step_id, "tp_cp")
                baseline_tp_cp_unmasked_ratio = self._linearity_ratio(baseline_mask_df, step_id, "tp_cp")

                if (current_tp_unmasked_ratio - baseline_tp_unmasked_ratio) >= 0.03 and (
                    current_tp_cp_unmasked_ratio - baseline_tp_cp_unmasked_ratio
                ) >= 0.03:
                    self._record_text(
                        f"当前tp的未掩盖率:{current_tp_unmasked_ratio}, 基线tp的未掩盖率:{baseline_tp_unmasked_ratio}, "
                        f"tp的差值是: {current_tp_unmasked_ratio - baseline_tp_unmasked_ratio}"
                    )
                    self._record_text(
                        f"当前tp_cp的未掩盖率:{current_tp_cp_unmasked_ratio}, "
                        f"基线tp_cp的未掩盖率:{baseline_tp_cp_unmasked_ratio}, "
                        f"tp_cp的差值是: {current_tp_cp_unmasked_ratio - baseline_tp_cp_unmasked_ratio}"
                    )
                    self._record_text("【判定】:预取阻塞计算 (Prefetch-Compute Overlap劣化)。")
                    self._record_text("【建议】:增大 Micro Batch Size ; 调整参数预取深度 (Prefetch Depth)。")

                for row_index, row_value in enumerate(operator_dp_df.itertuples()):
                    parallel_type = row_value.parallelType
                    current_opType = row_value.opType.replace("hcom_", "").rstrip("_")
                    current_dataType = row_value.dataType
                    current_count = row_value.count
                    operator_start_time = row_value.startNs
                    operator_end_time = row_value.endNs
                    operator_group_rank = row_value.group_rank
                    current_domain = current_value[f"max_{parallel_type}_rank"]
                    baseline_domain = baseline_value[f"max_{parallel_type}_rank"]
                    baseline_fb_df = baseline_value["forward_backward_ret"]

                    baseline_forward_backward_df = baseline_fb_df.loc[
                        (baseline_fb_df["group_rank"] == operator_group_rank)
                        & (baseline_fb_df["parallelType"].isin([parallel_type]))
                        & (baseline_fb_df["opType"].str.contains(current_opType, na=False))
                    ].reset_index(drop=True)
                    if baseline_forward_backward_df.empty:
                        continue

                    current_fb_duration = self._ns_to_ms(operator_end_time - operator_start_time)
                    baseline_forward_backward_start = baseline_forward_backward_df["startNs"].values[0]
                    baseline_forward_backward_end = baseline_forward_backward_df["endNs"].values[0]
                    baseline_fb_duration = self._ns_to_ms(
                        baseline_forward_backward_end - baseline_forward_backward_start
                    )
                    if current_count < 100:
                        ratio_dict = self.comm_lower_bound(
                            current_count,
                            baseline_fb_duration,
                            baseline_domain,
                            current_domain,
                            datatype=current_dataType,
                            op_type=current_opType,
                        )

                        actural_ratio = self._safe_divide(current_fb_duration, baseline_fb_duration)
                        operator_row = self._record_operator(
                            step_id=step_id,
                            phase="阶段二",
                            parallel_type=parallel_type,
                            op_type=current_opType,
                            data_type=current_dataType,
                            count=current_count,
                            group_rank=operator_group_rank,
                            start_ns=operator_start_time,
                            end_ns=operator_end_time,
                            current_domain=current_domain,
                            baseline_domain=baseline_domain,
                            current_duration=current_fb_duration,
                            baseline_duration=baseline_fb_duration,
                            actual_ratio=actural_ratio,
                            theoretical_ratio=ratio_dict["ratio"],
                            is_abnormal=actural_ratio >= 2 * ratio_dict["ratio"],
                            conclusion="出现强制阻塞 (Cross-Group Synchronization Barrier)"
                            if actural_ratio >= 2 * ratio_dict["ratio"]
                            else "",
                            suggestion="修改并行策略，减少跨域强制同步（例如拆分 CP 和 DP 的同步边界）"
                            if actural_ratio >= 2 * ratio_dict["ratio"]
                            else "",
                        )
                        operator_rows.append(operator_row)
                        if actural_ratio >= 2 * ratio_dict["ratio"]:
                            self._record_text("【判定】：出现强制阻塞 (Cross-Group Synchronization Barrier)。")
                            self._record_text(
                                "【建议】：修改并行策略，减少跨域强制同步（例如拆分 CP 和 DP 的同步边界）。"
                            )

        else:
            self._record_text("没有找到 Backward 阶段开始时间！")
        self._record_operator_table("阶段二算子评估表：", operator_rows)

    def _analyze_backward_gradient_phase(self, step_id, current_value, baseline_value):
        # 阶段3 反向传播阶段
        self._record_text("阶段三：")
        operator_rows = []
        backward_gradient_df = current_value["backward_gradient_ret"]
        if backward_gradient_df is None or backward_gradient_df.empty:
            return
        operator_bp_df = backward_gradient_df[
            (backward_gradient_df["parallelType"].isin(["dp", "dp_cp", "ep_dp"]))
            & (backward_gradient_df["opType"].str.contains("reduceScatter"))
        ]
        for row_index, row_value in enumerate(operator_bp_df.itertuples()):
            parallel_type = row_value.parallelType
            current_opType = row_value.opType.replace("hcom_", "").rstrip("_")
            current_dataType = row_value.dataType
            current_count = row_value.count
            operator_start_time = row_value.startNs
            operator_end_time = row_value.endNs
            operator_group_rank = row_value.group_rank
            current_domain = current_value[f"max_{parallel_type}_rank"]
            baseline_domain = baseline_value[f"max_{parallel_type}_rank"]
            baseline_gradient = baseline_value["backward_gradient_ret"]
            if baseline_gradient.empty:
                continue
            baseline_gradient_filter = baseline_gradient.loc[
                (baseline_gradient["group_rank"] == operator_group_rank)
                & (baseline_gradient["parallelType"].isin([parallel_type]))
                & (baseline_gradient["count"] * baseline_domain == current_count * current_domain)
                & (baseline_gradient["opType"].str.contains(current_opType, na=False))
            ].reset_index(drop=True)
            if baseline_gradient_filter.empty:
                continue
            current_row_gradient_duration = self._ns_to_ms(operator_end_time - operator_start_time)
            baseline_gradient_start = baseline_gradient_filter["startNs"].values[0]
            baseline_gradient_end = baseline_gradient_filter["endNs"].values[0]
            baseline_row_gradient_duration = self._ns_to_ms(baseline_gradient_end - baseline_gradient_start)
            ratio_dict = self.comm_lower_bound(
                current_count,
                baseline_row_gradient_duration,
                baseline_domain,
                current_domain,
                datatype=current_dataType,
                op_type=current_opType,
            )
            actual_ratio = self._safe_divide(current_row_gradient_duration, baseline_row_gradient_duration)
            is_abnormal = actual_ratio >= 2 * ratio_dict["ratio"]
            operator_row = self._record_operator(
                step_id=step_id,
                phase="阶段三",
                parallel_type=parallel_type,
                op_type=current_opType,
                data_type=current_dataType,
                count=current_count,
                group_rank=operator_group_rank,
                start_ns=operator_start_time,
                end_ns=operator_end_time,
                current_domain=current_domain,
                baseline_domain=baseline_domain,
                current_duration=current_row_gradient_duration,
                baseline_duration=baseline_row_gradient_duration,
                actual_ratio=actual_ratio,
                theoretical_ratio=ratio_dict["ratio"],
                is_abnormal=is_abnormal,
                conclusion="通信算法选择不当，或者参数面链路冲突" if is_abnormal else "",
                suggestion=(
                    "按拓扑自适应选择通信算法; 降低DP域大小; 优化部署的亲和性; 确认是否开启 TACO-ranktable 及 routeplan"
                )
                if is_abnormal
                else "",
            )
            operator_rows.append(operator_row)
            if actual_ratio >= 2 * ratio_dict["ratio"]:
                self._record_text("【异常原因（当前版本）】：通信算法选择不当，或者参数面链路冲突。")
                self._record_text(
                    "【优化建议】: 按拓扑自适应选择通信算法(如 Herarchical AllGather); "
                    "降低DP域大小, 减少跨亲和组流量; "
                    "优化部署的亲和性，确保同节点/同框内通信优先; "
                    "确认是否开启 TACO-ranktable 及 routeplan。"
                )
        self._record_operator_table("阶段三算子评估表：", operator_rows)

    def _analyze_optimizer_phase(self, step_id, current_value, baseline_value, step_duration):
        # 阶段4 优化器阶段
        self._record_text("阶段四：")
        operator_rows = []
        current_optimizer_df = current_value["backward_optimizer_ret"]
        if current_optimizer_df is None or current_optimizer_df.empty:
            return
        current_optimizer_df["duration"] = current_optimizer_df["endNs"] - current_optimizer_df["startNs"]
        allGather_costed_time = current_optimizer_df["duration"].sum()
        if self._safe_divide(allGather_costed_time, step_duration) > 0.02:
            self._record_text("【判定】：优化器通信过重（ Optimizer State Sharding Overhead ）。")
            self._record_text(
                "【建议】：切换为更轻量的优化器分片策略 (如 ZeRO-2 替代 ZeRO-3); 或使用分片优化器 (Sharded Optimizer) 。"
            )
            operator_optimizer_df = current_optimizer_df[
                (current_optimizer_df["parallelType"].isin(["dp"]))
                & (current_optimizer_df["opType"].str.contains("allReduce"))
            ]
            for row_index, row_value in enumerate(operator_optimizer_df.itertuples()):
                parallel_type = row_value.parallelType
                current_opType = row_value.opType.replace("hcom_", "").rstrip("_")
                current_dataType = row_value.dataType
                current_count = row_value.count
                operator_start_time = row_value.startNs
                operator_end_time = row_value.endNs
                operator_group_rank = row_value.group_rank
                current_domain = current_value[f"max_{parallel_type}_rank"]
                baseline_domain = baseline_value[f"max_{parallel_type}_rank"]
                current_row_optimizer_duration = self._ns_to_ms(operator_end_time - operator_start_time)
                baseline_optimizer_backward = baseline_value["backward_optimizer_ret"]
                baseline_optimizer_filter = baseline_optimizer_backward.loc[
                    (baseline_optimizer_backward["group_rank"] == operator_group_rank)
                    & (baseline_optimizer_backward["parallelType"].isin([parallel_type]))
                    & (baseline_optimizer_backward["opType"].str.contains(current_opType, na=False))
                ].reset_index(drop=True)
                if baseline_optimizer_filter.empty:
                    continue
                baseline_optimizer_start = baseline_optimizer_filter["startNs"].values[0]
                baseline_optimizer_end = baseline_optimizer_filter["endNs"].values[0]
                baseline_row_optimizer_duration = self._ns_to_ms(baseline_optimizer_end - baseline_optimizer_start)
                if current_count < 100:
                    ratio_dict = self.comm_lower_bound(
                        current_count,
                        baseline_row_optimizer_duration,
                        baseline_domain,
                        current_domain,
                        datatype=current_dataType,
                        op_type=current_opType,
                    )
                    actual_ratio = self._safe_divide(current_row_optimizer_duration, baseline_row_optimizer_duration)
                    is_abnormal = actual_ratio >= 2 * ratio_dict['ratio']
                    operator_row = self._record_operator(
                        step_id=step_id,
                        phase="阶段四",
                        parallel_type=parallel_type,
                        op_type=current_opType,
                        data_type=current_dataType,
                        count=current_count,
                        group_rank=operator_group_rank,
                        start_ns=operator_start_time,
                        end_ns=operator_end_time,
                        current_domain=current_domain,
                        baseline_domain=baseline_domain,
                        current_duration=current_row_optimizer_duration,
                        baseline_duration=baseline_row_optimizer_duration,
                        actual_ratio=actual_ratio,
                        theoretical_ratio=ratio_dict["ratio"],
                        is_abnormal=is_abnormal,
                        conclusion="出现强制阻塞 (Cross-Group Synchronization Barrier)" if is_abnormal else "",
                        suggestion="修改并行策略，减少跨域强制同步（例如拆分 CP 与 DP 的同步时间）"
                        if is_abnormal
                        else "",
                    )
                    operator_rows.append(operator_row)
                    if is_abnormal:
                        self._record_text("【判定】：出现强制阻塞 (Cross-Group Synchronization Barrier)。")
                        self._record_text("【建议】：修改并行策略，减少跨域强制同步（例如拆分 CP 与 DP 的同步时间）。")
        self._record_operator_table("阶段四算子评估表：", operator_rows)
