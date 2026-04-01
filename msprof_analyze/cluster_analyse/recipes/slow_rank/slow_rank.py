# Copyright (c) 2025, Huawei Technologies Co., Ltd.
# All rights reserved.
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
from collections import defaultdict

import pandas as pd
import numpy as np

from msprof_analyze.cluster_analyse.recipes.base_recipe_analysis import BaseRecipeAnalysis
from msprof_analyze.prof_common.constant import Constant
from msprof_analyze.prof_common.logger import get_logger
from msprof_analyze.prof_exports.cluster_time_summary_export import CommunicationTimeExport
from msprof_analyze.cluster_analyse.recipes.slow_rank.dixon_table import DIXON_TABLE_995

logger = get_logger()


def judge_norm(time_list, threshold=3):
    t_max = max(time_list)
    t_min = min(time_list)
    t_mean = np.mean(time_list)
    t_std = np.std(time_list)
    threshold_high = t_mean + threshold * t_std
    threshold_low = t_mean - threshold * t_std

    # 耗时低于下阈值的卡认为是慢卡
    outliers_idx = [i for i, time in enumerate(time_list) if time < threshold_low]

    # 如果存在高于上阈值的卡，则将耗时最短的卡加到慢卡的list中
    if t_max > threshold_high:
        if time_list.index(t_min) not in outliers_idx:
            outliers_idx.append(time_list.index(t_min))
    return outliers_idx


def judge_dixon(time_list):
    n = len(time_list)
    if n in [0, 1, 2]:
        return []
    sorted_list = sorted(time_list)

    # 判断计算检验指标时分母是否可能为0
    if len(set(sorted_list)) <= 3:
        return []

    # 计算狄克逊检验的检验指标，次小值和最小值差，比上最大值和最小值的差。根据数据数量改变次小值和最大值的选取
    if n <= Constant.MAX_DIXON_NUM:
        if n <= Constant.DIXON_THRESHOLD_1:
            flag = (sorted_list[1] - sorted_list[0]) / (sorted_list[-1] - sorted_list[0]) \
                if (sorted_list[-1] - sorted_list[0]) else 0
        elif n <= Constant.DIXON_THRESHOLD_2:
            flag = (sorted_list[1] - sorted_list[0]) / (sorted_list[-2] - sorted_list[0]) \
                if (sorted_list[-2] - sorted_list[0]) else 0
        elif n <= Constant.DIXON_THRESHOLD_3:
            flag = (sorted_list[2] - sorted_list[0]) / (sorted_list[-2] - sorted_list[0]) \
                if (sorted_list[-2] - sorted_list[0]) else 0
        else:
            flag = (sorted_list[2] - sorted_list[0]) / (sorted_list[-3] - sorted_list[0]) \
                if (sorted_list[-3] - sorted_list[0]) else 0
        
        # 根据数据数量查表，若计算的检验指标较大，则认为有异常值，耗时最短的卡是慢卡
        if flag > DIXON_TABLE_995[n]:
            return [time_list.index(sorted_list[0])]
    return []


def judge_slow_rank(time_list):
    """根据time list长度 选择狄克逊检验或三倍标准差"""
    if len(time_list) <= Constant.MAX_DIXON_NUM:
        return judge_dixon(time_list)
    else:
        return judge_norm(time_list)


class SlowRankAnalysis(BaseRecipeAnalysis):
    def __init__(self, params):
        super().__init__(params)
        self.perpector_df = None
        self.stat_df = None
        logger.info("Slow Rank Analysis init.")

    @property
    def base_dir(self):
        return os.path.basename(os.path.dirname(__file__))

    def reducer_func(self, mapper_res):
        mapper_res = list(filter(lambda df: df is not None, mapper_res))
        if not mapper_res:
            logger.error("Mapper data is None.")
            return None
        concated_df = pd.concat(mapper_res)
        return concated_df

    def run(self, context):
        if self._prof_type == Constant.MSPROF:
            logger.warning("Slow rank analysis do not support msprof db now.")
            return

        mapper_res = self.mapper_func(context)
        comm_ops_df = self.reducer_func(mapper_res)
        if comm_ops_df is None:
            return

        analyzer = SlowRankVoteAnalysis(comm_ops_df)
        self.perpector_df, self.stat_df = analyzer.run()
        if self.perpector_df is None or self.perpector_df.empty:
            logger.info(f"No slow rank found, skip data dump.")
            return
        if self._export_type == Constant.DB:
            self.save_db()
        elif self._export_type == Constant.NOTEBOOK:
            self.save_csv()
            self.save_notebook()
        elif self._export_type == Constant.TEXT:
            self.save_csv()
        else:
            logger.error("SlowRank analysis is not supported for notebook export type.")

    def save_db(self, ):
        self.dump_data(self.perpector_df, Constant.DB_CLUSTER_COMMUNICATION_ANALYZER, "SlowRank")
        self.dump_data(self.stat_df, Constant.DB_CLUSTER_COMMUNICATION_ANALYZER, "SlowOpStats", index=False)

    def save_notebook(self):
        self.create_notebook("stats.ipynb")
        self.add_helper_file("cluster_display.py")

    def save_csv(self):
        self.dump_data(self.perpector_df, "rank_stats.csv")
        self.dump_data(self.stat_df, "slow_op_stats.csv", index=False)

    def _mapper_func(self, data_map, analysis_class):
        profiler_db_path = data_map.get(Constant.PROFILER_DB_PATH)
        step_range = data_map.get(Constant.STEP_RANGE)
        df = CommunicationTimeExport(profiler_db_path, analysis_class, step_range).read_export_db()
        return df


class SlowRankVoteAnalysis:
    def __init__(self, comm_ops):
        self.comm_ops = comm_ops

    @staticmethod
    def calculate_basic_stats(time_list):
        """计算基础统计量"""
        if not time_list:
            return {}

        series = pd.Series(time_list)
        return {
            'Count': len(time_list),
            'MeanNs': series.mean(),
            'StdNs': series.std(),
            'MinNs': series.min(),
            'Q1Ns': series.quantile(0.25),
            'MedianNs': series.median(),
            'Q3Ns': series.quantile(0.75),
            'MaxNs': series.max(),
            'SumNs': series.sum()
        }

    def grouping_ops(self):
        """按照通信域、算子名称对通信算子进行分组"""
        grouped_ops_dict = defaultdict(lambda: defaultdict(list))
        self.comm_ops = self.comm_ops[~self.comm_ops["opName"].str.contains("send")]
        self.comm_ops = self.comm_ops[~self.comm_ops["opName"].str.contains("receive")]
        grouped_df = self.comm_ops.groupby("groupName")
        exclude_groups = []
        for group_name in grouped_df.groups.keys():
            ops_groupby_group_name = grouped_df.get_group(group_name)
            ops_num = ops_groupby_group_name.groupby("opName").size().values
            if len(set(ops_num)) > 1:
                exclude_groups.append(group_name)
        for exclude_group in exclude_groups:
            self.comm_ops.drop(self.comm_ops[self.comm_ops["groupName"] == exclude_group].index, inplace=True)
        self.comm_ops.reset_index(drop=True, inplace=True)
        n = len(self.comm_ops)
        group_name_arr = self.comm_ops["groupName"].values
        op_name_arr = self.comm_ops["opName"].values
        for idx in range(n):
            group_name = group_name_arr[idx]
            op_name = op_name_arr[idx]
            grouped_ops_dict[group_name][op_name].append(idx)
        return grouped_ops_dict

    def run(self):
        grouped_ops_dict = self.grouping_ops()
        perpector_df, stats_df = self.analysis(grouped_ops_dict)
        return perpector_df, stats_df

    def analysis(self, grouped_ops_dict):
        rank_id_arr = self.comm_ops["rankId"].values
        comm_time_arr = self.comm_ops["communication_time"].values
        comm_start_arr = self.comm_ops["startNs"].values
        perpector_dict = defaultdict(lambda: 0)
        record = []
        for group_name, ops_same_group in grouped_ops_dict.items():
            for op_name, ops_list in ops_same_group.items():
                time_list = [comm_time_arr[op_idx] for op_idx in ops_list]
                perpector_rank_idx = judge_slow_rank(time_list)
                if not perpector_rank_idx:
                    continue
                slow_ranks = []
                start_times = []
                for rank_idx in perpector_rank_idx:
                    slow_rank = rank_id_arr[ops_list[rank_idx]]
                    perpector_dict[slow_rank] += 1
                    slow_ranks.append(slow_rank)
                    start_times.append(comm_start_arr[ops_list[rank_idx]])
                # 计算统计信息
                stats = self.calculate_basic_stats(time_list)
                record.append({
                    'SlowRank': ",".join(str(rank_id) for rank_id in slow_ranks),
                    'OpName': op_name,
                    'GroupName': group_name,
                    'Timestamp': min(start_times),
                    **stats
                })

        perpector_df = pd.DataFrame(columns=["rankId", "slowAffectCount"])
        for rank, perpector_times in perpector_dict.items():
            perpector_df.loc[len(perpector_df)] = [rank, perpector_times]
        perpector_df.set_index(["rankId"], inplace=True)

        stats_df = pd.DataFrame(record)
        if not stats_df.empty:
            stats_df = stats_df.sort_values(by='Timestamp').reset_index(drop=True)
        return perpector_df, stats_df
