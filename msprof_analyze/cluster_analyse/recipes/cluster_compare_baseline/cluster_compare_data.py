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

import pandas as pd

from msprof_analyze.prof_common.constant import Constant
from msprof_analyze.prof_common.database_service import DatabaseService
from msprof_analyze.cluster_analyse.recipes.base_recipe_analysis import BaseRecipeAnalysis
from msprof_analyze.prof_common.logger import get_logger
from msprof_analyze.cluster_analyse.common_func.linearity_utils import LinearityUtils
from msprof_analyze.prof_exports.computational_op_masking_export import CommunicationOpWithExport
from msprof_analyze.prof_exports.computational_op_masking_export import ParallelGroupInfoExport


logger = get_logger()


class ClusterCompareDataMixin:
    """
    Data-classification mixin for the cluster baseline comparison recipe.

    This mixin is responsible for partitioning the communication operators of
    each profiling step into four phase buckets that the analysis layer
    (``ClusterCompareBaseline``) consumes:

        - forward_ret              : forward-phase communication ops
        - forward_backward_ret     : ops in the forward->backward transition
        - backward_gradient_ret    : backward gradient (reduceScatter) ops
        - backward_optimizer_ret   : optimizer-phase communication ops

    It also provides the linearity DataFrame and the total step duration used
    as comparison anchors.

    NOTE:
        ``_analyze_data_by_step`` relies on attributes provided by the composing
        class (``step_columns`` / ``parallel_types`` / ``PARALLEL_COL_NAME``).
        User-visible report text is emitted by ``ClusterCompareReportMixin``,
        not by this mixin; here only debug-level logging is produced.
    """

    def _get_step_df(self, data_map):
        """
        Return the step-time DataFrame and the profiler DB path for a data map.

        If ``STEP_RANGE`` overrides the default range, the single overridden
        range is returned as a one-row DataFrame instead of querying the DB.
        """
        if not data_map:
            return pd.DataFrame(), None

        profiler_db_path = data_map.get(Constant.PROFILER_DB_PATH)
        step_range = data_map.get(Constant.STEP_RANGE)
        if step_range != BaseRecipeAnalysis.DEFAULT_STEP_RANGE:
            return pd.DataFrame.from_dict([step_range]), profiler_db_path

        data_service = DatabaseService(profiler_db_path, step_range)
        data_service.add_table_for_query(Constant.TABLE_STEP_TIME, self.step_columns)
        return data_service.query_data().get(Constant.TABLE_STEP_TIME, pd.DataFrame()), profiler_db_path

    @staticmethod
    def _first_value(df, column, default=None):
        """Return the first value of ``column`` in ``df``, or ``default``."""
        if df is None or df.empty or column not in df.columns:
            return default
        return df[column].values[0]

    @staticmethod
    def _get_rank_count(group_info_df, group_name):
        """
        Return the rank count of a parallel group, or 0 if not found.

        The group information table is expected to contain ``group_name`` and
        ``rank_count`` columns; missing table/columns yield 0 so that the
        downstream comparison degrades gracefully.
        """
        if group_info_df is None or group_info_df.empty:
            return 0
        if "group_name" not in group_info_df.columns or "rank_count" not in group_info_df.columns:
            return 0
        values = group_info_df[group_info_df["group_name"] == group_name]["rank_count"].values
        return values[0] if len(values) else 0

    def get_linearity_df(self, data_map, analysis_class, target_step_id: int = None) -> pd.DataFrame:
        """
        Compute the linearity of communication operators.

        Delegates to the shared ``LinearityUtils.compute_linearity_df`` helper,
        forwarding the composing class's ``parallel_types`` / ``step_columns`` /
        ``PARALLEL_COL_NAME``. ``use_merge`` is kept as False to preserve the
        original per-operator (non-merged) semantics.
        """
        return LinearityUtils.compute_linearity_df(
            data_map=data_map,
            analysis_class=analysis_class,
            parallel_types=self.parallel_types,
            step_columns=self.step_columns,
            parallel_col_name=self.PARALLEL_COL_NAME,
            target_step_id=target_step_id,
            use_merge=False,  # Keep the original logic: do not merge communication intervals
        )

    def get_total_step_duration(self, data_map: dict):
        """
        Return the shortest step duration (in ns) and its step id from ``data_map``.

        The shortest step is used as the comparison anchor because it is the
        least affected by outliers / transient stalls.
        """
        step_df, profiler_db_path = self._get_step_df(data_map)

        if step_df is None or step_df.empty:
            logger.warning("There is no TABLE_STEP_TIME data in %s.", profiler_db_path)
            return 0, None

        step_df['duration'] = step_df['endNs'] - step_df['startNs']
        min_idx = step_df['duration'].idxmin()
        min_duration = step_df.loc[min_idx, 'duration']
        min_step_id = step_df.loc[min_idx, 'id']
        return min_duration, min_step_id

    def _analyze_data_by_step(self, data_map, analysis_class, target_step_id: int = None):
        """
        Classify communication operators per step into four phase buckets.

        For every step, the returned dict contains:
            start_time / end_time            : step boundaries (ns)
            max_dp_rank / max_dp_cp_rank /
            max_ep_dp_rank                   : rank counts of the DP-related groups
            forward_ret                      : forward-phase ops
            forward_backward_ret             : forward->backward transition ops
            backward_gradient_ret            : backward gradient (reduceScatter) ops
            backward_optimizer_ret           : optimizer-phase ops

        Only the four buckets are returned; callers that need the full
        communication DataFrame must fetch it themselves.
        """
        step_df, profiler_db_path = self._get_step_df(data_map)
        step_range = data_map.get(Constant.STEP_RANGE) if data_map else None

        if step_df is None or step_df.empty:
            logger.warning("There is no TABLE_STEP_TIME data in %s.", profiler_db_path)
            return {}

        if target_step_id is not None:
            step_df = step_df[step_df['id'] == target_step_id]
            if step_df.empty:
                logger.warning("No step found with id: %s", target_step_id)
                return {}

        communication_df = CommunicationOpWithExport(profiler_db_path, analysis_class, step_range).read_export_db()
        if communication_df is None or communication_df.empty:
            logger.warning("There is no TABLE_COMMUNICATION_OP data in %s.", profiler_db_path)
            return {}

        # Sort once by startNs outside the loop, then use searchsorted inside
        # the loop to slice the per-step candidates. This avoids re-filtering
        # the full table and re-sorting for every step.
        communication_df = communication_df.sort_values("startNs").reset_index(drop=True)
        start_ns_arr = communication_df["startNs"].to_numpy()

        group_info_df = ParallelGroupInfoExport(profiler_db_path, analysis_class, step_range).read_export_db()
        group_info_df = group_info_df if group_info_df is not None else pd.DataFrame()
        max_dp_rank = self._get_rank_count(group_info_df, "dp")
        max_dp_cp_rank = self._get_rank_count(group_info_df, "dp_cp")
        max_ep_dp_rank = self._get_rank_count(group_info_df, "ep_dp")

        dict_ret = {}
        for _, step_row in step_df.iterrows():
            result1 = pd.DataFrame()
            result2 = pd.DataFrame()
            result3 = pd.DataFrame()
            result4 = pd.DataFrame()
            start_time = step_row["startNs"]
            end_time = step_row["endNs"]
            step_id = step_row["id"]

            if end_time - start_time == 0:
                continue

            # Locate candidates via binary search on startNs, then filter by the
            # endNs upper bound so only ops fully contained in this step remain.
            left = start_ns_arr.searchsorted(start_time, side="left")
            right = start_ns_arr.searchsorted(end_time, side="right")
            candidate = communication_df.iloc[left:right]
            df = candidate[candidate["endNs"] <= end_time].copy()
            # communication_df is already sorted by startNs; slicing preserves
            # the order, so no further sort is needed here.
            df = df.reset_index(drop=True)

            if df.empty:
                continue

            # FIX: recompute cumcount per step so ``group_rank`` is restored.
            # Downstream ``_analyze_*_phase`` relies on ``row_value.group_rank``
            # and matches it against the baseline; the numbering must be per
            # step rather than global.
            df["group_rank"] = df.groupby("parallelType").cumcount()

            analyse_ret = {
                "start_time": start_time,
                "end_time": end_time,
                "max_dp_rank": max_dp_rank,
                "max_dp_cp_rank": max_dp_cp_rank,
                "max_ep_dp_rank": max_ep_dp_rank,
                "forward_ret": pd.DataFrame(),
                "forward_backward_ret": pd.DataFrame(),
                "backward_gradient_ret": pd.DataFrame(),
                "backward_optimizer_ret": pd.DataFrame(),
            }

            logger.debug("========== Step %s ==========", step_id)

            # ---------------------------------------------------------------
            # Bucket 1 (forward phase): allGather ops of dp_cp / ep_dp that
            # finish before the first TP allReduce starts. The start of that
            # first TP allReduce is treated as the forward/backward boundary.
            # ---------------------------------------------------------------
            tp_allReduce = df[
                (df["parallelType"] == "tp") & (df["opType"].str.contains("allReduce", na=False, regex=False))
            ]
            if not tp_allReduce.empty:
                tp_allReduce_start = tp_allReduce["startNs"].min()
                logger.debug("End time of the first TP broadcast: %s", tp_allReduce_start)

                result1 = df[
                    (df["parallelType"].isin(["dp_cp", "ep_dp"]))
                    & (df["opType"].str.contains("allGather", na=False, regex=False))
                    & (df["endNs"] < tp_allReduce_start)
                ].copy()

                if not result1.empty:
                    analyse_ret["forward_ret"] = result1
                logger.debug("Bucket 1 result: %s ops", len(result1))
            else:
                logger.debug("Bucket 1: no TP broadcast found")

            # ---------------------------------------------------------------
            # Determine the reference boundary between forward and backward:
            # the startNs of the last non-allReduce TP op preceding the last
            # large TP allReduce. If no such op exists, fall back to the startNs
            # of that allReduce itself.
            # NOTE: this intentionally differs from the PR description's
            # "start of the previous op" wording; the original behavior is kept.
            # ---------------------------------------------------------------
            tp_reference_end = None
            tp_allreduce = df[
                (df["parallelType"] == "tp")
                & (df["count"] > 100)
                & (df["opType"].str.contains("allReduce", na=False, regex=False))
            ]
            last_allreduce_idx = tp_allreduce.index[-1] if not tp_allreduce.empty else None

            if last_allreduce_idx is not None:
                prev_data = df.loc[: last_allreduce_idx - 1]
                tp_non_allreduce = prev_data[
                    (prev_data["parallelType"] == "tp")
                    & (~prev_data["opType"].str.contains("allReduce", na=False, regex=False))
                ]
                # If there is no non-allReduce TP op before the last large
                # allReduce, fall back to that allReduce's own startNs.
                # NOTE: this intentionally differs from the PR description's
                # "start of the previous op" wording; the original behavior is kept.
                tp_reference_end = (
                    tp_non_allreduce.iloc[-1]["startNs"]
                    if not tp_non_allreduce.empty
                    else df.loc[last_allreduce_idx, "startNs"]
                )

                # -----------------------------------------------------------
                # Bucket 3 (backward gradient): reduceScatter ops of
                # dp_cp / ep_dp that start after the TP reference boundary.
                # The upper bound (endNs < end_time) is added for consistency
                # with buckets 1/2/4 so ops never leak across step boundaries.
                # -----------------------------------------------------------
                dp_ep_reduce_scatter = df[
                    (df["parallelType"].isin(["dp_cp", "ep_dp"]))
                    & (df["opType"].str.contains("reduceScatter", na=False, regex=False))
                    & (df["startNs"] > tp_reference_end)
                    & (df["endNs"] < end_time)
                ].copy()

                if not dp_ep_reduce_scatter.empty:
                    dp_ep_reduce_scatter = dp_ep_reduce_scatter.sort_values("startNs")
                    first_start = dp_ep_reduce_scatter.iloc[0]["startNs"]
                    logger.debug("Start time of the first qualifying reduceScatter: %s", first_start)

                    # Apply the same endNs < end_time upper bound as buckets
                    # 1/2/4 to avoid counting across step boundaries.
                    result3 = df[
                        (df["parallelType"].isin(["dp_cp", "ep_dp"]))
                        & (df["opType"].str.contains("reduceScatter", na=False, regex=False))
                        & (df["startNs"] >= first_start)
                        & (df["endNs"] < end_time)
                    ].copy()

                    if not result3.empty:
                        analyse_ret["backward_gradient_ret"] = result3
                    logger.debug("Bucket 3 result: %s ops", len(result3))
                else:
                    logger.debug("Bucket 3: no reduceScatter still running after the TP phase")
            else:
                logger.debug("No allReduce op found in the TP domain")

            # ---------------------------------------------------------------
            # Bucket 4 (optimizer phase): after the TP reference boundary,
            # allGather of dp_cp / ep_dp, or allReduce of dp.
            # ---------------------------------------------------------------
            if tp_reference_end is not None:
                result4 = df[
                    (
                        (
                            (df["parallelType"].isin(["dp_cp", "ep_dp"]))
                            & (df["opType"].str.contains("allGather", na=False, regex=False))
                        )
                        | (
                            (df["parallelType"] == "dp")
                            & (df["opType"].str.contains("allReduce", na=False, regex=False))
                        )
                    )
                    & (df["startNs"] > tp_reference_end)
                    & (df["endNs"] < end_time)
                ].copy()

                if not result4.empty:
                    analyse_ret["backward_optimizer_ret"] = result4
                logger.debug("Bucket 4 result: %s ops", len(result4))
            else:
                logger.debug("Bucket 4: no TP allReduce event found")

            # ---------------------------------------------------------------
            # Bucket 2 (forward->backward transition): ops in the window
            # (forward_end, tp_reference_end), i.e. dp_cp / ep_dp allGather or
            # reduceScatter, or dp allReduce. This window only makes sense when
            # bucket 1 is non-empty, since forward_end comes from bucket 1.
            # ---------------------------------------------------------------
            if not result1.empty:
                forward_end = result1["endNs"].max()
                if tp_reference_end is not None:
                    logger.debug("Bucket 2 window: forward_end=%s, backward_start=%s", forward_end, tp_reference_end)

                    result2 = df[
                        (
                            (
                                (df["parallelType"].isin(["dp_cp", "ep_dp"]))
                                & (df["opType"].str.contains("allGather|reduceScatter", na=False, regex=False))
                            )
                            | (
                                (df["parallelType"] == "dp")
                                & (df["opType"].str.contains("allReduce", na=False, regex=False))
                            )
                        )
                        & ((df["startNs"] > forward_end) & (df["endNs"] < tp_reference_end))
                    ].copy()

                    if not result2.empty:
                        analyse_ret["forward_backward_ret"] = result2
                    logger.debug("Bucket 2 result: %s ops", len(result2))
                else:
                    logger.debug("Bucket 2: no TP allReduce event found")
            else:
                logger.debug("Bucket 2: cannot determine forward_end because bucket 1 is empty")
            dict_ret[step_id] = analyse_ret
        return dict_ret
