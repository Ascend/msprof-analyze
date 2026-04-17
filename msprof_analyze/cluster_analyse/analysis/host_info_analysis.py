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
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

from msprof_analyze.cluster_analyse.analysis.base_analysis import BaseAnalysis
from msprof_analyze.prof_common.db_manager import DBManager
from msprof_analyze.cluster_analyse.common_func.utils import increase_shared_value
from msprof_analyze.prof_common.path_manager import PathManager
from msprof_analyze.prof_common.constant import Constant
from msprof_analyze.prof_common.logger import get_logger
from msprof_analyze.cluster_analyse.cluster_data_preprocess.msprof_data_preprocessor import MsprofDataPreprocessor
from msprof_analyze.cluster_analyse.cluster_data_preprocess.mindspore_data_preprocessor import MindsporeDataPreprocessor

logger = get_logger()


@dataclass
class HostInfoScanTask:
    rank_id: str
    profiling_dir: str
    db_path: str


@dataclass
class HostInfoScanResult:
    host_uid: str = ""
    host_name: str = ""
    rank_device_info: list = field(default_factory=list)
    warning_items: list = field(default_factory=list)


class HostInfoAnalysis(BaseAnalysis):
    TABLE_HOST_INFO = "HOST_INFO"
    TABLE_RANK_DEVICE_MAP = "RANK_DEVICE_MAP"
    DEFAULT_WORKERS = Constant.DEFAULT_PROCESSES

    def __init__(self, param: dict):
        super().__init__(param)
        self.all_rank_host_info = {}
        self.all_rank_device_info = []
        self.is_msprof = param.get(Constant.IS_MSPROF)
        self.is_mindspore = param.get(Constant.IS_MINDSPORE)

    def run(self, completed_processes=None, lock=None):
        if self.data_type != Constant.DB:
            if completed_processes and lock:
                increase_shared_value(completed_processes, lock)
            logger.info("HostInfoAnalysis completed")
            return
        self.analyze_host_info()
        self.dump_db()
        if completed_processes and lock:
            increase_shared_value(completed_processes, lock)
        logger.info("HostInfoAnalysis completed")

    def dump_db(self):
        output_path = os.path.join(self.cluster_analysis_output_path, Constant.CLUSTER_ANALYSIS_OUTPUT)
        PathManager.make_dir_safety(output_path)
        result_db = os.path.join(output_path, Constant.DB_CLUSTER_COMMUNICATION_ANALYZER)
        conn, curs = DBManager.create_connect_db(result_db)
        if not (conn and curs):
            logger.error("Failed to create db %s", str(Constant.DB_CLUSTER_COMMUNICATION_ANALYZER))
            return
        self.dump_host_info(result_db, conn)
        self.dump_rank_device_map(result_db, conn)
        DBManager.destroy_db_connect(conn, curs)

    def dump_host_info(self, result_db, db_conn):
        if not self.all_rank_host_info:
            logger.warning("No host info data be analyzed.")
            return
        DBManager.create_tables(result_db, Constant.TABLE_HOST_INFO)
        save_host_info = list(self.all_rank_host_info.items())
        sql = "insert into {} values ({value})".format(Constant.TABLE_HOST_INFO,
                                                       value="?," * (len(save_host_info[0]) - 1) + "?")
        DBManager.executemany_sql(db_conn, sql, save_host_info)

    def dump_rank_device_map(self, result_db, db_conn):
        if not self.all_rank_device_info:
            logger.warning("No rank device map data be analyzed.")
            return
        self.all_rank_device_info.sort()
        DBManager.create_tables(result_db, Constant.TABLE_RANK_DEVICE_MAP)
        sql = "insert into {} values ({value})".format(Constant.TABLE_RANK_DEVICE_MAP,
                                                       value="?," * (len(self.all_rank_device_info[0]) - 1) + "?")
        DBManager.executemany_sql(db_conn, sql, self.all_rank_device_info)

    def analyze_host_info(self):
        tasks = self._build_rank_tasks()
        results = self._scan_all_ranks(tasks)
        self._merge_results(results)

    def _build_rank_tasks(self):
        tasks = []
        for rank_id, profiling_dir in self.data_map.items():
            tasks.append(HostInfoScanTask(
                rank_id=str(rank_id),
                profiling_dir=profiling_dir,
                db_path=self._get_db_path(rank_id, profiling_dir)
            ))
        return tasks

    def _scan_all_ranks(self, tasks):
        if not tasks:
            return []
        max_workers = min(len(tasks), self.DEFAULT_WORKERS)
        if max_workers <= 1:
            return [self._scan_single_rank(task) for task in tasks]
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            return list(executor.map(self._scan_single_rank, tasks))

    def _scan_single_rank(self, task: HostInfoScanTask):
        if not task.db_path or not os.path.exists(task.db_path):
            return self._build_warning_result(task, self.TABLE_HOST_INFO, self.TABLE_RANK_DEVICE_MAP)

        conn, curs = DBManager.create_connect_db(task.db_path)
        if not (conn and curs):
            return self._build_warning_result(task, self.TABLE_HOST_INFO, self.TABLE_RANK_DEVICE_MAP)
        host_info, rank_device_info = [], []
        try:
            host_info = self._query_table_data(curs, self.TABLE_HOST_INFO, first_row_only=True)
            rank_device_info = self._get_rank_device_info(task, curs)
        finally:
            DBManager.destroy_db_connect(conn, curs)

        missing_tables = []
        if not (host_info and host_info[0]):
            missing_tables.append(self.TABLE_HOST_INFO)
        if not (rank_device_info and rank_device_info[0]):
            missing_tables.append(self.TABLE_RANK_DEVICE_MAP)
        if missing_tables:
            return self._build_warning_result(task, *missing_tables)

        host_uid, host_name = str(host_info[0][0]), str(host_info[0][1])
        rank_device_info = [list(data) + [host_uid, task.profiling_dir] for data in rank_device_info]
        return HostInfoScanResult(
            host_uid=host_uid,
            host_name=host_name,
            rank_device_info=rank_device_info
        )

    def _merge_results(self, results):
        self.all_rank_host_info = {}
        self.all_rank_device_info = []
        warning_groups = {}
        for result in results:
            if result.warning_items:
                for warning_table, warning_rank_id in result.warning_items:
                    warning_groups.setdefault(warning_table, []).append(str(warning_rank_id))
            if result.host_uid and result.host_name:
                self.all_rank_host_info[result.host_uid] = result.host_name
            if result.rank_device_info:
                self.all_rank_device_info.extend(result.rank_device_info)
        aggregated_warning = self._build_aggregated_warning_message(warning_groups)
        if aggregated_warning:
            logger.warning(aggregated_warning)

    def _get_rank_device_info(self, task: HostInfoScanTask, curs):
        if self.is_msprof:
            device_id = MsprofDataPreprocessor.get_device_id(task.profiling_dir)
            return [[task.rank_id, device_id]] if device_id is not None else []
        if self.is_mindspore:
            prof_dir = MindsporeDataPreprocessor.get_msprof_dir(task.profiling_dir)
            if not prof_dir:
                return []
            device_id = MsprofDataPreprocessor.get_device_id(prof_dir)
            return [[task.rank_id, device_id]] if device_id is not None else []
        return self._query_table_data(curs, self.TABLE_RANK_DEVICE_MAP)

    @staticmethod
    def _query_table_data(curs, table_name, first_row_only=False):
        if not DBManager.judge_table_exists(curs, table_name):
            return []
        sql = f"select * from {table_name}"
        if first_row_only:
            sql += " limit 1"
        return DBManager.fetch_all_data(curs, sql, is_dict=False)

    def _get_db_path(self, rank_id, profiling_dir):
        if self.is_msprof:
            return MsprofDataPreprocessor.get_msprof_profiler_db_path(profiling_dir)
        if self.is_mindspore:
            return os.path.join(profiling_dir, Constant.SINGLE_OUTPUT, f"ascend_mindspore_profiler_{rank_id}.db")
        return os.path.join(profiling_dir, Constant.SINGLE_OUTPUT, f"ascend_pytorch_profiler_{rank_id}.db")

    def _build_warning_result(self, task: HostInfoScanTask, *table_names: str):
        warning_items = [(table_name, str(task.rank_id)) for table_name in table_names]
        return HostInfoScanResult(warning_items=warning_items)

    @staticmethod
    def _build_aggregated_warning_message(warning_groups):
        message_parts = []
        for table_name, rank_ids in warning_groups.items():
            unique_rank_ids = list(dict.fromkeys(rank_ids))
            message_parts.append(
                f"No {table_name} data for rank(s): [{','.join(unique_rank_ids)}] in db file."
            )
        if not message_parts:
            return ""
        return " ".join(message_parts)
