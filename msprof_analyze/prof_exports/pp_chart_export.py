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

from msprof_analyze.prof_common.db_manager import DBManager
from msprof_analyze.prof_common.constant import Constant
from msprof_analyze.prof_exports.base_stats_export import BaseStatsExport


class PPChartExport(BaseStatsExport):
    QUERY = """
    SELECT
        {}
        MSG_IDS.value AS msg,
        TASK.startNs,
        TASK.endNs
    FROM
        MSTX_EVENTS
    JOIN
        TASK ON MSTX_EVENTS.connectionId = TASK.connectionId
    JOIN
        STRING_IDS AS MSG_IDS ON MSTX_EVENTS.message = MSG_IDS.id
    {}
    WHERE
        msg LIKE '%forward%'
        OR msg LIKE '%backward%'
        OR msg LIKE '%WeightGradStore_pop%'
        AND MSTX_EVENTS.startNs >= ? and MSTX_EVENTS.startNs <= ?
    ORDER BY
        TASK.startNs
    """

    def __init__(self, db_path, recipe_name, param_dict):
        super().__init__(db_path, recipe_name, param_dict)
        self._query = self._build_query(db_path)

    def _build_query(self, db_path):
        str1 = "0 AS step,"
        str2 = ""
        if DBManager.check_tables_in_db(db_path, Constant.TABLE_STEP_TIME):
            str1 = "step_time.id AS step,"
            str2 = """
            LEFT JOIN STEP_TIME step_time
                ON MSTX_EVENTS.startNs >= step_time.startNs
                AND MSTX_EVENTS.endNs <= step_time.endNs
            """
        return self.QUERY.format(str1, str2)

    def get_param_order(self):
        return [Constant.START_NS, Constant.END_NS]
