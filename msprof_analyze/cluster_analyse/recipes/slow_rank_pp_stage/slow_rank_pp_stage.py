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
import json
from collections import defaultdict

import pandas as pd

from msprof_analyze.cluster_analyse.recipes.base_recipe_analysis import BaseRecipeAnalysis
from msprof_analyze.prof_common.constant import Constant
from msprof_analyze.prof_common.logger import get_logger
from msprof_analyze.prof_exports.cluster_time_summary_export import CommunicationTimeExport
from msprof_analyze.prof_common.database_service import DatabaseService

logger = get_logger()


class SlowRankPPStageAnalysis(BaseRecipeAnalysis):
    def __init__(self, params):
        super().__init__(params)
        logger.info("SlowRank PPstage analysis init.")

        self.p2p_analysis_result = None
        self.pp_analysis_result = None
        self.p2p_vote_result = None
        self.pp_vote_result = None

        self.distributed_args = self.load_distributed_args()

    @property
    def base_dir(self):
        return os.path.basename(os.path.dirname(__file__))
    
    @classmethod
    def add_parser_argument(cls, parser):
        parser.add_argument("--tp", type=int, help=cls.TP_SIZE, default=None)
        parser.add_argument("--pp", type=int, help=cls.PP_SIZE, default=None)
        parser.add_argument("--dp", type=int, help=cls.DP_SIZE, default=None)

    def reducer_func(self, mapper_res):
        mapper_res = list(filter(lambda df: df is not None, mapper_res))
        if not mapper_res:
            logger.error("Mapper data is None.")
            return None
        concated_df = pd.concat(mapper_res)
        return concated_df

    def run(self, context):
        if self.distributed_args is None:
            return
        mapper_res = self.mapper_func(context)
        comm_ops_df = self.reducer_func(mapper_res)
        if comm_ops_df is None:
            return

        p2p_analysis_result_list = []
        p2p_vote_result_list = []
        pp_analysis_result_list = []
        pp_vote_result_list = []

        pp_stage_rank_map = self.map_rank_pp_stage()

        for _, df_one_step in comm_ops_df.groupby("step"):
            p2p_analysis_result, p2p_vote_result, pp_analysis_result, pp_vote_result = \
                SlowRankPPStageStepAnalysis(df_one_step).analysis(pp_stage_rank_map)
            p2p_analysis_result_list.append(p2p_analysis_result)
            p2p_vote_result_list.append(p2p_vote_result)
            pp_analysis_result_list.append(pp_analysis_result)
            pp_vote_result_list.append(pp_vote_result)

        for step_id, (p2p_analysis_result, p2p_vote_result, pp_analysis_result, pp_vote_result) in \
                enumerate(
                    zip(
                        p2p_analysis_result_list, 
                        p2p_vote_result_list, 
                        pp_analysis_result_list, 
                        pp_vote_result_list
                    )):
            p2p_analysis_result["step"] = step_id
            p2p_vote_result["step"] = step_id
            pp_analysis_result["step"] = step_id
            pp_vote_result["step"] = step_id
            
        self.p2p_analysis_result = pd.concat(p2p_analysis_result_list)
        self.p2p_vote_result = pd.concat(p2p_vote_result_list)
        self.pp_analysis_result = pd.concat(pp_analysis_result_list)
        self.pp_vote_result = pd.concat(pp_vote_result_list)

        if self._export_type == Constant.DB:
            self.save_db()
        else:
            logger.error("SlowRank PPstage is not supported for notebook export type.")

    def save_db(self):
        self.dump_data(self.p2p_vote_result, Constant.DB_CLUSTER_COMMUNICATION_ANALYZER, "P2PAnalysisResult")
        self.dump_data(self.pp_vote_result, Constant.DB_CLUSTER_COMMUNICATION_ANALYZER, "PPAnalysisResult")
    
    def map_rank_pp_stage(self):
        tp_size = self.distributed_args.get(self.TP_SIZE, 1)
        pp_size = self.distributed_args.get(self.PP_SIZE, 1)
        dp_size = self.distributed_args.get(self.DP_SIZE, 1)
        
        rank_pp_stage_map = {}
        rank = 0
        for i in range(pp_size):
            for _ in range(tp_size * dp_size):
                rank_pp_stage_map[rank] = i
                rank += 1
        return rank_pp_stage_map

    def _mapper_func(self, data_map, analysis_class):
        profiler_db_path = data_map.get(Constant.PROFILER_DB_PATH)
        step_range = data_map.get(Constant.STEP_RANGE)
        df = CommunicationTimeExport(profiler_db_path, analysis_class, step_range).read_export_db()
        return df


class SlowRankPPStageStepAnalysis:
    def __init__(self, comm_ops):
        self.comm_ops = comm_ops
        self.exclude_ranks = []

    def grouping_pp_stage_ops(self, pp_stage_rank_map):
        p2p_op_group = defaultdict(lambda: defaultdict(list))
        pp_op_group = defaultdict(lambda: defaultdict(list))

        def divid_opname(op_name):
            # op_name的格式:输入 OPTYPE__GORUPHASH_IDX_1 输出 OPTYPE_IDX
            splited_name = op_name.split("__")
            if len(splited_name) != 2:
                return None
            splited_num = splited_name[1].split("_")
            if len(splited_num) != 3:
                return None
            return "_".join([splited_name[0], splited_num[1]])

        ops_num = len(self.comm_ops)
        op_name_arr = self.comm_ops["opName"].values
        rank_id_arr = self.comm_ops["rank"].values
        for idx in range(ops_num):
            rank = rank_id_arr[idx]
            op_name = op_name_arr[idx]
            op_name_short = divid_opname(op_name)
            if op_name_short is None:
                continue
            pp_stage_idx = pp_stage_rank_map[rank]
            if rank in self.exclude_ranks:
                continue
            if "send" in op_name_short or "receive" in op_name_short:
                p2p_op_group[pp_stage_idx][op_name_short].append(idx)
            else:
                pp_op_group[pp_stage_idx][op_name_short].append(idx)

        return p2p_op_group, pp_op_group

    def analysis_pp_stage(self, vote_group):
        min_time_dict = defaultdict(lambda: defaultdict(lambda: 0))
        max_time_dict = defaultdict(lambda: defaultdict(lambda: 0))
        mean_time_dict = defaultdict(lambda: defaultdict(lambda: 0))
        count_dict = defaultdict(lambda: defaultdict(lambda: 0))
        rank_vote = defaultdict(lambda: 0)
        perpetrator_dict = defaultdict(lambda: defaultdict(lambda: 0))
        minimum_rank_op_name = defaultdict(list)

        communication_time_arr = self.comm_ops["communication_time"].values
        rank_id_arr = self.comm_ops["rank"].values
        for pp_idx, ops_same_group in vote_group.items():
            for op_name, ops in ops_same_group.items():
                communication_time_list = [communication_time_arr[op_idx] for op_idx in ops]
                min_time = min(communication_time_list)
                min_op_idx = ops[communication_time_list.index(min_time)]
                min_op_rank = rank_id_arr[min_op_idx]
                rank_vote[min_op_rank] += 1
                perpetrator_dict[pp_idx][op_name] = min_op_rank
                minimum_rank_op_name[min_op_rank].append(op_name)

                max_time = max(communication_time_list)
                mean_time = sum(communication_time_list) // len(communication_time_list)
                min_time_dict[pp_idx][op_name] = min_time
                max_time_dict[pp_idx][op_name] = max_time
                mean_time_dict[pp_idx][op_name] = mean_time
                count_dict[pp_idx][op_name] = len(ops)

        analysis_result = pd.DataFrame(
            columns=[
                "ppIdx", 
                "opName", 
                "minTime", 
                "maxTime", 
                "meanTime", 
                "count", 
                "perpetratorRank"
                ]
            )

        for pp_idx in min_time_dict.keys():
            for op_name in min_time_dict[pp_idx].keys():
                analysis_result.loc[len(analysis_result)] = [
                    pp_idx, op_name,
                    min_time_dict[pp_idx][op_name],
                    max_time_dict[pp_idx][op_name],
                    mean_time_dict[pp_idx][op_name],
                    count_dict[pp_idx][op_name],
                    perpetrator_dict[pp_idx][op_name]
                ]

        vote_result = pd.DataFrame(columns=["rankId", "minimumTimes"])
        for rank, minimum_times in rank_vote.items():
            vote_result.loc[len(vote_result)] = [rank, minimum_times]
        vote_result.set_index(["rankId"], inplace=True)

        return analysis_result, vote_result

    def analysis(self, pp_stage_rank_map):
        self.select_exclude_ranks()
        p2p_op_group, pp_op_group = self.grouping_pp_stage_ops(pp_stage_rank_map)
        p2p_analysis_result, p2p_vote_result = self.analysis_pp_stage(p2p_op_group)
        pp_analysis_result, pp_vote_result = self.analysis_pp_stage(pp_op_group)
        return p2p_analysis_result, p2p_vote_result, pp_analysis_result, pp_vote_result

    def select_exclude_ranks(self):
        grouped_df = self.comm_ops.groupby("rank")
        for rank in grouped_df.groups.keys():
            ops_groupby_rank = grouped_df.get_group(rank)
            ops_num = ops_groupby_rank.groupby("opName").size().values
            if len(set(ops_num)) > 1:
                self.exclude_ranks.append(rank)
