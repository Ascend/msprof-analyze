# Copyright (c) 2025-2026, Huawei Technologies Co., Ltd.
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
import pandas as pd

from msprof_analyze.prof_common.constant import Constant
from msprof_analyze.prof_common.db_manager import DBManager
from msprof_analyze.prof_common.logger import get_logger

logger = get_logger()


class DBStepTimeFinder:
    """
    通过数据库查询方式查找step_time信息
    """
    def __init__(self, db_path):
        self._db_path = db_path
        self.related_table = Constant.TABLE_STEP_TIME
        self.step_time: float = 0.0

    QUERY_AVG_STEP_TIME_SQL = """
        SELECT AVG(endNs - startNs) AS avg_step_time
        FROM STEP_TIME
        WHERE startNs IS NOT NULL
            AND endNs IS NOT NULL
            AND endNs >= startNs
    """

    def get_avg_step_time(self) -> float:
        if not DBManager.check_tables_in_db(self._db_path, self.related_table):
            return 0.0
        if not self._query_step_time(self.QUERY_AVG_STEP_TIME_SQL):
            return 0.0
        return self.step_time

    def _query_step_time(self, sql: str) -> bool:
        conn, cursor = None, None
        try:
            conn, cursor = DBManager.create_connect_db(self._db_path)
            df = pd.read_sql(sql, conn)
            if df is None or df.empty:
                return False
            self.step_time = df['avg_step_time'][0] / 1000
            return True
        except Exception as e:
            logger.error("Error loading step time: {%s}", e)
            self.step_time = 0.0
            return False
        finally:
            if conn and cursor:
                DBManager.destroy_db_connect(conn, cursor)
