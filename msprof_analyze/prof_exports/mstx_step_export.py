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
from msprof_analyze.prof_common.db_manager import DBManager
from msprof_analyze.prof_common.constant import Constant
from msprof_analyze.prof_common.logger import get_logger

logger = get_logger()

QUERY = """
SELECT
    id AS "step_id",
    startNs AS "start_ns",
    endNs AS "end_ns"
FROM
    STEP_TIME
ORDER BY
    startNs
    """


class MstxStepExport(BaseStatsExport):

    def __init__(self, db_path, recipe_name, step_range):
        super().__init__(db_path, recipe_name, step_range)
        self._query = QUERY

    def read_export_db(self):
        try:
            if not self._db_path:
                logger.error("db path is None.")
                return None
            query = self.get_query()
            if query is None:
                logger.error("query is None.")
                return None
            conn, cursor = DBManager.create_connect_db(self._db_path, Constant.ANALYSIS)

            if not DBManager.judge_table_exists(cursor, "STEP_TIME"):
                DBManager.destroy_db_connect(conn, cursor)
                return pd.DataFrame(columns=['step_id', 'start_ns', 'end_ns'])

            if self._param is not None and re.search(Constant.SQL_PLACEHOLDER_PATTERN, query):
                data = pd.read_sql(query, conn, params=self._param)
            else:
                data = pd.read_sql(query, conn)
            DBManager.destroy_db_connect(conn, cursor)
            return data
        except Exception as e:
            logger.error(f"File {self._db_path} read failed error: {e}")
            return None