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
import re

import pandas as pd

from msprof_analyze.prof_common.db_manager import DBManager
from msprof_analyze.prof_common.logger import get_logger
from msprof_analyze.prof_common.constant import Constant

logger = get_logger()


class DatabaseService:
    TABLE_TS_DICT = {
        "TASK": "startNs",
        "COMMUNICATION_OP": "startNs",
        "CANN_API": "startNs",
        "PYTORCH_API": "startNs",
        "MSTX_EVENTS": "startNs",
        "GC_RECORD": "startNs",
        "ACC_PMU": "timestampNs",
        "NIC": "timestampNs",
        "RoCE": "timestampNs",
        "LLC": "timestampNs",
        "SAMPLE_PMU_TIMELINE": "timestampNs",
        "NPU_MEM": "timestampNs",
        "NPU_MODULE_MEM": "timestampNs",
        "NPU_OP_MEM": "timestampNs",
        "HBM": "timestampNs",
        "DDR": "timestampNs",
        "HCCS": "timestampNs",
        "PCIE": "timestampNs",
        "AICORE_FREQ": "timestampNs"
    }

    def __init__(self, db_path, step_range):
        self._db_path = db_path
        self._step_range = step_range
        self._table_info = {}
        self._param = (self._step_range.get(Constant.START_NS),
                       self._step_range.get(Constant.END_NS)) if self._step_range else None

    def add_table_for_query(self, table_name: str, columns=None):
        if not isinstance(table_name, str):
            logger.error("Parameter table_name must be type of string.")
            return
        if columns is not None and not isinstance(columns, list):
            logger.error("Parameter columns must be type of list.")
            return
        self._table_info[table_name] = columns

    def query_data(self):
        result_data = {}
        if not self._table_info or not self._db_path:
            return result_data
        try:
            conn, cursor = DBManager.create_connect_db(self._db_path)
        except Exception as err:
            logger.error(err)
            return result_data
        for table_name, columns in self._table_info.items():
            if not DBManager.judge_table_exists(cursor, table_name):
                continue
            table_columns = DBManager.get_table_columns_name(cursor, table_name)
            if not columns:
                columns_str = ",".join(table_columns)
            else:
                columns = [column for column in columns if column in table_columns]
                columns_str = ",".join(columns)
            if not columns_str:
                logger.error(f"The fields to be queried in Table {table_name} are invalid.")
                return result_data
            if table_name in self.TABLE_TS_DICT and self._step_range:
                where_str = f"where {self.TABLE_TS_DICT.get(table_name)} >= ? " \
                            f"and {self.TABLE_TS_DICT.get(table_name)} <= ?"
            else:
                where_str = ""
            query_sql = f"select {columns_str} from {table_name} {where_str}"
            try:
                if self._param is not None and re.search(Constant.SQL_PLACEHOLDER_PATTERN, query_sql):
                    data = pd.read_sql(query_sql, conn, params=self._param)
                else:
                    data = pd.read_sql(query_sql, conn)
                result_data[table_name] = data
            except Exception as err:
                logger.error(err)
                break
        DBManager.destroy_db_connect(conn, cursor)
        return result_data
