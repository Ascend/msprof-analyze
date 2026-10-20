# -------------------------------------------------------------------------
# This file is part of the MindStudio project.
# Copyright (c) 2024 Huawei Technologies Co.,Ltd.
#
# MindStudio is licensed under Mulan PSL v2.
# You can use this software according to the terms and conditions of the Mulan PSL v2.
# You may obtain a copy of Mulan PSL v2 at:
#
#          http://license.coscl.org.cn/MulanPSL2
#
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND,
# EITHER EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT,
# MERCHANTABILITY OR FIT FOR A PARTICULAR PURPOSE.
# See the Mulan PSL v2 for more details.
# -------------------------------------------------------------------------
import os
import re

from msprof_analyze.prof_common.db_manager import DBManager
from msprof_analyze.cluster_analyse.common_func.utils import increase_shared_value
from msprof_analyze.cluster_analyse.cluster_utils.parallel_strategy_calculator import ParallelStrategyCalculator
from msprof_analyze.cluster_analyse.prof_bean.step_trace_time_bean import StepTraceTimeBean
from msprof_analyze.prof_common.constant import Constant
from msprof_analyze.prof_common.file_manager import FileManager
from msprof_analyze.prof_common.logger import get_logger
from msprof_analyze.cluster_analyse.analysis.msprof_step_trace_time_adapter import MsprofStepTraceTimeAdapter
from msprof_analyze.cluster_analyse.cluster_data_preprocess.msprof_data_preprocessor import MsprofDataPreprocessor
from msprof_analyze.cluster_analyse.analysis.msprof_step_trace_time_adapter import MsprofStepTraceTimeDBAdapter
from msprof_analyze.cluster_analyse.analysis.stage_group_analysis import StageInfoAnalysis

logger = get_logger()


class StepTraceTimeAnalysis:
    CLUSTER_TRACE_TIME_CSV = "cluster_step_trace_time.csv"
    CLUSTER_TRACE_TIME_TABLE = "ClusterStepTraceTime"
    PROFILER_METADATA_JSON = "profiler_metadata.json"
    PARALLEL_HEADERS = ["DP Index", "PP Index", "TP Index"]
    STEP_TRACE_TIME_SQL = """
    SELECT
        step,
        computing,communication_not_overlapped,
        overlapped,
        communication,
        free,
        stage,
        bubble,
        communication_not_overlapped_and_exclude_receive,
        preparing
    FROM {}
    """

    def __init__(self, param: dict):
        self.collection_path = param.get(Constant.COLLECTION_PATH)
        self.cluster_analysis_output_path = param.get(Constant.CLUSTER_ANALYSIS_OUTPUT_PATH)
        self.data_map = param.get(Constant.DATA_MAP)
        self.communication_data_dict = param.get(Constant.COMM_DATA_DICT, {})
        self.step_time_dict = {}
        self.step_data_list = []
        self.data_type = param.get(Constant.DATA_TYPE)
        self.distributed_args = None
        self.is_msprof = param.get(Constant.IS_MSPROF)
        self.is_mindspore = param.get(Constant.IS_MINDSPORE)

    @staticmethod
    def get_max_data_row(data_group_list: list):
        if not data_group_list:
            return []
        ret = []
        for item in zip(*data_group_list):
            ret.append(max(item))
        return ret

    @staticmethod
    def find_msprof_json(path):
        msprof_pattern = r'^msprof_\d{14}\.json$'
        msprof_slice_pattern = r'^msprof_slice_\d{1}_\d{14}\.json$'
        msprof_dict, msprof_slice_dict = {}, {}
        for file_name in os.listdir(path):
            if re.match(msprof_pattern, file_name):
                timestamp = re.search(r"\d{14}", file_name).group()
                msprof_dict.setdefault(timestamp, []).append(os.path.join(path, file_name))
            elif re.match(msprof_slice_pattern, file_name):
                timestamp = re.search(r"\d{14}", file_name).group()
                msprof_slice_dict.setdefault(timestamp, []).append(os.path.join(path, file_name))
        if msprof_dict:
            max_timestamp = max(msprof_dict.keys())
            return msprof_dict.get(max_timestamp)
        if msprof_slice_dict:
            max_timestamp = max(msprof_slice_dict.keys())
            return msprof_slice_dict.get(max_timestamp)
        return []

    def run(self, completed_processes, lock):
        self.load_step_trace_time_data()
        self.analyze_step_time()
        self.partition_ranks_data()
        self.dump_data()
        increase_shared_value(completed_processes, lock)
        logger.info("StepTraceTimeAnalysis completed")

    def partition_ranks_data(self):
        if not self.distributed_args:
            return

        if not isinstance(self.distributed_args, dict):
            self.distributed_args = None
            return

        try:
            calculator = ParallelStrategyCalculator(**self.distributed_args)  # pylint: disable=not-a-mapping
            parallelism_map = calculator.run()
        except Exception as err:
            logger.error(err)
            self.distributed_args = None
            return

        if len(parallelism_map) > len(self.step_time_dict):
            missing_rank_ids = [
                rank_id for rank_id in range(len(parallelism_map)) if rank_id not in self.step_time_dict
            ]
            logger.warning(
                "Step trace data length should equal to real rank numbers, but get step data length ="
                "%s, real rank numbers = %s, maybe lost some rank ids = %s, please check your profiling "
                "data.",
                str(len(self.step_time_dict)),
                str(len(parallelism_map)),
                str(missing_rank_ids),
            )

        if len(parallelism_map) < len(self.step_time_dict):
            logger.error(
                "Step trace data length should equal to real rank numbers, but get step data length = %s,"
                " real rank numbers = %s, maybe parallel params in profiler_metadata.json is error, "
                "please check your metadata data.",
                str(len(self.step_time_dict)),
                str(len(parallelism_map)),
            )
            self.distributed_args = None
            return

        for step_data in self.step_data_list:
            rank_id = step_data[2]
            if isinstance(rank_id, int):
                # type is rank, rank_id is int
                step_data.extend(
                    list(parallelism_map[rank_id]) if parallelism_map[rank_id] else ['NA'] * len(self.PARALLEL_HEADERS)
                )
            else:
                # type is stage, rank_id is tuple
                step_data.extend(['NA'] * len(self.PARALLEL_HEADERS))

    def dump_data(self):
        if not self.step_data_list:
            logger.warning("Can't get step time info!")
            return
        if self.data_type == Constant.TEXT:
            headers = self.get_headers()
            FileManager.create_csv_file(
                self.cluster_analysis_output_path, self.step_data_list, self.CLUSTER_TRACE_TIME_CSV, headers
            )
        else:
            output_path = os.path.join(self.cluster_analysis_output_path, Constant.CLUSTER_ANALYSIS_OUTPUT)
            result_db = os.path.join(output_path, Constant.DB_CLUSTER_COMMUNICATION_ANALYZER)
            DBManager.create_tables(result_db, self.CLUSTER_TRACE_TIME_TABLE)
            column_len = DBManager.get_table_column_count(result_db, self.CLUSTER_TRACE_TIME_TABLE)
            data_len = len(self.step_data_list[0])
            if data_len < column_len:
                for data in self.step_data_list:
                    data.extend([0] * (column_len - data_len))
            conn, cursor = DBManager.create_connect_db(result_db)
            sql = "insert into {} values ({value})".format(  # nosec B608
                self.CLUSTER_TRACE_TIME_TABLE, value="?," * (len(self.step_data_list[0]) - 1) + "?"
            )
            DBManager.executemany_sql(conn, sql, self.step_data_list)
            DBManager.destroy_db_connect(conn, cursor)

    def load_step_trace_time_data(self):
        for rank_id, profiling_dir_path in self.data_map.items():
            metadata_path = os.path.join(profiling_dir_path, self.PROFILER_METADATA_JSON)
            if not self.distributed_args and os.path.exists(metadata_path):
                metadata = FileManager.read_json_file(metadata_path)
                self.distributed_args = metadata.get(Constant.DISTRIBUTED_ARGS, None) if metadata else None
            if self.data_type == Constant.TEXT:
                if self.is_msprof:
                    msprof_json = self.find_msprof_json(os.path.join(profiling_dir_path, "mindstudio_profiler_output"))
                    self.step_time_dict[rank_id] = MsprofStepTraceTimeAdapter(
                        msprof_json
                    ).generate_step_trace_time_data()
                else:
                    step_time_file = os.path.join(profiling_dir_path, Constant.SINGLE_OUTPUT, Constant.STEP_TIME_CSV)
                    if os.path.exists(step_time_file):
                        self.step_time_dict[rank_id] = FileManager.read_csv_file(step_time_file, StepTraceTimeBean)
            else:
                if self.is_msprof or self.is_mindspore:
                    profiler_db = (
                        MsprofDataPreprocessor.get_msprof_profiler_db_path(profiling_dir_path)
                        if self.is_msprof
                        else os.path.join(
                            profiling_dir_path, Constant.SINGLE_OUTPUT, f"ascend_mindspore_profiler_{rank_id}.db"
                        )
                    )
                    self.step_time_dict[rank_id] = MsprofStepTraceTimeDBAdapter(
                        {Constant.PROFILER_DB_PATH: profiler_db}
                    ).generate_step_trace_time_data()
                else:
                    step_time_file = os.path.join(
                        profiling_dir_path, Constant.SINGLE_OUTPUT, Constant.DB_COMMUNICATION_ANALYZER
                    )
                    if os.path.exists(step_time_file) and DBManager.check_tables_in_db(
                        step_time_file, Constant.TABLE_STEP_TRACE
                    ):
                        conn, cursor = DBManager.create_connect_db(step_time_file)
                        sql = self.STEP_TRACE_TIME_SQL.format(Constant.TABLE_STEP_TRACE)
                        data = DBManager.fetch_all_data(cursor, sql, is_dict=False)
                        self.step_time_dict[rank_id] = data
                        DBManager.destroy_db_connect(conn, cursor)
            if not self.step_time_dict.get(rank_id):
                logger.warning(
                    "Rank %s does not have a valid step_trace_time data in %s file.", str(rank_id), str(self.data_type)
                )

    def analyze_step_time(self):
        for rank_id, data_bean_list in self.step_time_dict.items():
            for data_bean in data_bean_list:
                if self.data_type == Constant.TEXT:
                    self.step_data_list.append([data_bean.step, Constant.RANK, rank_id] + data_bean.row)
                else:
                    self.step_data_list.append([data_bean[0], Constant.RANK, rank_id] + list(data_bean[1:]))

        stage_list = self.generate_stage_group_list()
        if not stage_list:
            return
        step_group_dict = {}
        for data_list in self.step_data_list:
            stage_group = tuple()
            for stage in stage_list:
                if data_list[2] in stage:
                    stage_group = tuple(stage)
                    break
            key = (data_list[0], stage_group)
            step_group_dict.setdefault(key, []).append(data_list[3:])

        for key, data_group_list in step_group_dict.items():
            if self.data_type == Constant.TEXT:
                self.step_data_list.append([key[0], Constant.STAGE, key[1]] + self.get_max_data_row(data_group_list))
            else:
                index = "(" + ",".join(str(i) for i in key[1]) + ")"
                self.step_data_list.append([key[0], Constant.STAGE, index] + self.get_max_data_row(data_group_list))

    def get_headers(self):
        if self.step_time_dict:
            for rank, rank_data in self.step_time_dict.items():
                if rank_data and self.distributed_args:
                    return rank_data[0].all_headers + self.PARALLEL_HEADERS
                elif rank_data:
                    return rank_data[0].all_headers
        return []

    def generate_stage_group_list(self):
        if Constant.STAGE in self.communication_data_dict:
            return self.communication_data_dict[Constant.STAGE]
        params = {
            Constant.CLUSTER_ANALYSIS_OUTPUT_PATH: self.cluster_analysis_output_path,
            Constant.DATA_TYPE: self.data_type,
            Constant.COMM_DATA_DICT: self.communication_data_dict,
        }
        stage_analyzer = StageInfoAnalysis(params)
        stage_list = stage_analyzer.run()
        return stage_list
