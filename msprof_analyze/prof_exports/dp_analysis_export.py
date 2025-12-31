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

from msprof_analyze.prof_exports.base_stats_export import BaseStatsExport

RANGE_QUERY = '''
SELECT
    MSG_IDS.value AS "msg",
    MSTX_EVENTS.startNs AS "cann_start_ts",
    MSTX_EVENTS.endNs AS "cann_end_ts",
    TASK.startNs AS "device_start_ts",
    TASK.endNs AS "device_end_ts",
    MSTX_EVENTS.globalTid AS "tid"
FROM
    MSTX_EVENTS
LEFT JOIN
    TASK
    ON MSTX_EVENTS.connectionId = TASK.connectionId
LEFT JOIN
    STRING_IDS AS MSG_IDS
    ON MSTX_EVENTS.message = MSG_IDS.id
LEFT JOIN
    ENUM_MSTX_EVENT_TYPE AS EVENT_TYPE
    ON MSTX_EVENTS.eventType = EVENT_TYPE.id
LEFT JOIN
    STRING_IDS AS DOMAIN_IDS
    ON MSTX_EVENTS.domainId = DOMAIN_IDS.id
WHERE
    EVENT_TYPE.name = 'start/end'
    AND DOMAIN_IDS.value = 'step_process'
AND
    MSTX_EVENTS.connectionId != 4294967295
ORDER BY
    MSTX_EVENTS.startNs
    '''


class MstxRangeExport(BaseStatsExport):

    def __init__(self, db_path, recipe_name):
        super().__init__(db_path, recipe_name)
        self._query = RANGE_QUERY


MARK_QUERY = '''
SELECT
    MSG_IDS.value AS "msg",
    MSTX_EVENTS.startNs AS "cann_ts",
    TASK.startNs AS "device_ts",
    MSTX_EVENTS.globalTid AS "tid"
FROM
    MSTX_EVENTS
LEFT JOIN
    TASK
    ON MSTX_EVENTS.connectionId = TASK.connectionId
LEFT JOIN
    STRING_IDS AS MSG_IDS
    ON MSTX_EVENTS.message = MSG_IDS.id
LEFT JOIN
    ENUM_MSTX_EVENT_TYPE AS EVENT_TYPE
    ON MSTX_EVENTS.eventType = EVENT_TYPE.id
LEFT JOIN
    STRING_IDS AS DOMAIN_IDS
    ON MSTX_EVENTS.domainId = DOMAIN_IDS.id
WHERE
    EVENT_TYPE.name = 'marker'
    AND DOMAIN_IDS.value = 'step_process'
ORDER BY
    MSTX_EVENTS.startNs
    '''


class MstxDPMarkExport(BaseStatsExport):

    def __init__(self, db_path, recipe_name):
        super().__init__(db_path, recipe_name)
        self._query = MARK_QUERY