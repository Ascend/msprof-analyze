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
    MSTX_EVENTS.eventType = 3 AND MSTX_EVENTS.startNs >= ? AND MSTX_EVENTS.startNs <= ?
ORDER BY
    MSTX_EVENTS.startNs
"""


class MstxMarkExport(BaseStatsExport):

    def __init__(self, db_path, recipe_name, step_range):
        super().__init__(db_path, recipe_name, step_range)
        self._query = self.get_query_statement()

    def get_query_statement(self):

        has_pytorch_api = DBManager.judge_table_exists(self._db_path, "PYTORCH_API")
        has_task = DBManager.judge_table_exists(self._db_path, "TASK")

        with_clause = ""
        framework_join = ""
        framework_start_ts = "0"

        if has_pytorch_api:
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
        )

    def get_param_order(self):
        return [Constant.START_NS, Constant.END_NS]


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
    MSTX_EVENTS.eventType = 2 AND MSTX_EVENTS.startNs >= ? AND MSTX_EVENTS.startNs <= ?
AND
    MSTX_EVENTS.connectionId != 4294967295
ORDER BY
    MSTX_EVENTS.startNs
'''


class MstxRangeExport(BaseStatsExport):

    def __init__(self, db_path, recipe_name, param_dict):
        super().__init__(db_path, recipe_name, param_dict)
        self.set_query()

    def set_query(self):
        if not DBManager.check_tables_in_db(self._db_path, "TASK"):
            self._query = self.get_query_statement_no_task()
        else:
            self._query = self.get_query_statement_with_task()

    def get_query_statement_with_task(self):
        return RANGE_QUERY_TEMPLATE.format(
            device_start_ts="TASK.startNs",
            device_end_ts="TASK.endNs",
            task_join="LEFT JOIN TASK ON MSTX_EVENTS.connectionId = TASK.connectionId",
        )

    def get_query_statement_no_task(self):
        return RANGE_QUERY_TEMPLATE.format(
            device_start_ts="0",
            device_end_ts="0",
            task_join="",
        )

    def get_param_order(self):
        return [Constant.START_NS, Constant.END_NS]

