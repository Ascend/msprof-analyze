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
from msprof_analyze.prof_common.logger import get_logger
from msprof_analyze.prof_exports.hccl_sum_export import HcclSumExport

logger = get_logger()


def double_hash(data):
    prime = [29, 131]
    hash_num = [0, 0]
    for d in data:
        hash_num[0] = (((hash_num[0] * prime[0]) & Constant.UINT32_MASK) + ord(d)) & Constant.UINT32_MASK
        hash_num[1] = (((hash_num[1] * prime[1]) & Constant.UINT32_MASK) + ord(d)) & Constant.UINT32_MASK

    return str((hash_num[0] << Constant.UINT32_BITS) | hash_num[1])


class HcclSum(BaseRecipeAnalysis):
    TABLE_ALL_RANK_STATS = "HcclAllRankStats"
    TABLE_PER_RANK_STATS = "HcclPerRankStats"
    TABLE_TOP_OP_STATS = "HcclTopOpStats"
    TABLE_GROUP_NAME_MAP = "HcclGroupNameMap"

    TOP_NUM = "top_num"
    DEFAULT_TOP_NUM = 15

    def __init__(self, params):
        super().__init__(params)
        logger.info("HcclSum init.")
        self.per_rank_stats = None
        self.all_rank_stats = None
        self.group_name_map = None
        self.top_op_stats = None
        top_num = self._extra_args.get(self.TOP_NUM, self.DEFAULT_TOP_NUM)
        self.top_num = int(top_num) if isinstance(top_num, str) and top_num.isdigit() else self.DEFAULT_TOP_NUM

    @property
    def base_dir(self):
        return os.path.basename(os.path.dirname(__file__))

    @classmethod
    def add_parser_argument(cls, parser):
        parser.add_argument("--top_num", type=str, help="Duration cost top count", default=cls.DEFAULT_TOP_NUM)

    def reducer_func(self, mapper_res):
        mapper_res = list(filter(lambda df: df is not None, mapper_res))
        if not mapper_res:
            logger.error("Mapper data is None.")
            return
        self.per_rank_stats = pd.concat(
            describe_duration(df.groupby("OpType")["Duration"]).assign(Rank=df["Rank"][0]) for df in mapper_res)
        self.per_rank_stats.sort_values(by=["Rank"], inplace=True)
        all_op_data = pd.concat(mapper_res)
        self.all_rank_stats = describe_duration(all_op_data.groupby("OpType")["Duration"])
        grouped_op_stats = all_op_data.groupby("OpName")
        self.top_op_stats = describe_duration(grouped_op_stats["Duration"]).nlargest(self.top_num, "MeanNs")
        min_rank = []
        max_rank = []
        for op_name in self.top_op_stats.index:
            df = grouped_op_stats.get_group(op_name)
            min_rank.append(df[df["Duration"] == df["Duration"].min()]["Rank"].values[0])
            max_rank.append(df[df["Duration"] == df["Duration"].max()]["Rank"].values[0])
        self.top_op_stats["MinRank"] = min_rank
        self.top_op_stats["MaxRank"] = max_rank

        grouped_group_name_stats = all_op_data.groupby("GroupName")
        group_name_rank_map = grouped_group_name_stats.apply(
            lambda x: ';'.join(map(str, x['Rank'].drop_duplicates().sort_index()))).sort_index()
        self.group_name_map = pd.DataFrame(
            data={
                "GroupId": [key[-3:] for key in map(double_hash, group_name_rank_map.keys())],
                "Ranks": group_name_rank_map.values
            },
            index=sorted(grouped_group_name_stats.groups.keys())
        )
        self.group_name_map.index.name = "GroupName"
        self.group_name_map.sort_values("GroupId", inplace=True)

    def run(self, context):
        if self.top_num <= 0:
            logger.warning(f"HcclSum: top_num is set to a invalid value, "
                           f"it will be reset to default value({self.DEFAULT_TOP_NUM}).")
            self.top_num = self.DEFAULT_TOP_NUM
        mapper_res = self.mapper_func(context)
        self.reducer_func(mapper_res)

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
        self.dump_data(self.per_rank_stats, "rank_stats.csv")
        self.dump_data(self.top_op_stats, "top_op_stats.csv")
        self.dump_data(self.group_name_map, "group_name_map.csv")

    def save_db(self):
        self.dump_data(self.all_rank_stats, Constant.DB_CLUSTER_COMMUNICATION_ANALYZER, self.TABLE_ALL_RANK_STATS)
        self.dump_data(self.per_rank_stats, Constant.DB_CLUSTER_COMMUNICATION_ANALYZER, self.TABLE_PER_RANK_STATS)
        self.dump_data(self.top_op_stats, Constant.DB_CLUSTER_COMMUNICATION_ANALYZER, self.TABLE_TOP_OP_STATS)
        self.dump_data(self.group_name_map, Constant.DB_CLUSTER_COMMUNICATION_ANALYZER, self.TABLE_GROUP_NAME_MAP)

    def _mapper_func(self, data_map, analysis_class):
        profiler_db_path = data_map.get(Constant.PROFILER_DB_PATH)
        rank_id = data_map.get(Constant.RANK_ID)
        step_range = data_map.get(Constant.STEP_RANGE)
        df = HcclSumExport(profiler_db_path, analysis_class, step_range).read_export_db()
        if df is None or df.empty:
            logger.warning(f"There is no stats data in {profiler_db_path}.")
            return None
        df["Rank"] = rank_id
        return df
