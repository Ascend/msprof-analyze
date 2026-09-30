# -------------------------------------------------------------------------
# This file is part of the MindStudio project.
# Copyright (c) 2024 Huawei Technologies Co.,Ltd.
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

"""
connection manager
"""

import os
import re
from typing import List

from sqlalchemy import MetaData, create_engine


class ConnectionManager:
    """
    Connection Manager
    """

    def __init__(self, path, db_name):
        self.db_path = os.path.join(path, db_name)
        self.connection = create_engine(f'sqlite:///{self.db_path}')
        self.metadata = MetaData()
        self.metadata.reflect(bind=self.connection)

    def __call__(self, *args, **kwargs):
        return self.connection

    @staticmethod
    def check_db_exists(db_path: str, dbs: List) -> bool:
        """
        check db exists
        """
        if not os.path.isdir(db_path):
            return False
        for prof_db in dbs:
            if not os.access(db_path, os.R_OK) or prof_db not in os.listdir(db_path):
                return False
        return True

    @classmethod
    def get_connection(cls, path, dbs, tables=None, is_host=False):
        """
        get connection
        """
        if is_host:
            pattern = r"/device_[0-9]"
            path = re.sub(pattern, "/host", path)
        if not cls.check_db_exists(path, dbs):
            return None
        conn = cls(path, dbs)
        if tables and not conn.check_table_exists(tables):
            return None
        return conn

    def check_table_exists(self, tables: List) -> bool:
        """
        check table exists
        """
        for table in tables:
            if table not in self.metadata.tables:
                return False
        return True

    def check_column_exists(self, table_name: str, columns: List) -> bool:
        """
        check column exists
        """
        if table_name not in self.metadata.tables:
            return False
        for column in columns:
            if column not in self.metadata.tables[table_name].columns:
                return False
        return True
