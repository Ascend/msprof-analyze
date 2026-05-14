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
from collections import defaultdict
import pandas as pd

from msprof_analyze.cluster_analyse.recipes.base_recipe_analysis import BaseRecipeAnalysis
from msprof_analyze.prof_common.constant import Constant
from msprof_analyze.prof_common.json_output import set_json_success
from msprof_analyze.prof_common.logger import get_logger
from msprof_analyze.prof_common.database_service import DatabaseService

logger = get_logger()


class FreqAnalysis(BaseRecipeAnalysis):
    COMMON_FREQ = 1800
    FREE_FREQ = 800
    SUGGESTION = """
    FreeFrequencyRanks：统计因设备长时间空闲自动降至 800MHz 的 rank 列表及对应频率区间，用它区分空闲休眠式降频，排查是否存在算力空转、任务调度不饱满问题。
    AbnormalFrequencyRanks：统计出现非标准 1800MHz/800MHz 以外异常频率的 rank 及频率明细，用它精准定位硬件 / 调度异常导致的非自愿降频，快速锁定异常 NPU 卡。
    """

    def __init__(self, params):
        super().__init__(params)
        self.free_freq_ranks = []
        self.abnormal_freq_ranks = []
        self.abnormal_freq_ranks_map = {}

    @property
    def base_dir(self):
        return os.path.basename(os.path.dirname(__file__))

    def reducer_func(self, mapper_res):
        if self._prof_type == Constant.MSPROF:
            logger.warning("Freq analysis do not support msprof db now.")
            return
        mapper_res = list(filter(lambda res: res[0] is not None, mapper_res))
        if not mapper_res:
            logger.error("Mapper data is None, load profiling data failed.")
            return
        for freqs, rank_id in mapper_res:
            if freqs == [self.COMMON_FREQ]:
                continue
            elif set(freqs) == {self.COMMON_FREQ, self.FREE_FREQ}:
                self.free_freq_ranks.append(rank_id)
            else:
                self.abnormal_freq_ranks.append(rank_id)
                self.abnormal_freq_ranks_map[rank_id] = str(freqs)
        self.free_freq_ranks.sort()
        self.abnormal_freq_ranks.sort()

    def save_db(self):
        if len(self.free_freq_ranks) > 0:
            logger.info(f"Found {len(self.free_freq_ranks)} ranks with free time, "
                        f"aicore frequency in {[self.FREE_FREQ, self.COMMON_FREQ]}.")
            free_ranks_df = pd.DataFrame()
            free_ranks_df["rankId"] = self.free_freq_ranks
            free_ranks_df["aicoreFrequency"] = str([self.FREE_FREQ, self.COMMON_FREQ])
            free_ranks_df.set_index(["rankId"], inplace=True)
            self.dump_data(free_ranks_df, Constant.DB_CLUSTER_COMMUNICATION_ANALYZER, "FreeFrequencyRanks")
        else:
            logger.info("No rank found with free time.")
        if len(self.abnormal_freq_ranks) > 0:    
            logger.info(f"Found {len(self.abnormal_freq_ranks)} ranks with abnormal aicore frequency.")

            abnormal_ranks_df = pd.DataFrame.from_dict(self.abnormal_freq_ranks_map, 
                                                       orient="index", columns=["aicoreFrequency"])
            abnormal_ranks_df = abnormal_ranks_df.reset_index().rename(columns={"index": "rankId"})
            abnormal_ranks_df.set_index(["rankId"], inplace=True)
            self.dump_data(abnormal_ranks_df, Constant.DB_CLUSTER_COMMUNICATION_ANALYZER, "AbnormalFrequencyRanks")
        else:
            logger.info("No rank found with abnormal aicore frequency.")
        if len(self.free_freq_ranks) > 0 or len(self.abnormal_freq_ranks) > 0:
            logger.info("Please verify result in output file.")
        set_json_success(
            msg_dict={
                "db_path": os.path.join(self.output_path, Constant.DB_CLUSTER_COMMUNICATION_ANALYZER),
                "tables": ["FreeFrequencyRanks", "AbnormalFrequencyRanks"]
            },
            suggestion=self.SUGGESTION
        )

    def run(self, context):
        mapper_res = self.mapper_func(context)
        self.reducer_func(mapper_res)

        if self._export_type == Constant.DB:
            self.save_db() 
        else:
            logger.error("Frequence analysis is not supported for notebook export type.")

    def _mapper_func(self, data_map, analysis_class):
        profiler_db_path = data_map.get(Constant.PROFILER_DB_PATH)
        service = DatabaseService(profiler_db_path, None)
        service.add_table_for_query("AICORE_FREQ", ["deviceId", "freq"])
        service.add_table_for_query("RANK_DEVICE_MAP", ["rankId"])
        service_res = service.query_data()
        aic_freq = service_res.get("AICORE_FREQ", None)
        rank_id = service_res.get("RANK_DEVICE_MAP", None)
        if aic_freq is None or aic_freq.empty:
            logger.error(f"No aic freq data found in {profiler_db_path}.")
            return None, None
        if rank_id is None or rank_id.empty:
            logger.error(f"No rank_id data found in {profiler_db_path}.")
            return None, None
        rank_id = rank_id["rankId"].values[0]
        freq_arr = aic_freq["freq"].values
        freqs = list(set(freq_arr))
        freqs.sort()
        return freqs, rank_id
