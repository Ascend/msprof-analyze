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

import json
import os
import pandas as pd
from datetime import datetime
from datetime import timezone

from msprof_analyze.cluster_analyse.common_func.context import ConcurrentContext
from msprof_analyze.cluster_analyse.common_func.table_constant import TableConstant
from msprof_analyze.cluster_analyse.common_func.utils import double_hash
from msprof_analyze.cluster_analyse.recipes.base_recipe_analysis import BaseRecipeAnalysis
from msprof_analyze.cluster_analyse.recipes.communication_group_map.communication_group_map import CommunicationGroupMap
from msprof_analyze.prof_common.constant import Constant
from msprof_analyze.prof_common.logger import get_logger
from msprof_analyze.prof_exports.cluster_time_summary_export import CommunicationOpWithStepExport
from msprof_analyze.prof_exports.cluster_time_summary_export import MemoryAndDispatchTimeExport
from msprof_analyze.prof_common.database_service import DatabaseService
from msprof_analyze.prof_common.db_manager import DBManager

logger = get_logger()


class OverlapInfo:
    def __init__(self, start, end, overlap_type):
        self.start = start
        self.end = end
        self.type = overlap_type


class ClusterTimeSummary(BaseRecipeAnalysis):
    COMPUTING_TYPE = 0
    COMMUNICATION_TYPE = 1
    MEMORY_TYPE = 4
    STEP_TIME = "step_time"
    STEP_TRACE = "step_trace"
    COMMUNICATION = "communication"
    MEMORY = "memory"

    def __init__(self, params):
        super().__init__(params)
        self.params = params
        self.db_paths = self._get_rank_db()
        self.stats_data = None
        self.communication_group_mapping = None

    @property
    def base_dir(self):
        return os.path.basename(os.path.dirname(__file__))

    @classmethod
    def get_memory_not_overlap(cls, df: pd.DataFrame):
        memory_not_overlap_time = 0  # free的时间段里面memory的总时间（异步拷贝）
        cur_block = OverlapInfo(df.iloc[0]["start"], df.iloc[0]["start"], -1)
        for time_info in df.itertuples():
            if cur_block.type == cls.MEMORY_TYPE:
                tmp_start = cur_block.start
                tmp_end = cur_block.end if time_info.start > cur_block.end else time_info.start
                if tmp_start < tmp_end:
                    memory_not_overlap_time += tmp_end - tmp_start
            if time_info.start > cur_block.end:
                cur_block.end = time_info.end
                cur_block.type = time_info.type
                cur_block.start = time_info.start
            else:
                cur_block.type = time_info.type if time_info.end > cur_block.end else cur_block.type
                cur_block.start = cur_block.end if time_info.end > cur_block.end else time_info.end
                cur_block.end = time_info.end if time_info.end > cur_block.end else cur_block.end
        # 此处为了添加最后一块数据
        if cur_block.type == cls.MEMORY_TYPE:
            memory_not_overlap_time += cur_block.end - cur_block.start
        return memory_not_overlap_time / Constant.TIME_UNIT_SCALE

    @classmethod
    def calculate_memory_time(cls, df: pd.DataFrame) -> pd.DataFrame:
        filtered_df = df[df['type'].isin([cls.MEMORY_TYPE])].copy()
        filtered_df['memory'] = filtered_df['end'] - filtered_df['start']
        result = filtered_df.groupby(['step'])['memory'].sum().reset_index()
        result['memory'] = result['memory'] / Constant.TIME_UNIT_SCALE
        return result

    def calculate_step_time(self, data_map, analysis_class):
        profiler_db_path = data_map.get(Constant.PROFILER_DB_PATH)
        rank_id = data_map.get(Constant.RANK_ID)
        data_service = DatabaseService(profiler_db_path, {})
        data_service.add_table_for_query(Constant.TABLE_STEP_TIME, ["id", "startNs", "endNs"])
        df = data_service.query_data().get(Constant.TABLE_STEP_TIME)
        if df is None or df.empty:
            df = pd.DataFrame(
                {"id": [-1], "stepTime": None}
            )
        else:
            df["stepTime"] = (df["endNs"] - df["startNs"]) / Constant.TIME_UNIT_SCALE
        result_df = df[["id", "stepTime"]].rename(columns={"id": "step"})
        result_df.insert(0, "rank", rank_id)
        return result_df

    def calculate_step_trace_time(self, data_map, analysis_class):
        analysis_db_path = data_map.get(Constant.ANALYSIS_DB_PATH)
        rank_id = data_map.get(Constant.RANK_ID)
        data_service = DatabaseService(analysis_db_path, {})
        data_service.add_table_for_query(Constant.TABLE_STEP_TRACE, ["step", "computing",
                                                                     "communication_not_overlapped", "overlapped",
                                                                     "communication", "free", ])
        df = data_service.query_data().get(Constant.TABLE_STEP_TRACE)
        if df is None or df.empty:
            logger.warning(f"There is no TABLE_STEP_TRACE data in {analysis_db_path}.")
            return None
        df.insert(0, "rank", rank_id)
        df["step"] = df["step"].fillna("-1").astype(int)
        return df

    def calculate_communication_time(self, data_map, analysis_class):
        analysis_db_path = data_map.get(Constant.PROFILER_DB_PATH)
        profiler_db_path = data_map.get(Constant.PROFILER_DB_PATH)
        step_range = data_map.get(Constant.STEP_RANGE)
        df = CommunicationOpWithStepExport(analysis_db_path, analysis_class, step_range,
            step_exits=DBManager.check_tables_in_db(profiler_db_path,
                                                    Constant.TABLE_COMM_ANALYZER_TIME,)).read_export_db()
        if df is None or df.empty:
            logger.warning(f"There is no communication op data in {analysis_db_path}.")
            return None
        return df

    def calculate_transmit_and_wait_df(self, communication_df):
        transmit_and_wait_df = pd.DataFrame(columns=["rank", "step", "communicationWaitStageTime",
                                                     "communicationTransmitStageTime"])
        if communication_df.empty:
            logger.warning(f"There is no communication op data in cluster, skip calculate transmit and wait time")
            return transmit_and_wait_df

        # 得到group_name与rank_set的对应关系
        rank_set_df = self.communication_group_mapping
        if rank_set_df is None or rank_set_df.empty:
            return transmit_and_wait_df

        # 将"(2)"或者"(2,4,6,8)"这样从CommunicationGroupMapping的rank_set列读取出来的字符串转换为集合
        def parse_rank_set(rank_set):
            try:
                ranks_list = set(map(int, rank_set.strip('()').split(',')))
                return ranks_list
            except Exception as e:
                logger.error(f"Failed to parse rank_set: {rank_set}, error: {e}")
                return set()

        rank_set_df[TableConstant.RANK_SET] = rank_set_df[TableConstant.RANK_SET].apply(parse_rank_set)
        # 这里两个表里面的group_name类型不一致
        group_to_ranks = dict(zip(rank_set_df[TableConstant.GROUP_ID], rank_set_df[TableConstant.RANK_SET]))

        # 自定义 filter 函数，检查一个 group 是否包含所有 required_ranks
        def valid_group(group):
            group_name = group.name[0]  # group.name 是 (groupName, opName, step) 的元组
            required_ranks = group_to_ranks.get(group_name, set())
            actual_ranks = set(group['rank'])
            return required_ranks.issubset(actual_ranks)

        communication_df["groupName"] = communication_df["groupName"].apply(double_hash)
        filtered_df = (communication_df.groupby(["groupName", "opName", "step"], group_keys=False).
                       filter(valid_group))
        if filtered_df.empty:
            logger.warning("No group satisfies the required rank set condition.")
            return transmit_and_wait_df

        # 通信算子分组计算传输和等待耗时
        filtered_df["communicationTransmitStageTime"] = \
            filtered_df.groupby(["groupName", "opName", "step"])["communication_time"].transform("min")
        filtered_df["communicationWaitStageTime"] = \
            filtered_df["communication_time"] - filtered_df["communicationTransmitStageTime"]
        transmit_and_wait_df = filtered_df.groupby(["rank", "step"])[
            ["communicationWaitStageTime", "communicationTransmitStageTime"]].sum().reset_index()
        return transmit_and_wait_df

    def calculate_memory_and_not_overlapped_time(self, data_map, analysis_class):
        """
        rank  step memory memoryNotOverlapComputationCommunication
        0       1    120    150
        0       2    130    150
        """
        columns = ["rank", "step", "memory", "memoryNotOverlapComputationCommunication"]
        profiler_db_path = data_map.get(Constant.PROFILER_DB_PATH)
        rank_id = data_map.get(Constant.RANK_ID)
        step_range = data_map.get(Constant.STEP_RANGE)
        df = MemoryAndDispatchTimeExport(profiler_db_path, analysis_class, step_range,
            step_exits=DBManager.check_tables_in_db(profiler_db_path, Constant.TABLE_STEP_TIME)).read_export_db()
        if df is None or df.empty:
            logger.warning(f"Can not get memcpy task info from {profiler_db_path}.")
            return pd.DataFrame(columns=columns)

        memory_df = ClusterTimeSummary.calculate_memory_time(df)
        memory_not_overlap_df = (df.groupby(["step"])[["start", "end", "type"]].apply(self.get_memory_not_overlap).
                                 reset_index(name="memoryNotOverlapComputationCommunication"))
        result_df = pd.merge(memory_df, memory_not_overlap_df, on='step', how='inner')
        result_df.insert(0, "rank", rank_id)
        return result_df

    def aggregate_stats(self, context: ConcurrentContext):
        def safe_concat(key: str) -> pd.DataFrame:
            futures = context.future_dict.get(key, [])
            df_list = [future.result() for future in futures]
            valid_dfs = [df for df in df_list if df is not None and not df.empty]
            return pd.concat(valid_dfs, ignore_index=True) if valid_dfs else pd.DataFrame()

        # 获取各DataFrame
        step_time_df = safe_concat(ClusterTimeSummary.STEP_TIME)
        step_trace_df = safe_concat(ClusterTimeSummary.STEP_TRACE)
        communication_df = safe_concat(ClusterTimeSummary.COMMUNICATION)
        memory_df = safe_concat(ClusterTimeSummary.MEMORY)

        # filter by step_id, 没有step_time/step_trace_time则无需进行后续拆解
        step_time_df = self._filter_by_step_id(step_time_df)
        step_trace_df = self._filter_by_step_id(step_trace_df)
        if step_time_df.empty or step_trace_df.empty:
            logger.error(f"No valid step_time/step_trace_time in cluster data, skipping analysis")
            return pd.DataFrame()

        # 通信时间细粒度拆解
        transmit_and_wait_df = self.calculate_transmit_and_wait_df(communication_df)
        if transmit_and_wait_df.empty:
            logger.error(f"No valid transmit and wait time in cluster data, skipping analysis")
            return pd.DataFrame()

        # 合并所有信息
        all_dfs = [step_time_df, step_trace_df, transmit_and_wait_df, memory_df]
        merged_df = all_dfs[0]
        for df in all_dfs[1:]:
            merged_df = pd.merge(merged_df, df, on=['rank', 'step'], how='outer')
        # 缺少step id的情况下需要补充stepTime
        merged_df.loc[merged_df["stepTime"].isna(), "stepTime"] = merged_df["computing"] + merged_df[
            "communication_not_overlapped"] + merged_df["free"]
        # 将所有NaN替换为0
        merged_df = merged_df.fillna(0)
        # 根据 step 和 rank 列对合并后的 DataFrame 进行排序
        merged_df = merged_df.sort_values(by=['rank', 'step'])
        merged_df["free"] = merged_df["free"] - merged_df["memoryNotOverlapComputationCommunication"]
        # 单卡场景，通信传输时间和等待时间全部置0
        if communication_df.empty or len(communication_df['rank'].unique()) == 1:
            merged_df[['communicationWaitStageTime', 'communicationTransmitStageTime']] = 0
        merged_df = merged_df.rename(columns={
            'computing': 'computation',
            'overlapped': 'communicationOverlapComputation',
            'communication_not_overlapped': 'communicationNotOverlapComputation'})
        return merged_df.sort_values(by=['rank', 'step'])

    def mapper_func(self, context: ConcurrentContext):
        for db_map in self.db_paths:
            context.submit(self.STEP_TIME, self.calculate_step_time, db_map, self._recipe_name)
            context.submit(self.STEP_TRACE, self.calculate_step_trace_time, db_map, self._recipe_name)
            context.submit(self.COMMUNICATION, self.calculate_communication_time,
                           db_map, self._recipe_name)
            context.submit(self.MEMORY, self.calculate_memory_and_not_overlapped_time,
                           db_map, self._recipe_name)

    def run(self, context: ConcurrentContext):
        logger.info("ClusterTimeSummary init.")

        if self._export_type not in [Constant.DB, Constant.TEXT]:
            logger.error(f"Invalid export type: {self._export_type} for 'cluster time summary', "
                         f"required to be {Constant.DB} or {Constant.TEXT}")
            return

        # Prepare: 需要CommunicationGroupMap
        if not self.run_communication_group_map_recipe(context):
            return

        # 数据处理与分析
        try:
            self.mapper_func(context)
            context.wait_all_futures()
            self.stats_data = self.aggregate_stats(context)
            if self._export_type == Constant.DB:
                self.dump_data(self.stats_data, Constant.DB_CLUSTER_COMMUNICATION_ANALYZER,
                               Constant.TABLE_CLUSTER_TIME_SUMMARY, index=False)
            elif self._export_type == Constant.TEXT:
                file_name = f"cluster_time_summary_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}.csv"
                self.stats_data = self.stats_data.rename(columns={
                    "rank": "Rank",
                    "step": "Step",
                    "stepTime": "Step Time(us)",
                    "computation": "Computation(us)",
                    "communicationNotOverlapComputation": "Communication Not Overlap Computation(us)",
                    "communicationOverlapComputation": "Communication Overlap Computation(us)",
                    "communication": "Communication(us)",
                    "free": "Free(us)",
                    "communicationWaitStageTime": "Communication Wait Stage Time(us)",
                    "communicationTransmitStageTime": "Communication Transmit Stage Time(us)",
                    "memory": "Memory(us)",
                    "memoryNotOverlapComputationCommunication": "Memory Not Overlap Computation Communication(us)",
                })
                self.dump_data(self.stats_data, file_name=file_name, index=False)
        except Exception as err:
            logger.error("Execute ClusterTimeSummary with exception: %s" % str(err))
            return

    def run_communication_group_map_recipe(self, context):
        """
        Run Recipe to create CommunicationGroupMapping table
        """
        logger.info(f"Run CommunicationGroupMap recipe first to get {Constant.TABLE_COMMUNICATION_GROUP_MAPPING} table")
        try:
            group_map_recipe = CommunicationGroupMap(self.params)
            self.communication_group_mapping = group_map_recipe.generate_communication_group_mapping(context)
        except Exception as e:
            logger.error(f"Run CommunicationGroupMap recipe failed: {e}!")
            return False
        return True

    def _filter_by_step_id(self, df):
        if self._step_id == Constant.VOID_STEP or 'step' not in df.columns:
            return df
        return df[df['step'] == self._step_id]
