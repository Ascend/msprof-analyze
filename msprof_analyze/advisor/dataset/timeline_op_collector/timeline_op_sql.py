# Copyright (C) 2025. Huawei Technologies Co., Ltd. All rights reserved.
# Licensed under the Apache License, Version 2.0 (the "License");
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
import re

import pandas as pd

from msprof_analyze.prof_common.constant import Constant
from msprof_analyze.prof_common.db_manager import DBManager
from msprof_analyze.prof_common.logger import get_logger

logger = get_logger()


class TimelineEventType:
    FRAMEWORK_API = 0
    CANN_API = 1
    AICORE_FREQ = 2
    GC_RECORD = 3
    TASK_EVENT = 4
    CALL_STACK_SIMPLE = 5
    OVERLAP_ANALYSIS = 6


class TimelineEventDBSQL:
    QUERY_PYTORCH_API_SQL = """
    SELECT
        str.value AS name,
        api.startNs / 1000.0 AS ts,
        (api.endNs - api.startNs) / 1000.0 AS dur,
        ROW_NUMBER() OVER (ORDER BY api.startNs) AS dataset_index
    FROM 
        PYTORCH_API as api
    JOIN 
        STRING_IDS str ON api.name = str.id
    """

    QUEYR_CANN_API_SQL = """
    SELECT 
        CASE type.name
            WHEN 'acl' THEN 'AscendCL@' || str.value
            WHEN 'runtime' THEN 'Runtime@' || str.value
            WHEN 'node' THEN 'Node@' || str.value
            WHEN 'model' THEN 'Model@' || str.value
            ELSE str.value
        END AS name,
        api.startNs / 1000.0 AS ts,
        (api.endNs - api.startNs) / 1000.0 AS dur,
        type.name as type
    FROM 
        CANN_API as api
    JOIN 
        STRING_IDS as str ON api.name = str.id
    JOIN
        ENUM_API_TYPE as type ON api.type = type.id
    """

    QUERY_AICORE_FREQ_SQL = """
    SELECT
        'AI Core Freq' AS name,
        timestampNs / 1000.0 AS ts,
        freq AS MHz,
        LEAD(timestampNs) OVER (ORDER BY timestampNs) AS end
    FROM 
        AICORE_FREQ
    """

    QUERY_GC_SQL = """
    SELECT
        'GC' AS name,
        startNs / 1000.0 AS ts,
        (endNs - startNs) / 1000.0 AS dur
    FROM 
        GC_RECORD
    """

    QUERY_TASK_EVENT_SQL = """
    SELECT 
        str.value as name,
        CTI.taskType as 'Task Type',
        TASK.startNs / 1000.0 as ts,
        (TASK.endNs - TASK.startNs) / 1000.0 as dur,
        TASK.taskId as task_id
    FROM COMPUTE_TASK_INFO CTI
    JOIN STRING_IDS as str ON CTI.name= str.id
    JOIN TASK ON TASK.globalTaskId = CTI.globalTaskId    
    """

    QUERY_OVERLAP_ANALYSIS_SQL = """
    WITH combined_tasks AS (
        SELECT 
            TASK.startNs as startNs,
            TASK.endNs as endNs
        FROM COMPUTE_TASK_INFO CTI
        JOIN TASK ON TASK.globalTaskId = CTI.globalTaskId
    
        UNION ALL
        
        SELECT 
            COMM.startNs as startNs,
            COMM.endNs as endNs
        FROM COMMUNICATION_OP COMM
    ),
    
    -- Assign group numbers to identify continuous overlapping intervals
    grouped_tasks AS (
        SELECT 
            startNs,
            endNs,
            SUM(new_group) OVER (ORDER BY startNs) AS group_id
        FROM (
            SELECT 
                startNs,
                endNs,
                -- Detect when a new group should start (no overlap with previous max end)
                CASE WHEN startNs > MAX(endNs) OVER (
                    ORDER BY startNs 
                    ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING
                ) OR MAX(endNs) OVER (
                    ORDER BY startNs 
                    ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING
                ) IS NULL THEN 1 ELSE 0 END AS new_group
            FROM combined_tasks
        )
    )
    
    -- Merge intervals within each group
    SELECT 
        MIN(startNs) AS startNs,
        MAX(endNs) AS endNs
    FROM grouped_tasks
    GROUP BY group_id
    ORDER BY startNs
    """


    QUYER_CALL_STACK_SIMPLE = """
    SELECT
        str.value AS name,
        api.startNs / 1000.0 AS ts,
        ROW_NUMBER() OVER (ORDER BY api.startNs) AS dataset_index
    FROM 
        PYTORCH_API as api
    JOIN 
        STRING_IDS str ON api.name = str.id
    WHERE
        api.callchains is not NULL
    """

    QUERY_API_CALL_STACK_SQL = """
    WITH ranked_api AS (
        SELECT 
            api.*,
            ROW_NUMBER() OVER (ORDER BY api.startNs) AS dataset_index
        FROM 
            PYTORCH_API as api
    )

    SELECT 
        api.dataset_index,
        api_name_str.value AS name,
        api.startNs / 1000.0 AS ts,
        (api.endNs - api.startNs) / 1000.0 AS dur,
        GROUP_CONCAT(stack_str.value, ' -> ' ORDER BY call.stackDepth ASC) AS call_stack
    FROM ranked_api as api
    LEFT JOIN STRING_IDS as api_name_str ON api.name = api_name_str.id
    LEFT JOIN PYTORCH_CALLCHAINS as call ON api.callchainId = call.id
    LEFT JOIN STRING_IDS as stack_str ON call.stack = stack_str.id
    WHERE api.callchainId IS NOT NULL
    GROUP BY api.startNs, api.name, api_name_str.value, api.globalTid, api.endNs, api.dataset_index;
    """

    TABLE_MAPPING = {
        TimelineEventType.FRAMEWORK_API: [Constant.TABLE_STRING_IDS, Constant.TABLE_PYTORCH_API],
        TimelineEventType.CANN_API: [Constant.TABLE_CANN_API, Constant.TABLE_STRING_IDS,
                                     Constant.TABLE_ENUM_API_TYPE],
        TimelineEventType.AICORE_FREQ: [Constant.TABLE_AICORE_FREQ],
        TimelineEventType.GC_RECORD: [Constant.TABLE_GC_RECORD],
        TimelineEventType.TASK_EVENT: [Constant.TABLE_TASK, Constant.TABLE_STRING_IDS,
                                       Constant.TABLE_COMPUTE_TASK_INFO],
        TimelineEventType.CALL_STACK_SIMPLE: [Constant.TABLE_PYTORCH_API],
        TimelineEventType.OVERLAP_ANALYSIS: [Constant.TABLE_TASK, Constant.TABLE_COMPUTE_TASK_INFO,
                                             Constant.TABLE_COMMUNICATION_OP]
    }

    SQL_MAPPING = {
        TimelineEventType.FRAMEWORK_API: QUERY_PYTORCH_API_SQL,
        TimelineEventType.CANN_API: QUEYR_CANN_API_SQL,
        TimelineEventType.AICORE_FREQ: QUERY_AICORE_FREQ_SQL,
        TimelineEventType.GC_RECORD: QUERY_GC_SQL,
        TimelineEventType.TASK_EVENT: QUERY_TASK_EVENT_SQL,
        TimelineEventType.CALL_STACK_SIMPLE: QUYER_CALL_STACK_SIMPLE,
        TimelineEventType.OVERLAP_ANALYSIS: QUERY_OVERLAP_ANALYSIS_SQL
    }

    @staticmethod
    def get_related_table(event_type):
        if event_type not in TimelineEventDBSQL.TABLE_MAPPING:
            logger.error(f"Unsupported event type: {event_type}, can not get related table")
            return []
        return TimelineEventDBSQL.TABLE_MAPPING[event_type]

    @staticmethod
    def get_sql(event_type):
        if event_type not in TimelineEventDBSQL.SQL_MAPPING:
            logger.error(f"Unsupported event type: {event_type}, can not get sql")
            return ""
        return TimelineEventDBSQL.SQL_MAPPING[event_type]


class TimelineDBHelper:

    def __init__(self, db_path):
        self.init = False
        self.event_data_map = {}
        self.table_exist_dict = {}
        self.db_path = db_path
        self.conn, self.curs = None, None
        self.is_pta = self.is_ascend_pytorch_profiler_db(db_path)

    @staticmethod
    def is_ascend_pytorch_profiler_db(db_path):
        file_name = db_path.split(os.sep)[-1]
        pattern = r'ascend_pytorch_profiler(?:_\d+)?\.db$'
        match = re.search(pattern, file_name)
        return match is not None

    def init_timeline_db_helper(self):
        if not self.db_path:
            logger.error("db path is None.")
            return False
        self.conn, self.curs = DBManager.create_connect_db(self.db_path)
        self.init = bool(self.conn and self.curs)
        return self.init

    def destroy_db_connection(self):
        DBManager.destroy_db_connect(self.conn, self.curs)
        self.init = False

    def check_table_exist(self, table_name):
        if table_name in self.table_exist_dict:
            return self.table_exist_dict[table_name]
        res = DBManager.judge_table_exists(self.curs, table_name)
        self.table_exist_dict[table_name] = res
        return res

    def query_timeline_event(self, event_type: TimelineEventType):
        if not self.init:
            return None

        if event_type == TimelineEventType.FRAMEWORK_API and not self.is_pta:
            return None

        if event_type in self.event_data_map:
            return self.event_data_map[event_type]

        self.event_data_map[event_type] = None

        # Check if all related tables exist
        related_tables = TimelineEventDBSQL.get_related_table(event_type)
        sql = TimelineEventDBSQL.get_sql(event_type)
        if not sql or not related_tables or any(not self.check_table_exist(t) for t in related_tables):
            return None

        # execute sql
        try:
            df = pd.read_sql(sql, self.conn)
        except Exception as err:
            logger.error(f"execute sql failed: {err}")
            return None
        self.event_data_map[event_type] = df
        return df

