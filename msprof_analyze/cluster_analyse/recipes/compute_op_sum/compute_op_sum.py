# Copyright (c) 2024, Huawei Technologies Co., Ltd.
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
import pandas as pd

from msprof_analyze.cluster_analyse.common_func.utils import describe_duration
from msprof_analyze.cluster_analyse.recipes.base_recipe_analysis import BaseRecipeAnalysis
from msprof_analyze.prof_common.constant import Constant
from msprof_analyze.prof_common.json_output import set_json_success
from msprof_analyze.prof_common.logger import get_logger
from msprof_analyze.prof_exports.compute_op_sum_export import ComputeOpSumExport
from msprof_analyze.prof_exports.compute_op_sum_export import ComputeOpSumExportExcludeOpName

logger = get_logger()


class ComputeOpSum(BaseRecipeAnalysis):
    TABLE_ALL_RANK_STATS = "ComputeOpAllRankStats"
    TABLE_PER_RANK_STATS_BY_OPTYPE = "ComputeOpPerRankStatsByOpType"
    TABLE_PER_RANK_STATS_BY_OPNAME = "ComputeOpPerRankStatsByOpName"

    EXCLUDE_OP_NAME = "exclude_op_name"
    DEFAULT_SWITCH = False
    SUGGESTION = """
    ComputeOpAllRankStats / all_stats.csv：汇总所有 rank 上各类计算算子按 OpType + TaskType 的耗时分布，用它先找整体最重的计算类型。
    ComputeOpPerRankStatsByOpType / per_rank_stats_by_optype.csv：按 rank 统计各类计算算子的耗时分布，用它定位是哪几个 rank 的某类计算算子异常慢。
    ComputeOpPerRankStatsByOpName / per_rank_stats_by_opname.csv：按 rank 统计具体算子名、类型和输入 shape 的耗时分布，用它继续下钻到“是哪一个具体算子/shape 组合导致变慢”。
    """

    def __init__(self, params):
        super().__init__(params)
        logger.info("ComputeOpSum init.")
        self.all_rank_stats = None
        self.per_rank_stats_by_optype = None
        self.per_rank_stats_by_opname = None
        self.exclude_op_name = self._extra_args.get(self.EXCLUDE_OP_NAME, self.DEFAULT_SWITCH)

    @property
    def base_dir(self):
        return os.path.basename(os.path.dirname(__file__))

    @classmethod
    def add_parser_argument(cls, parser):
        BaseRecipeAnalysis.add_parser_argument(parser)
        parser.add_argument(
            '--exclude_op_name', default=False, action='store_true', help='whether exclude op_name in the SQL query'
        )

    def reducer_func(self, mapper_res):
        mapper_res = list(filter(lambda df: df is not None, mapper_res))
        if not mapper_res:
            logger.error("Mapper data is None.")
            return
        # get per rank stats by optype
        self.per_rank_stats_by_optype = pd.concat(
            describe_duration(df.groupby(["OpType", "TaskType"])["Duration"]).assign(Rank=df["Rank"][0])
            for df in mapper_res
        )
        self.per_rank_stats_by_optype.sort_values(by=["SumNs"], inplace=True, ascending=False)

        # get all rank stats by optype
        all_op_data = pd.concat(mapper_res)
        self.all_rank_stats = describe_duration(all_op_data.groupby(["OpType", "TaskType"])["Duration"])
        self.all_rank_stats.sort_values(by=["SumNs"], inplace=True, ascending=False)

        if self.exclude_op_name:
            return
        # get per rank stats by opname
        self.per_rank_stats_by_opname = pd.concat(
            describe_duration(df.groupby(["OpName", "OpType", "TaskType", "InputShapes"])["Duration"]).assign(
                Rank=df["Rank"][0]) for df in mapper_res)
        self.per_rank_stats_by_opname.sort_values(by=["SumNs"], inplace=True, ascending=False)

    def run(self, context):
        mapper_res = self.mapper_func(context)
        self.reducer_func(mapper_res)
        if self.all_rank_stats is None or self.per_rank_stats_by_optype is None:
            return

        if self._export_type == Constant.DB:
            self.save_db()
        elif self._export_type == Constant.NOTEBOOK:
            self.save_csv()
            self.save_notebook()
        elif self._export_type == Constant.TEXT:
            self.save_csv()
        else:
            logger.error("Unknown export type.")

    def save_notebook(self):
        self.create_notebook("stats.ipynb")
        self.add_helper_file("cluster_display.py")

    def save_csv(self):
        self.dump_data(self.all_rank_stats, "all_stats.csv")
        self.dump_data(self.per_rank_stats_by_optype, "rank_stats_by_optype.csv")
        if not self.exclude_op_name:
            self.dump_data(self.per_rank_stats_by_opname, "rank_stats_by_opname.csv")
        set_json_success(
            msg_dict={
                "csv_path": [
                    os.path.join(self.output_path, "all_stats.csv"),
                    os.path.join(self.output_path, "rank_stats_by_optype.csv"),
                    os.path.join(self.output_path, "rank_stats_by_opname.csv")
                ]
            },
            suggestion=self.SUGGESTION
        )

    def save_db(self):
        self.dump_data(self.all_rank_stats, Constant.DB_CLUSTER_COMMUNICATION_ANALYZER, self.TABLE_ALL_RANK_STATS)
        self.dump_data(self.per_rank_stats_by_optype, Constant.DB_CLUSTER_COMMUNICATION_ANALYZER,
                       self.TABLE_PER_RANK_STATS_BY_OPTYPE)
        if not self.exclude_op_name:
            self.dump_data(self.per_rank_stats_by_opname, Constant.DB_CLUSTER_COMMUNICATION_ANALYZER,
                       self.TABLE_PER_RANK_STATS_BY_OPNAME)
        set_json_success(
            msg_dict={
                "db_path": os.path.join(self.output_path, Constant.DB_CLUSTER_COMMUNICATION_ANALYZER),
                "tables": [
                    self.TABLE_ALL_RANK_STATS,
                    self.TABLE_PER_RANK_STATS_BY_OPTYPE,
                    self.TABLE_PER_RANK_STATS_BY_OPNAME
                ]
            },
            suggestion=self.SUGGESTION
        )

    def _mapper_func(self, data_map, analysis_class):
        profiler_db_path = data_map.get(Constant.PROFILER_DB_PATH)
        rank_id = data_map.get(Constant.RANK_ID)
        step_range = data_map.get(Constant.STEP_RANGE)
        if self.exclude_op_name:
            df = ComputeOpSumExportExcludeOpName(profiler_db_path, analysis_class, step_range).read_export_db()
        else:
            df = ComputeOpSumExport(profiler_db_path, analysis_class, step_range).read_export_db()
        if df is None or df.empty:
            logger.warning(f"There is no stats data in {profiler_db_path}.")
            return None
        df["Rank"] = rank_id
        return df
