# Copyright (c) 2026, Huawei Technologies Co., Ltd.
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
import argparse
import pandas as pd


from tqdm import tqdm
from typing import List, Tuple
from msprof_analyze.prof_common.constant import Constant
from msprof_analyze.prof_common.logger import get_logger
from msprof_analyze.cluster_analyse.common_func.context import ConcurrentContext
from msprof_analyze.cluster_analyse.recipes.base_recipe_analysis import BaseRecipeAnalysis
from msprof_analyze.prof_common.database_service import DatabaseService
from msprof_analyze.prof_common.interval_manager import IntervalManager
from msprof_analyze.prof_exports.computational_op_masking_export import CommunicationOpWithExport
from msprof_analyze.prof_exports.computational_op_masking_export import ComputeTaskInfoWithExport

logger = get_logger()


class RetDataFrames:
    def __init__(self, step_df, communication_df, computation_df):
        self.step_df = step_df
        self.communication_df = communication_df
        self.computation_df = computation_df


class ComputationalOpMasking(BaseRecipeAnalysis):
    PARALLEL_INPUT_NAME = "parallel_types"
    PARALLEL_COL_NAME = "parallelType"
    STEP_LINEARITY = "step_linearity"
    Computational_Operator_Linearity_COLUMNS = [
        "stepId",
        "parallelType",
        "stepStartTime",
        "stepEndTime",
        "totalCommunicationOperatorTime",
        "timeRatioOfStepCommunicationOperator",
        "totalTimeWithoutCommunicationBlackout",
        "ratioOfUnmaskedCommunication",
    ]
    parallel_types = [("dp", "edp"), ("edp",), ("dp",), ("ep",), ("pp",), ("mp",), ("tp",)]
    step_columns = ["id", "startNs", "endNs"]

    def __init__(self, params):
        super().__init__(params)
        self.linearity_ret = pd.DataFrame()
        self.params = params
        self.db_paths = self._get_rank_db()
        if self._extra_args.get(self.PARALLEL_INPUT_NAME) is not None:
            self.parallel_types = [tuple(item) for item in self._extra_args[self.PARALLEL_INPUT_NAME]]


    @property
    def base_dir(self):
        return os.path.basename(os.path.dirname(__file__))

    @classmethod
    def add_parser_argument(cls, parser):
        parser.add_argument(
            "--parallel_types",
            type=cls.parse_parallel_type,
            default=cls.parallel_types,
            help=(
                "Parallel strategy groups. Format: 'a;b,c;d,e,f' (NO trailing semicolon). "
                "Each group: 1+ comma-separated names. Example:'dp;mp,tp'.Default: %(default)s"
            )
        )
        BaseRecipeAnalysis.add_parser_argument(parser)

    def parse_parallel_type(value: str) -> List[Tuple[str, ...]]:
        """
        Parse a string like "a;b,c;d,e,f" into[('a',), ('b','c'), ('d','e','f')].
        Rules:
            -Groups are separated by ';'
            -Items within a group are separated by ','
            -Empty input returns []
            -Empty groups (e.g. "a;;b") are ignored (not an error)**
            -Whitespace around items is stripped
        """
        if not value or not value.strip():
            return []
        groups = []
        for i, group_str in enumerate(value.split(";")):
            group_str = group_str.strip()
            if not group_str:
                raise argparse.ArgumentTypeError(
                    f"Empty group at position ({i + 1} (input: '{value}')"
                )
            items = [item.strip() for item in group_str.split(",")]
            if any(not item for item in items):
                raise argparse.ArgumentTypeError(
                    f"Empty item in group (after filtering empty groups): '{group_str}'"
                )
            groups.append(tuple(items))
        return groups

    def aggregate_stats(self, context: ConcurrentContext):
        def safe_concat(key: str) -> pd.DataFrame:
            futures = context.future_dict.get(key, [])
            df_list = [future.result() for future in futures]
            valid_dfs = [df for df in df_list if df is not None and not df.empty]
            return pd.concat(valid_dfs, ignore_index=True) if valid_dfs else pd.DataFrame()

        # Get each DataFrame
        step_time_df = safe_concat(ComputationalOpMasking.STEP_LINEARITY)
        return step_time_df

    def mapper_func(self, context: ConcurrentContext):
        for db_map in self.db_paths:
            context.submit(self.STEP_LINEARITY, self.get_linearity_df, db_map, self._recipe_name)

    def run(self, context: ConcurrentContext):
        self.mapper_func(context)
        context.wait_all_futures()
        self.linearity_ret = self.aggregate_stats(context)
        if self.linearity_ret.empty:
            logger.warning("No data available for linearity analysis.")
            return
        if self._export_type == Constant.DB:
            self.save_db()
        elif self._export_type == Constant.TEXT:
            self.save_csv()
        else:
            logger.error("Unknown export type.")

    def save_db(self):
        self.dump_data(data=self.linearity_ret,
                       file_name=Constant.DB_CLUSTER_COMMUNICATION_ANALYZER,
                       table_name=Constant.TABLE_COMPUTATIONAL_OPERATOR_MASKING_LINEARITY,
                       index=False)

    def save_csv(self):
        self.dump_data(data=self.linearity_ret, file_name="computational_operator_masking_linearity.csv", index=False)

    def get_linearity_df(self, data_map, analysis_class) -> pd.DataFrame:
        """
        Compute the linearity of communication operators.

        Args:
            step_df: DataFrame containing step information.
            communication_df: DataFrame containing communication data.
            computation_df: DataFrame containing computation data.

        Returns:
            A DataFrame containing the linearity results, or None if no data is available.
        """
        ret_df = pd.DataFrame()
        result_lst = []

        profiler_db_path = data_map.get(Constant.PROFILER_DB_PATH)
        step_range = data_map.get(Constant.STEP_RANGE)
        # If step_id does not have a specified input, the default value is -1.
        if self._step_id != -1:
            step_df = pd.DataFrame.from_dict([step_range])
        else:
            data_service = DatabaseService(profiler_db_path, step_range)
            data_service.add_table_for_query(Constant.TABLE_STEP_TIME, self.step_columns)
            step_df = data_service.query_data().get(Constant.TABLE_STEP_TIME, None)
        if step_df is None or step_df.empty:
            logger.warning(f"There is no TABLE_STEP_TIME data in {profiler_db_path}.")
            return ret_df
        communication_df = CommunicationOpWithExport(profiler_db_path, analysis_class, step_range).read_export_db()
        if communication_df is None or communication_df.empty:
            logger.warning(f"There is no TABLE_COMMUNICATION_OP data in {profiler_db_path}.")
            return ret_df
        computation_df = ComputeTaskInfoWithExport(profiler_db_path, analysis_class,step_range).read_export_db()
        if computation_df is None or computation_df.empty:
            logger.warning(f"There is no TABLE_COMPUTE_TASK_INFO data in {profiler_db_path}.")
            return ret_df

        for parallel_type in tqdm(self.parallel_types):
            filter_communication_df = communication_df[communication_df[self.PARALLEL_COL_NAME].isin(parallel_type)]
            if filter_communication_df.empty:
                continue
            for index, row in step_df.iterrows():
                step_id = row["id"]
                start_time = row["startNs"]
                end_time = row["endNs"]
                if end_time - start_time == 0:
                    continue
                filter_communication_df = filter_communication_df[(filter_communication_df["startNs"] >= start_time) &
                                                                  (filter_communication_df["endNs"] <= end_time)]
                filter_computation_df = computation_df[(computation_df["task_start_time"] >= start_time) &
                                                       (computation_df["task_end_time"] <= end_time)]
                communication_op_lst = list(zip(filter_communication_df["startNs"], filter_communication_df["endNs"]))
                computation_op_lst = list(zip(filter_computation_df["task_start_time"],
                                              filter_computation_df["task_end_time"]))
                interval_process = IntervalManager()
                merge_communication_op_lst = interval_process.merge_intervals(communication_op_lst)
                merge_computation_op_lst = interval_process.merge_intervals(computation_op_lst)

                merge_communication_op_intervals = [sample[1] - sample[0] for sample in merge_communication_op_lst]
                merge_computation_op_intervals = [sample[1] - sample[0] for sample in merge_computation_op_lst]
                total_communication_operator_time = sum(merge_communication_op_intervals)
                time_ratio_of_step_communication_operator = total_communication_operator_time / (end_time - start_time)
                uncovered = interval_process.compute_uncovered_durations(communication_op_lst, computation_op_lst)
                total_time_without_communication_blackout = sum(uncovered)
                ratio_unmasked_communication = round(sum(uncovered) / (end_time - start_time), 5)
                operator_type_str = "+".join(parallel_type)
                line_result = [step_id, operator_type_str, start_time, end_time, total_communication_operator_time,
                               time_ratio_of_step_communication_operator, total_time_without_communication_blackout,
                               ratio_unmasked_communication]
                result_lst.append(line_result)
        if len(result_lst) == 0:
            return ret_df
        ret_df = pd.DataFrame(result_lst, columns=self.Computational_Operator_Linearity_COLUMNS)
        return ret_df
