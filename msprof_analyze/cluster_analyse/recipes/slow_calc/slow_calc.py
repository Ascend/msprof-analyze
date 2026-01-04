# Copyright (c) 2025, Huawei Technologies Co., Ltd.
# All rights reserved.
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
# http://www.apache.org/licenses/LICENSE-2.0
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import os
from pathlib import Path
import tqdm
import numpy as np
import pandas as pd

from msprof_analyze.cluster_analyse.recipes.base_recipe_analysis import BaseRecipeAnalysis
from msprof_analyze.prof_common.constant import Constant
from msprof_analyze.prof_common.logger import get_logger
from msprof_analyze.prof_common.database_service import DatabaseService

from msprof_analyze.prof_exports.slow_calc_export import SlowCalcExport
from msprof_analyze.cluster_analyse.common_func.utils import calculate_zscore


logger = get_logger()

STR_COLUMN_RANK = "rank"

GROUP_KEY_LIST = ["opName", "inputShapes", "outputShapes"]


class SlowCalc(BaseRecipeAnalysis):
    TABLE_SLOW_CALC_SUM = "SlowCalcSum"
    TABLE_SLOW_CALC_TETAIL = "SlowCalcDetail"

    def __init__(self, params):
        super().__init__(params)
        logger.info("SlowRankCheck init.")
        self.path_output = Path(self._output_path)

    @property
    def base_dir(self):
        return os.path.basename(os.path.dirname(__file__))

    @staticmethod
    def check_abnormal(df_total) -> pd.DataFrame:
        str_name_p = "p_score"
        str_name_z = "z_score"
        str_name_index = "the_index"

        # * 计算偏离最小值很多的算子
        df_total: pd.DataFrame = df_total
        df_total.loc[:, str_name_index] = range(len(df_total))
        df_total.set_index(str_name_index, inplace=True)
        df_total.loc[:, str_name_p] = np.nan
        df_total.loc[:, str_name_z] = np.nan

        all_df_total = df_total.groupby(GROUP_KEY_LIST)

        # * 第一层： shape 和算子名称分组
        dict_abnormal = {}
        for group_i in tqdm.tqdm(all_df_total.groups, desc="Analyzing..."):
            # * 第二层：rank 分组
            the_index_i = all_df_total.get_group(group_i).index
            detail_i = df_total.loc[the_index_i]

            np_duration = detail_i[[Constant.DURATION_TIME]].to_numpy().reshape(-1)

            m = np.mean(np_duration)
            sd = np.std(np_duration)

            if m == 0:
                p = 1
            else:
                p = (detail_i[Constant.DURATION_TIME].to_numpy() - m) / m
            z = calculate_zscore(np_duration, m, sd)

            df_total.loc[the_index_i, str_name_p] = p
            df_total.loc[the_index_i, str_name_z] = z

            detail_i = df_total.loc[the_index_i]  # * 重新索引，更新写入的数据
            df_abnormal_i = detail_i.groupby(STR_COLUMN_RANK, as_index=False).agg(
                count=(Constant.DURATION_TIME, len),
                time_mean=(Constant.DURATION_TIME, "mean"),
                time_max=(Constant.DURATION_TIME, "max"),
                p_mean=(str_name_p, "mean"),
                p_max=(str_name_p, "max"),
                z_mean=(str_name_z, "mean"),
                z_max=(str_name_z, "max"),
            )

            for ii, k in enumerate(GROUP_KEY_LIST):
                df_abnormal_i[k] = group_i[ii]

            dict_abnormal[group_i] = df_abnormal_i

        logger.info("Summarizing...")
        df_abnormal = pd.concat(dict_abnormal.values(), axis=0)

        dict_df = {
            SlowCalc.TABLE_SLOW_CALC_SUM: df_abnormal,
            SlowCalc.TABLE_SLOW_CALC_TETAIL: df_total,
        }
        return dict_df

    @staticmethod
    def _mapper_func(data_map, analysis_class):
        profiler_db_path = data_map.get(Constant.PROFILER_DB_PATH)
        rank_id = data_map.get(Constant.RANK_ID)

        db_service = DatabaseService(profiler_db_path, {})
        db_service.add_table_for_query("STRING_IDS")
        dict_table = db_service.query_data()
        if "STRING_IDS" not in dict_table:
            logger.error(f"No STRING_IDS in database ({profiler_db_path}).")
            return None
        name_data = dict_table["STRING_IDS"]

        df_calc = SlowCalcExport(profiler_db_path, analysis_class).read_export_db()

        dict_id_name = dict(zip(name_data["id"], name_data["value"]))
        df_calc["inputShapes"] = df_calc["inputShapes"].map(dict_id_name)
        df_calc["outputShapes"] = df_calc["outputShapes"].map(dict_id_name)
        df_calc["opName"] = df_calc["opName"].map(dict_id_name)
        df_calc["opType"] = df_calc["opType"].map(dict_id_name)
        df_calc[STR_COLUMN_RANK] = rank_id

        return df_calc

    def run(self, context):
        mapper_res = self.mapper_func(context)
        logger.info("Collecting op info completed.")
        self.reducer_func(mapper_res)
        logger.info("Summarying completed.")

    def reducer_func(self, mapper_res):
        if mapper_res is None or len(mapper_res) == 0:
            logger.error("mapper_res is None.")
            return
        list_df = [i for i in mapper_res if i is not None]
        total_df = pd.concat(list_df, axis=0)

        dict_df = self.check_abnormal(total_df)
        self.save_summary(dict_df)

    def save_summary(self, dict_df):
        self.slow_calc_sum = dict_df[self.TABLE_SLOW_CALC_SUM]
        self.slow_calc_detail = dict_df[self.TABLE_SLOW_CALC_TETAIL]

        if self._export_type == "db":
            self.save_db()
        elif self._export_type == "notebook":
            self.save_notebook()
        else:
            logger.warning(f"Unknown export type [{self._export_type}]. Defalut to save db.")
            self.save_db()

    def save_notebook(self):
        self.dump_data(self.slow_calc_sum, "slow_calc_sum" + Constant.CSV_SUFFIX, index=False)
        self.dump_data(self.slow_calc_detail, "slow_calc_detail" + Constant.CSV_SUFFIX, index=False)

    def save_db(self):
        self.dump_data(
            self.slow_calc_sum,
            Constant.DB_CLUSTER_COMMUNICATION_ANALYZER,
            self.TABLE_SLOW_CALC_SUM,
            index=False,
        )
        self.dump_data(
            self.slow_calc_detail,
            Constant.DB_CLUSTER_COMMUNICATION_ANALYZER,
            self.TABLE_SLOW_CALC_TETAIL,
            index=False,
        )
