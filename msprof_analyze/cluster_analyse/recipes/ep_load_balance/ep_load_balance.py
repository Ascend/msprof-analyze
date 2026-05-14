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

import pandas as pd

from msprof_analyze.cluster_analyse.recipes.base_recipe_analysis import BaseRecipeAnalysis
from msprof_analyze.prof_common.constant import Constant
from msprof_analyze.prof_common.json_output import set_json_success
from msprof_analyze.prof_common.logger import get_logger
from msprof_analyze.prof_exports.ep_load_balance_ecport import InputShapeExport
from msprof_analyze.prof_common.database_service import DatabaseService

logger = get_logger()


class EPLoadBalance(BaseRecipeAnalysis):

    EP_TOKENS_SUMMARY = "EPTokensSummary"
    TOP_EP_TOKENS_INFO = "TopEPTokensInfo"
    META_DATA = "META_DATA"
    Top_Num = 20
    GROUPEP = "exp"
    SUGGESTION = """
    EPTokensSummary：汇总各 rank 及对应 EP 分组下 GroupedMatmul 算子输入首维 token 总量，用它全局梳理所有 EP 分组、各卡的专家 token 承载量级，直观判断整体专家流量分布基底情况。
    TopEPTokensInfo：统计存在负载不均的 EP 分组及组内 token 最大最小差值，用它直接筛选出负载不均最严重的专家并行分组，精准定位需要调优的 EP 组。
    """

    def __init__(self, params):
        super().__init__(params)
        logger.info("EPLoadBalance init.")
        self.ep_tokens_summary = None
        self.top_ep_tokens_map = None

    @property
    def base_dir(self):
        return os.path.basename(os.path.dirname(__file__))

    def process_input_shapes(self, df):
        def calculate_seqlength(shape_str):
            shape_str = shape_str.strip('"')
            parts = shape_str.split(";")
            non_empty_parts = [part for part in parts if part]
            # 取前 n-2 个有值的部分
            if len(non_empty_parts) > 1:
                non_empty_parts = non_empty_parts[: len(non_empty_parts) - 2]
            else:
                return None
            seqlength = 0
            for part in non_empty_parts:
                part = part.strip()
                try:
                    first_dim = int(part.split(",")[0])
                except (IndexError, ValueError) as e:
                    return None
                seqlength += first_dim
            return seqlength

        df["InputShapes"] = df["InputShapes"].apply(calculate_seqlength)
        return df

    def reducer_func(self, mapper_res):
        mapper_res = list(filter(lambda df: df is not None, mapper_res))
        if not mapper_res:
            logger.error("Mapper data is None.")
            return
        for i, df in enumerate(mapper_res):
            mapper_res[i] = self.process_input_shapes(df)
        mapper_res = [df.dropna() for df in mapper_res]
        for df in mapper_res:
            df["epRanks"] = df["epRanks"].apply(lambda x: ",".join(map(str, x)))
        combined_df = pd.concat(mapper_res)
        self.ep_tokens_summary = combined_df.groupby(["Rank", "epRanks"]).agg({"InputShapes": "sum"}).reset_index()
        self.ep_tokens_summary.columns = ["rank", "epRanks", "inputShapesSummary"]
        self.top_ep_tokens_map = (
            self.ep_tokens_summary.groupby("epRanks")["inputShapesSummary"]
            .agg(tokensDiff=lambda x: x.max() - x.min())
            .reset_index()
        )
        self.top_ep_tokens_map = self.top_ep_tokens_map.sort_values(by="tokensDiff", ascending=False).head(self.Top_Num)

    def run(self, context):
        mapper_res = self.mapper_func(context)
        self.reducer_func(mapper_res)

        if self._export_type == "db":
            self.save_db()
        else:
            logger.error("ep_load_balance is only supported for db export type.")

    def save_db(self):
        self.dump_data(self.ep_tokens_summary, Constant.DB_CLUSTER_COMMUNICATION_ANALYZER, self.EP_TOKENS_SUMMARY,
                       index=False)
        self.dump_data(self.top_ep_tokens_map, Constant.DB_CLUSTER_COMMUNICATION_ANALYZER, self.TOP_EP_TOKENS_INFO,
                       index=False)
        set_json_success(
            msg_dict={
                "db_path": os.path.join(self.output_path, Constant.DB_CLUSTER_COMMUNICATION_ANALYZER),
                "tables": [self.EP_TOKENS_SUMMARY, self.TOP_EP_TOKENS_INFO]
            },
            suggestion=self.SUGGESTION
        )

    def _mapper_func(self, data_map, analysis_class):
        profiler_db_path = data_map.get(Constant.PROFILER_DB_PATH)
        rank_id = data_map.get(Constant.RANK_ID)
        step_range = data_map.get(Constant.STEP_RANGE)
        analysis_data_service = DatabaseService(profiler_db_path, {})
        analysis_data_service.add_table_for_query(self.META_DATA)
        meta_map = analysis_data_service.query_data()[self.META_DATA]
        parallel_group_info = meta_map.loc[meta_map['name'] == 'parallel_group_info', 'value'].iloc[0]
        try:
            data_dict = json.loads(parallel_group_info)
        except json.JSONDecodeError as e:
            logger.error(f"{profiler_db_path}'s parallel_group_info is illegal")
            return None
        if not isinstance(data_dict, dict):
            raise TypeError('{} must be dict, not {}.'.format(data_dict, type(data_dict).__name__))     
        for _, value in data_dict.items():
            if value["group_name"] == self.GROUPEP:
                global_ranks = value["global_ranks"]
                break
        df = InputShapeExport(profiler_db_path, analysis_class, step_range).read_export_db()
        if df is None or df.empty:
            logger.warning(f"There is no stats data in {profiler_db_path}.")
            return None
        df["Rank"] = rank_id
        df["epRanks"] = [global_ranks] * len(df)
        return df