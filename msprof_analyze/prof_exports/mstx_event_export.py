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
import re
import pandas as pd

from msprof_analyze.prof_exports.base_stats_export import BaseStatsExport
from msprof_analyze.prof_common.constant import Constant
from msprof_analyze.prof_common.logger import get_logger
from msprof_analyze.prof_common.db_manager import DBManager

logger = get_logger()

MARK_QUERY_TEMPLATE = """
{with_clause}
SELECT
    MSG_IDS.value AS "msg",
    MSTX_EVENTS.startNs AS "cann_ts",
    {device_start_ts} AS "device_ts",
    {framework_start_ts} AS "framework_ts",
    MSTX_EVENTS.globalTid AS "tid"
FROM
    MSTX_EVENTS
{task_join}
{framework_join}
LEFT JOIN
    STRING_IDS AS MSG_IDS
    ON MSTX_EVENTS.message = MSG_IDS.id
WHERE 
    MSTX_EVENTS.eventType = 3 {event_condition}
ORDER BY
    MSTX_EVENTS.startNs
"""


class MstxMarkExport(BaseStatsExport):

    def __init__(self, db_path, recipe_name, step_range):
        super().__init__(db_path, recipe_name, step_range)
        self._param = (step_range.get(Constant.START_NS), step_range.get(Constant.END_NS),
                       step_range.get(Constant.START_NS),
                       step_range.get(Constant.END_NS)) if step_range else None

    def get_query_condition(self, table_name):
        if self._step_range:
            return f"AND {table_name}.startNs >= ? AND {table_name}.startNs <= ?"
        else:
            return ""

    def get_query_statement(self):
        event_condition = self.get_query_condition("MSTX_EVENTS")

        has_pytorch_api = DBManager.judge_table_exists(self._db_path, "PYTORCH_API")
        has_task = DBManager.judge_table_exists(self._db_path, "TASK")

        with_clause = ""
        framework_join = ""
        framework_start_ts = "0"

        if has_pytorch_api:
            framework_condition = self._get_query_condition("PYTORCH_API")
            with_clause = f"""
                WITH
                    FRAMEWORK_API AS (
                SELECT
                    PYTORCH_API.startNs,
                    CONNECTION_IDS.connectionId
                FROM
                    PYTORCH_API
                LEFT JOIN
                    CONNECTION_IDS
                ON PYTORCH_API.connectionId = CONNECTION_IDS.id
            {framework_condition}
            )
            """
            framework_join = "LEFT JOIN FRAMEWORK_API ON MSTX_EVENTS.connectionId = FRAMEWORK_API.connectionId"
            framework_start_ts = "FRAMEWORK_API.startNs"

        task_join = ""
        device_start_ts = "0"

        if has_task:
            task_join = "LEFT JOIN TASK ON MSTX_EVENTS.connectionId = TASK.connectionId"
            device_start_ts = "TASK.startNs"

        return MARK_QUERY_TEMPLATE.format(
            with_clause=with_clause,
            device_start_ts=device_start_ts,
            framework_start_ts=framework_start_ts,
            task_join=task_join,
            framework_join=framework_join,
            event_condition=event_condition
        )

    def read_export_db(self):
        try:
            if not self._db_path:
                logger.error("db path is None.")
                return None

            conn, cursor = DBManager.create_connect_db(self._db_path, Constant.ANALYSIS)

            query = self.get_query_statement()

            if self._param is not None and re.search(Constant.SQL_PLACEHOLDER_PATTERN, query):
                data = pd.read_sql(query, conn, params=self._param)
            else:
                data = pd.read_sql(query, conn)

            DBManager.destroy_db_connect(conn, cursor)
            return data
        except Exception as e:
            logger.error(f"File {self._db_path} read failed error: {e}")
            return None


# SQL query template
RANGE_QUERY_TEMPLATE = '''
SELECT
    MSG_IDS.value AS "msg",
    MSTX_EVENTS.startNs AS "cann_start_ts",
    MSTX_EVENTS.endNs AS "cann_end_ts",
    {device_start_ts} AS "device_start_ts",
    {device_end_ts} AS "device_end_ts",
    MSTX_EVENTS.globalTid AS "tid"
FROM
    MSTX_EVENTS
{task_join}
LEFT JOIN
    STRING_IDS AS MSG_IDS
    ON MSTX_EVENTS.message = MSG_IDS.id
WHERE
    MSTX_EVENTS.eventType = 2 {event_condition}
AND
    MSTX_EVENTS.connectionId != 4294967295
ORDER BY
    MSTX_EVENTS.startNs
'''


class MstxRangeExport(BaseStatsExport):

    def __init__(self, db_path, recipe_name, step_range):
        super().__init__(db_path, recipe_name, step_range)
        self._param = (step_range.get(Constant.START_NS), step_range.get(Constant.END_NS)) if step_range else None

    def get_query_condition(self):
        if self._step_range:
            return "AND MSTX_EVENTS.startNs >= ? AND MSTX_EVENTS.startNs <= ?"
        else:
            return ""

    def get_query_statement_with_task(self):
        event_condition = self.get_query_condition()
        return RANGE_QUERY_TEMPLATE.format(
            device_start_ts="TASK.startNs",
            device_end_ts="TASK.endNs",
            task_join="LEFT JOIN TASK ON MSTX_EVENTS.connectionId = TASK.connectionId",
            event_condition=event_condition
        )

    def get_query_statement_no_task(self):
        event_condition = self.get_query_condition()
        return RANGE_QUERY_TEMPLATE.format(
            device_start_ts="0",
            device_end_ts="0",
            task_join="",
            event_condition=event_condition
        )

    def read_export_db(self):
        try:
            if not self._db_path:
                logger.error("db path is None.")
                return None

            conn, cursor = DBManager.create_connect_db(self._db_path, Constant.ANALYSIS)

            if not DBManager.judge_table_exists(cursor, "TASK"):
                query = self.get_query_statement_no_task()
            else:
                query = self.get_query_statement_with_task()

            if self._param is not None and re.search(Constant.SQL_PLACEHOLDER_PATTERN, query):
                data = pd.read_sql(query, conn, params=self._param)
            else:
                data = pd.read_sql(query, conn)

            DBManager.destroy_db_connect(conn, cursor)
            return data
        except Exception as e:
            logger.error(f"File {self._db_path} read failed error: {e}")
            return None

