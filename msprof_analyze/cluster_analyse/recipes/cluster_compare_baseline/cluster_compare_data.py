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
    def _get_step_df(self, data_map):
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
        if df is None or df.empty or column not in df.columns:
            return default
        return df[column].values[0]

    @staticmethod
    def _get_rank_count(group_info_df, group_name):
        if group_info_df is None or group_info_df.empty:
            return 0
        if "group_name" not in group_info_df.columns or "rank_count" not in group_info_df.columns:
            return 0
        values = group_info_df[group_info_df["group_name"] == group_name]["rank_count"].values
        return values[0] if len(values) else 0

    def get_linearity_df(self, data_map, analysis_class, target_step_id: int = None) -> pd.DataFrame:
        """
        Compute the linearity of communication operators.
        使用共享工具类实现
        """
        return LinearityUtils.compute_linearity_df(
            data_map=data_map,
            analysis_class=analysis_class,
            parallel_types=self.parallel_types,
            step_columns=self.step_columns,
            parallel_col_name=self.PARALLEL_COL_NAME,
            target_step_id=target_step_id,
            use_merge=False,  # 保持原有逻辑，不合并通信区间
        )

    def get_total_step_duration(self, data_map: dict):
        """
        从 data_map 中获取 step 总时长（纳秒）
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
        分析单个数据源，按 step 返回结果
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
        communication_df["group_rank"] = communication_df.sort_values(["startNs"]).groupby("parallelType").cumcount()

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

            analyse_ret = {
                "start_time": start_time,
                "end_time": end_time,
                "max_dp_rank": max_dp_rank,
                "max_dp_cp_rank": max_dp_cp_rank,
                "max_ep_dp_rank": max_ep_dp_rank,
                "communication": communication_df,
                "forward_ret": pd.DataFrame(),
                "forward_backward_ret": pd.DataFrame(),
                "backward_gradient_ret": pd.DataFrame(),
                "backward_optimizer_ret": pd.DataFrame(),
            }

            if end_time - start_time == 0:
                continue

            df = communication_df[
                (communication_df["startNs"] >= start_time) & (communication_df["endNs"] <= end_time)
            ].copy()
            df = df.sort_values(["startNs"]).reset_index(drop=True)
            df["group_rank"] = df.groupby("parallelType").cumcount()

            if df.empty:
                continue

            self._record_text(f"========== Step {step_id} ==========")

            tp_allReduce = df[(df["parallelType"] == "tp") & (df["opType"].str.contains("allReduce"))]
            if not tp_allReduce.empty:
                tp_allReduce_start = tp_allReduce["startNs"].min()
                self._record_text(f"第一个TP broadcast结束时间: {tp_allReduce_start}")

                result1 = df[
                    (df["parallelType"].isin(["dp_cp", "ep_dp"]))
                    & (df["opType"].str.contains("allGather"))
                    & (df["endNs"] < tp_allReduce_start)
                ].copy()

                if not result1.empty:
                    analyse_ret["forward_ret"] = result1
                    self._record_text(f"需求1结果: {len(result1)} 个")
                else:
                    self._record_text(f"需求1结果: {len(result1)} 个")
            else:
                self._record_text("需求1: 没有找到TP broadcast")

            tp_reference_end = -1
            tp_allreduce = df[
                (df["parallelType"] == "tp") & (df["count"] > 100) & (df["opType"].str.contains("allReduce", na=False))
            ]
            last_allreduce_idx = tp_allreduce.index[-1] if not tp_allreduce.empty else -1

            if last_allreduce_idx != -1:
                prev_data = df.loc[: last_allreduce_idx - 1]
                tp_non_allreduce = prev_data[
                    (prev_data["parallelType"] == "tp") & (~prev_data["opType"].str.contains("allReduce", na=False))
                ]
                # 确定参考时间
                tp_reference_end = (
                    tp_non_allreduce.iloc[-1]["startNs"]
                    if not tp_non_allreduce.empty
                    else df.loc[last_allreduce_idx, "startNs"]
                )
                dp_ep_reduce_scatter = df[
                    (df["parallelType"].isin(["dp_cp", "ep_dp"]))
                    & (df["opType"].str.contains("reduceScatter"))
                    & (df["startNs"] > tp_reference_end)
                    & (df["endNs"] < end_time)
                ].copy()

                if not dp_ep_reduce_scatter.empty:
                    dp_ep_reduce_scatter = dp_ep_reduce_scatter.sort_values("startNs")
                    first_start = dp_ep_reduce_scatter.iloc[0]["startNs"]
                    self._record_text(f"第一个符合条件的reduce_scatter开始时间: {first_start}")

                    result3 = df[
                        (df["parallelType"].isin(["dp_cp", "ep_dp"]))
                        & (df["opType"].str.contains("reduceScatter"))
                        & (df["startNs"] >= first_start)
                    ].copy()

                    if not result3.empty:
                        analyse_ret["backward_gradient_ret"] = result3
                        self._record_text(f"需求3结果: {len(result3)} 个")
                    else:
                        self._record_text(f"需求3结果: {len(result3)} 个")
                else:
                    self._record_text("需求3: 没有找到TP结束后仍在通信的reduce_scatter")
            else:
                self._record_text("TP域没有找到allReduce算子")

            if tp_reference_end != -1:
                result4 = df[
                    (
                        ((df["parallelType"].isin(["dp_cp", "ep_dp"])) & (df["opType"].str.contains("allGather")))
                        | ((df["parallelType"] == "dp") & (df["opType"].str.contains("allReduce")))
                    )
                    & (df["startNs"] > tp_reference_end)
                    & (df["endNs"] < end_time)
                ].copy()

                if not result4.empty:
                    analyse_ret["backward_optimizer_ret"] = result4
                    self._record_text(f"需求4结果: {len(result4)} 个")
                else:
                    self._record_text(f"需求4结果: {len(result4)} 个")
            else:
                self._record_text("需求4: 没有找到TP域对应的allReduce算子事件")

            if not result1.empty:
                forward_end = result1["endNs"].max()

                backward_starts = []
                if not result3.empty:
                    backward_starts.append(result3["startNs"].min())
                if not result4.empty:
                    backward_starts.append(result4["startNs"].min())

                if tp_reference_end != -1:
                    self._record_text(f"需求2区间: Forward结束={forward_end}, Backward开始={tp_reference_end}")

                    result2 = df[
                        (
                            (
                                (df["parallelType"].isin(["dp_cp", "ep_dp"]))
                                & (df["opType"].str.contains("allGather|reduceScatter"))
                            )
                            | ((df["parallelType"] == "dp") & (df["opType"].str.contains("allReduce")))
                        )
                        & ((df["startNs"] > forward_end) & (df["endNs"] < tp_reference_end))
                    ].copy()

                    if not result2.empty:
                        analyse_ret["forward_backward_ret"] = result2
                        self._record_text(f"需求2结果: {len(result2)} 个")
                    else:
                        self._record_text(f"需求2结果: {len(result2)} 个")
                else:
                    self._record_text("需求2: 没有找到TP域对应的allReduce算子事件")
            else:
                self._record_text("需求2: 无法确定Forward结束边界，因为需求1结果为空")
            dict_ret[step_id] = analyse_ret
        return dict_ret
