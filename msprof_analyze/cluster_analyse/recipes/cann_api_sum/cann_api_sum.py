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

from msprof_analyze.cluster_analyse.common_func.utils import stdev
from msprof_analyze.cluster_analyse.recipes.base_recipe_analysis import BaseRecipeAnalysis
from msprof_analyze.prof_common.constant import Constant
from msprof_analyze.prof_common.logger import get_logger
from msprof_analyze.prof_exports.cann_api_sum_export import CannApiSumExport

logger = get_logger()


class CannApiSum(BaseRecipeAnalysis):

    def __init__(self, params):
        super().__init__(params)
        logger.info("CannApiSum init.")
        self._stats_rank_data = None
        self._stats_data = None

    @property
    def base_dir(self):
        return os.path.basename(os.path.dirname(__file__))

    @staticmethod
    def _aggregate_stats(stats_res):
        grouped = stats_res.groupby("name")
        res = {}
        total_time = grouped["totalTimeNs"].sum()
        res["timeRatio"] = total_time / total_time.sum() * 100.0 if total_time.sum() else 0
        res["totalTimeNs"] = total_time
        res["totalCount"] = grouped["totalCount"].sum()
        res["averageNs"] = res["totalTimeNs"] / res["totalCount"].where(res["totalCount"] != 0, other=0)
        res["Q1Ns"] = grouped["Q1Ns"].min()
        res["medNs"] = grouped["medNs"].median()
        res["Q3Ns"] = grouped["Q3Ns"].max()
        res["minNs"] = grouped["minNs"].min()
        res["maxNs"] = grouped["maxNs"].max()
        res["stdev"] = grouped.apply(lambda x: stdev(x, res))
        min_value = grouped["minNs"].min()
        res["minRank"] = grouped.apply(
            lambda x: ", ".join(x.loc[x["minNs"] == min_value.loc[x.name], "rank"].astype(str))
        )
        max_value = grouped["maxNs"].max()
        res["maxRank"] = grouped.apply(
            lambda x: ", ".join(x.loc[x["maxNs"] == max_value.loc[x.name], "rank"].astype(str))
        )
        res = pd.concat(res.values(), axis=1, keys=res.keys()).round(1)
        res.sort_values(by="totalTimeNs", ascending=False, inplace=True)
        return res

    def reducer_func(self, mapper_res):
        stats_rank_data = self._filter_data(mapper_res)
        if not stats_rank_data:
            logger.error("Mapper data is None.")
            return
        stats_rank_data = [df.assign(rank=rank) for rank, df in stats_rank_data]
        self._stats_rank_data = pd.concat(stats_rank_data)
        self._stats_data = self._aggregate_stats(self._stats_rank_data)

    def run(self, context):
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

    def save_db(self):
        self.dump_data(self._stats_rank_data, Constant.DB_CLUSTER_COMMUNICATION_ANALYZER, "CannApiSumRank",
                       index=False)
        self.dump_data(self._stats_data, Constant.DB_CLUSTER_COMMUNICATION_ANALYZER, "CannApiSum")

    def save_csv(self):
        self.dump_data(self._stats_rank_data, "rank_stats.csv", index=False)
        self.dump_data(self._stats_data, "all_stats.csv")

    def _mapper_func(self, data_map, analysis_class):
        profiler_db_path = data_map.get(Constant.PROFILER_DB_PATH)
        rank_id = data_map.get(Constant.RANK_ID)
        step_range = data_map.get(Constant.STEP_RANGE)
        df = CannApiSumExport(profiler_db_path, analysis_class, step_range).read_export_db()
        if df is None or df.empty:
            logger.warning(f"There is no stats data in {profiler_db_path}.")
            return None, None
        return rank_id, df
