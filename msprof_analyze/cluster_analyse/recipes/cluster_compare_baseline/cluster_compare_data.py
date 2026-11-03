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

    This mixin partitions the communication operators of each profiling step
    into four phase buckets. Bucket filters are shared with the analysis side
    via ``PHASE_FILTERS`` so both sides cannot drift apart.

    Empty buckets are initialized with the expected columns so consumers can
    access columns safely even when a bucket is empty.
    """

    BUCKET_COLUMNS = ["parallelType", "opType", "dataType", "count", "startNs", "endNs", "group_rank"]

    # Shared phase -> (parallelTypes, opType substrings) filter definition.
    # Both the data side (bucket collection) and the analysis side (phase
    # iteration) use this map, so collected operators are always analyzed.
    #
    # forward_backward / optimizer intentionally only contain dp allReduce:
    # dp_cp / ep_dp allGather/reduceScatter are window-boundary operators and
    # are not diagnosed in those two phases.
    PHASE_FILTERS = {
        "forward": (["dp_cp", "ep_dp"], ["allGather"]),
        "forward_backward": (["dp"], ["allReduce"]),
        "backward_gradient": (["dp", "dp_cp", "ep_dp"], ["reduceScatter"]),
        "optimizer": (["dp"], ["allReduce"]),
    }

    @staticmethod
    def _reindex_group_rank(bucket):
        """Reset ``group_rank`` to a per-parallelType cumcount within the bucket."""
        if bucket is None or bucket.empty:
            return bucket
        bucket = bucket.reset_index(drop=True)
        bucket["group_rank"] = bucket.groupby("parallelType").cumcount()
        return bucket

    @classmethod
    def _empty_bucket(cls):
        """Return an empty bucket with the expected columns pre-initialized."""
        return pd.DataFrame(columns=cls.BUCKET_COLUMNS)

    def _get_step_df(self, data_map):
        """Return the step-time DataFrame and the profiler DB path for a data map."""
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
        """Return the rank count of a parallel group, or 0 if not found."""
        if group_info_df is None or group_info_df.empty:
            return 0
        if "group_name" not in group_info_df.columns or "rank_count" not in group_info_df.columns:
            return 0
        values = group_info_df[group_info_df["group_name"] == group_name]["rank_count"].values
        return values[0] if len(values) else 0

    def get_linearity_df(self, data_map, analysis_class, target_step_id: int = None) -> pd.DataFrame:
        """Compute the linearity of communication operators via LinearityUtils."""
        return LinearityUtils.compute_linearity_df(
            data_map=data_map,
            analysis_class=analysis_class,
            parallel_types=self.parallel_types,
            step_columns=self.step_columns,
            parallel_col_name=self.PARALLEL_COL_NAME,
            target_step_id=target_step_id,
            use_merge=False,
        )

    def get_total_step_duration(self, data_map: dict):
        """Return the shortest step duration (ns) and its step id from ``data_map``."""
        step_df, profiler_db_path = self._get_step_df(data_map)

        if step_df is None or step_df.empty:
            logger.warning("There is no TABLE_STEP_TIME data in %s.", profiler_db_path)
            return 0, None

        step_df['duration'] = step_df['endNs'] - step_df['startNs']
        min_idx = step_df['duration'].idxmin()
        min_duration = step_df.loc[min_idx, 'duration']
        min_step_id = step_df.loc[min_idx, 'id']
        return min_duration, min_step_id

    @classmethod
    def _phase_filter(cls, phase, df):
        """Return the subset of ``df`` that belongs to the given phase."""
        parallel_types, op_substrings = cls.PHASE_FILTERS[phase]
        mask = df["parallelType"].isin(parallel_types)
        op_mask = pd.Series(False, index=df.index)
        for sub in op_substrings:
            op_mask = op_mask | df["opType"].str.contains(sub, na=False, regex=False)
        return df[mask & op_mask].copy()

    def _analyze_data_by_step(self, data_map, analysis_class, target_step_id: int = None):
        """
        Classify communication operators per step into four phase buckets.

        Bucket membership is defined by ``PHASE_FILTERS`` and shared with the
        analysis side. Empty buckets are pre-initialized with the expected
        columns. Only the given ``target_step_id`` is analyzed when provided.
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

        communication_df = communication_df.sort_values("startNs").reset_index(drop=True)
        start_ns_arr = communication_df["startNs"].to_numpy()

        group_info_df = ParallelGroupInfoExport(profiler_db_path, analysis_class, step_range).read_export_db()
        group_info_df = group_info_df if group_info_df is not None else pd.DataFrame()
        max_dp_rank = self._get_rank_count(group_info_df, "dp")
        max_dp_cp_rank = self._get_rank_count(group_info_df, "dp_cp")
        max_ep_dp_rank = self._get_rank_count(group_info_df, "ep_dp")

        dict_ret = {}
        for _, step_row in step_df.iterrows():
            start_time = step_row["startNs"]
            end_time = step_row["endNs"]
            step_id = step_row["id"]

            if end_time - start_time == 0:
                continue

            left = start_ns_arr.searchsorted(start_time, side="left")
            right = start_ns_arr.searchsorted(end_time, side="right")
            candidate = communication_df.iloc[left:right]
            df = candidate[candidate["endNs"] <= end_time].copy().reset_index(drop=True)

            if df.empty:
                continue

            df["group_rank"] = df.groupby("parallelType").cumcount()

            analyse_ret = {
                "start_time": start_time,
                "end_time": end_time,
                "max_dp_rank": max_dp_rank,
                "max_dp_cp_rank": max_dp_cp_rank,
                "max_ep_dp_rank": max_ep_dp_rank,
                "forward_ret": self._empty_bucket(),
                "forward_backward_ret": self._empty_bucket(),
                "backward_gradient_ret": self._empty_bucket(),
                "backward_optimizer_ret": self._empty_bucket(),
            }

            logger.debug("========== Step %s ==========", step_id)

            # TP reference boundary is still needed to split forward/backward.
            tp_allReduce = df[
                (df["parallelType"] == "tp") & (df["opType"].str.contains("allReduce", na=False, regex=False))
            ]
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
                tp_reference_end = (
                    tp_non_allreduce.iloc[-1]["startNs"]
                    if not tp_non_allreduce.empty
                    else df.loc[last_allreduce_idx, "startNs"]
                )

            forward_end = None
            if not tp_allReduce.empty:
                tp_allReduce_start = tp_allReduce["startNs"].min()
                forward_bucket = self._phase_filter("forward", df)
                forward_bucket = forward_bucket[forward_bucket["endNs"] < tp_allReduce_start]
                if not forward_bucket.empty:
                    analyse_ret["forward_ret"] = self._reindex_group_rank(forward_bucket)
                    forward_end = forward_bucket["endNs"].max()

            if tp_reference_end is not None:
                gradient_bucket = self._phase_filter("backward_gradient", df)
                gradient_bucket = gradient_bucket[gradient_bucket["startNs"] > tp_reference_end]
                if not gradient_bucket.empty:
                    analyse_ret["backward_gradient_ret"] = self._reindex_group_rank(gradient_bucket)

                optimizer_bucket = self._phase_filter("optimizer", df)
                optimizer_bucket = optimizer_bucket[optimizer_bucket["startNs"] > tp_reference_end]
                if not optimizer_bucket.empty:
                    analyse_ret["backward_optimizer_ret"] = self._reindex_group_rank(optimizer_bucket)

            if forward_end is not None and tp_reference_end is not None:
                fb_bucket = self._phase_filter("forward_backward", df)
                fb_bucket = fb_bucket[(fb_bucket["startNs"] > forward_end) & (fb_bucket["endNs"] < tp_reference_end)]
                if not fb_bucket.empty:
                    analyse_ret["forward_backward_ret"] = self._reindex_group_rank(fb_bucket)

            dict_ret[step_id] = analyse_ret
        return dict_ret
