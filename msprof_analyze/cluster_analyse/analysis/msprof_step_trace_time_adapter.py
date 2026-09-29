# -------------------------------------------------------------------------
# This file is part of the MindStudio project.
# Copyright (c) 2025 Huawei Technologies Co.,Ltd.
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

from msprof_analyze.cluster_analyse.prof_bean.step_trace_time_bean import StepTraceTimeBean
from msprof_analyze.prof_common.utils import convert_to_float
from msprof_analyze.prof_common.file_manager import FileManager
from msprof_analyze.cluster_analyse.common_func.time_range_calculator import RangeCaculator
from msprof_analyze.prof_common.db_manager import DBManager
from msprof_analyze.prof_common.logger import get_logger
from msprof_analyze.cluster_analyse.common_func.table_constant import TableConstant
from msprof_analyze.cluster_analyse.common_func.time_range_calculator import CommunicationTimeRange
from msprof_analyze.prof_common.constant import Constant

logger = get_logger()


class MsprofStepTraceTimeAdapter:
    COMPUTE = "Computing"
    COMM_NOT_OVERLAP = "Communication(Not Overlapped)"
    OVERLAPPED = "Overlapped"
    COMMUNICATION = "Communication"
    FREE = "Free"
    STAGE = "Stage"
    BUBBLE = "Bubble"
    COMM_NOT_OVERLAP_EXCLUDE_RECEIVE = "Communication(Not Overlapped and Exclude Receive)"
    PREPARE = "Preparing"
    STEP = "Step"

    def __init__(self, file_path):
        self.file_path = file_path
        self._data = {
            self.STEP: None,
            self.COMPUTE: 0,
            self.COMM_NOT_OVERLAP: 0,
            self.OVERLAPPED: 0,
            self.COMMUNICATION: 0,
            self.FREE: 0,
            self.STAGE: 0,
            self.BUBBLE: 0,
            self.COMM_NOT_OVERLAP_EXCLUDE_RECEIVE: 0,
            self.PREPARE: 0,
        }

    def generate_step_trace_time_data(self):
        json_str = []
        for file_path in self.file_path:
            json_str.extend(FileManager.read_json_file(file_path))
        receive_comm = []
        analysis_data = {}
        for data in json_str:
            event_name = data.get("name", "")
            if event_name in {self.COMMUNICATION, self.COMPUTE, self.FREE, self.COMM_NOT_OVERLAP}:
                analysis_data.setdefault(event_name, []).append(data)
            elif event_name.startswith('hcom_receive'):
                receive_comm.append(data)
        for event_type, event_list in analysis_data.items():
            self._data[event_type] = sum((convert_to_float(event.get("dur", 0)) for event in event_list))
        self._data[self.BUBBLE] = sum((convert_to_float(event.get("dur", 0)) for event in receive_comm))
        self._data[self.COMM_NOT_OVERLAP_EXCLUDE_RECEIVE] = self._data[self.COMM_NOT_OVERLAP] - self._data[self.BUBBLE]
        self._data[self.OVERLAPPED] = self._data[self.COMMUNICATION] - self._data[self.COMM_NOT_OVERLAP]
        e2e_time = self._data[self.FREE] + self._data[self.COMPUTE] + self._data[self.COMM_NOT_OVERLAP]
        self._data[self.STAGE] = e2e_time - self._data[self.BUBBLE]
        return [StepTraceTimeBean(self._data)]


class MsprofStepTraceTimeDBAdapter(MsprofStepTraceTimeAdapter):
    OP_NAME = 0
    START_NS = 1
    END_NS = 2

    def __init__(self, file_path):
        super().__init__(file_path)
        self.task_db_con = None
        self.task_db_curs = None
        self.string_id_map = None
        self.compute_task_info = None
        self.communication_op_info = None

    def generate_step_trace_time_data(self):
        try:
            self._init_task_info_from_db()
        except Exception as err:
            logger.error(err)
            DBManager.destroy_db_connect(self.task_db_con, self.task_db_curs)
            return []
        origin_compute_data = self._get_compute_data()
        origin_communication_data, bubble_data = self._get_communication_data()
        compute_data = RangeCaculator.merge_continuous_intervals(origin_compute_data)
        self._data[self.COMPUTE] = sum(data.end_ts - data.start_ts for data in compute_data)
        communication_data = RangeCaculator.merge_continuous_intervals(origin_communication_data)
        self._data[self.COMMUNICATION] = sum(data.end_ts - data.start_ts for data in communication_data)
        pure_communication_data, free_data = RangeCaculator.compute_pipeline_overlap(communication_data, compute_data)
        self._data[self.COMM_NOT_OVERLAP] = sum(data.end_ts - data.start_ts for data in pure_communication_data)
        self._data[self.FREE] = sum(data.end_ts - data.start_ts for data in free_data)
        self._data[self.BUBBLE] = sum(data.end_ts - data.start_ts for data in bubble_data)
        self._data[self.COMM_NOT_OVERLAP_EXCLUDE_RECEIVE] = self._data[self.COMM_NOT_OVERLAP] - self._data[self.BUBBLE]
        self._data[self.OVERLAPPED] = self._data[self.COMMUNICATION] - self._data[self.COMM_NOT_OVERLAP]
        e2e_time = self._data[self.FREE] + self._data[self.COMPUTE] + self._data[self.COMM_NOT_OVERLAP]
        self._data[self.STAGE] = e2e_time - self._data[self.BUBBLE]
        return [
            [
                self._data[self.STEP],
                self._data[self.COMPUTE] / Constant.NS_TO_US,
                self._data[self.COMM_NOT_OVERLAP] / Constant.NS_TO_US,
                self._data[self.OVERLAPPED] / Constant.NS_TO_US,
                self._data[self.COMMUNICATION] / Constant.NS_TO_US,
                self._data[self.FREE] / Constant.NS_TO_US,
                self._data[self.STAGE] / Constant.NS_TO_US,
                self._data[self.BUBBLE] / Constant.NS_TO_US,
                self._data[self.COMM_NOT_OVERLAP_EXCLUDE_RECEIVE] / Constant.NS_TO_US,
                self._data[self.PREPARE] / Constant.NS_TO_US,
            ]
        ]

    def _init_task_info_from_db(self):
        db_path = self.file_path.get(Constant.PROFILER_DB_PATH)
        conn, curs = DBManager.create_connect_db(db_path)
        if not (conn and curs):
            logger.warning("Failed to connect to db file: %s", db_path)
            return
        self.task_db_con = conn
        self.task_db_curs = curs
        if DBManager.judge_table_exists(curs, TableConstant.TABLE_STRING_IDS):
            sql = "select id, value from {}".format(TableConstant.TABLE_STRING_IDS)  # nosec B608
            string_id_data = DBManager.fetch_all_data(curs, sql, is_dict=False)
            self.string_id_map = {data[0]: data[1] for data in string_id_data}
        if DBManager.judge_table_exists(curs, TableConstant.TABLE_COMPUTE_TASK_INFO):
            sql = (
                f"select TASK.startNs, TASK.endNs from {TableConstant.TABLE_COMPUTE_TASK_INFO} JOIN "  # nosec B608
                f"{TableConstant.TABLE_TASK} on {TableConstant.TABLE_TASK}.globalTaskId = "
                f"{TableConstant.TABLE_COMPUTE_TASK_INFO}.globalTaskId"
            )
            self.compute_task_info = DBManager.fetch_all_data(curs, sql, is_dict=False)
        if DBManager.judge_table_exists(curs, TableConstant.TABLE_COMMUNICATION_OP):
            sql = "select opName, startNs, endNs from {}".format(TableConstant.TABLE_COMMUNICATION_OP)  # nosec B608
            self.communication_op_info = DBManager.fetch_all_data(curs, sql, is_dict=False)
        DBManager.destroy_db_connect(conn, curs)

    def _get_communication_data(self):
        communication_data = []
        bubble_data = []
        for op_info in self.communication_op_info:
            op_start_time = op_info[self.START_NS]
            time_range = RangeCaculator.generate_time_range(
                op_start_time, op_info[self.END_NS], class_range=CommunicationTimeRange
            )
            communication_data.append(time_range)
            op_name = self.string_id_map.get(op_info[self.OP_NAME], '')
            if op_name.startswith('hcom_receive'):
                bubble_data.append(time_range)
        return communication_data, bubble_data

    def _get_compute_data(self):
        compute_data = []
        for compute_task in self.compute_task_info:
            compute_data.append(RangeCaculator.generate_time_range(compute_task[0], compute_task[1]))
        return compute_data
