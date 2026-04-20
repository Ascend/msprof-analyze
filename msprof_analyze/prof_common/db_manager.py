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

import os
import sqlite3
from typing import List

from msprof_analyze.cluster_analyse.common_func.empty_class import EmptyClass
from msprof_analyze.cluster_analyse.common_func.tables_config import TablesConfig
from msprof_analyze.prof_common.sql_extention_func import SqlExtentionAggregateFunc
from msprof_analyze.prof_common.constant import Constant
from msprof_analyze.prof_common.file_manager import check_db_path_valid
from msprof_analyze.prof_common.logger import get_logger

logger = get_logger()


class DBManager:
    """
    class to manage DB operation
    """
    FETCH_SIZE = 10000
    INSERT_SIZE = 10000
    MAX_ROW_COUNT = 100000000

    @staticmethod
    def create_connect_db(db_path: str, mode=None) -> tuple:
        """
        create and connect database
        """
        if not check_db_path_valid(db_path):
            return EmptyClass("empty conn"), EmptyClass("empty curs")
        db_file_exist = os.path.exists(db_path)
        try:
            conn = sqlite3.connect(db_path)
        except sqlite3.Error as err:
            logger.error(f"Connect db failed: {err}")
            return EmptyClass("empty conn"), EmptyClass("empty curs")
        if not db_file_exist:
            try:
                os.chmod(db_path, Constant.FILE_AUTHORITY)
            except PermissionError:
                logger.error(f"Cannot chmod db file (ignore): {db_path}")
            except Exception as err:
                logger.error(f"Chmod db failed: {err}")
        try:
            # 注册自定义聚合函数
            if mode == Constant.ANALYSIS:
                for func_name, params_count, class_name in SqlExtentionAggregateFunc:
                    conn.create_aggregate(func_name, params_count, class_name)
            curs = conn.cursor()
            return conn, curs
        except sqlite3.Error as err:
            logger.error(f"Init cursor failed: {err}")
            conn.close()
            return EmptyClass("empty conn"), EmptyClass("empty curs")

    @staticmethod
    def destroy_db_connect(conn: any, curs: any) -> None:
        """
        destroy db connection
        """
        try:
            if isinstance(curs, sqlite3.Cursor):
                curs.close()
        except sqlite3.Error as err:
            logger.error(err)
        try:
            if isinstance(conn, sqlite3.Connection):
                conn.close()
        except sqlite3.Error as err:
            logger.error(err)

    @staticmethod
    def judge_table_exists(curs: any, table_name: str) -> any:
        """
        judge table exists
        """
        if not isinstance(curs, sqlite3.Cursor):
            return False
        try:
            curs.execute("select count(*) from sqlite_master where type='table' and name=?", (table_name,))
            return curs.fetchone()[0]
        except sqlite3.Error as err:
            logger.error(err)
            return False

    @staticmethod
    def sql_generate_table(table_map: str):
        header_with_type_begin = "("
        header_with_type_end = ")"
        header_with_type_list = []
        if table_map in TablesConfig.DATA:
            items = TablesConfig.DATA[table_map]
            for item in items:
                if item[0] == "index":
                    header_with_type_list.append('"' + item[0] + '" ' + item[1].split(",")[0])
                else:
                    header_with_type_list.append(item[0] + ' ' + item[1].split(",")[0])
            header_with_type_begin += ",".join(header_with_type_list)
            header_with_type_begin += header_with_type_end
            return header_with_type_begin
        return ""

    @staticmethod
    def execute_sql(conn: any, sql: str, params: any = None) -> bool:
        """
        execute sql
        """
        try:
            if isinstance(conn, sqlite3.Connection):
                if params:
                    conn.cursor().execute(sql, params)
                else:
                    conn.cursor().execute(sql)
                conn.commit()
                return True
        except sqlite3.Error as err:
            logger.error(err)
            return False
        logger.error("conn is invalid param")
        return False

    @staticmethod
    def executemany_sql(conn: any, sql: str, params: any) -> bool:
        """
        execute many sql once
        """
        try:
            if isinstance(conn, sqlite3.Connection):
                conn.cursor().executemany(sql, params)
                conn.commit()
                return True
        except sqlite3.Error as err:
            logger.error(err)
            return False
        logger.error("conn is invalid param")
        return False

    @classmethod
    def check_tables_in_db(cls, db_path: any, *tables: any) -> bool:
        if check_db_path_valid(db_path):
            conn, curs = cls.create_connect_db(db_path)
            if not (conn and curs):
                return False
            res = True
            for table in tables:
                if not cls.judge_table_exists(curs, table):
                    res = False
                    break
            cls.destroy_db_connect(conn, curs)
            return res
        return False

    @classmethod
    def create_tables(cls, db_path: any, *tables: any):
        conn, curs = cls.create_connect_db(db_path)
        if not (conn and curs):
            return
        for table_name in tables:
            if cls.judge_table_exists(curs, table_name):
                drop_sql = "drop table {0}".format(table_name)
                cls.execute_sql(conn, drop_sql)
            table_map = "{0}Map".format(table_name)
            header_with_type = cls.sql_generate_table(table_map)
            sql = "CREATE TABLE IF NOT EXISTS " + table_name + header_with_type
            cls.execute_sql(conn, sql)
        cls.destroy_db_connect(conn, curs)

    @classmethod
    def get_table_column_count(cls, db_path: any, table: any) -> int:
        conn, curs = cls.create_connect_db(db_path)
        if not (conn and curs):
            return 0
        sql = f"PRAGMA table_info({table})"
        res = 0
        try:
            curs.execute(sql)
            res = len(curs.fetchall())
        except sqlite3.Error as err:
            logger.error(err)
        finally:
            cls.destroy_db_connect(conn, curs)
        return res

    @classmethod
    def get_table_columns_name(cls, curs: any, table: any) -> List[str]:
        sql = f"PRAGMA table_info({table})"
        try:
            curs.execute(sql)
            columns = curs.fetchall()
        except sqlite3.Error as err:
            logger.error(err)
            return []
        return [column[1] for column in columns]

    @classmethod
    def fetch_all_data(cls: any, curs: any, sql: str, param: tuple = None, is_dict: bool = True) -> list:
        """
        fetch 10000 num of data from db each time to get all data
        """
        if not isinstance(curs, sqlite3.Cursor):
            return []
        data = []
        try:
            if param:
                res = curs.execute(sql, param)
            else:
                res = curs.execute(sql)
        except sqlite3.Error as err:
            logger.error(err)
            curs.row_factory = None
            return []
        try:
            description = res.description
            while True:
                res = curs.fetchmany(cls.FETCH_SIZE)
                if is_dict:
                    data += CustomizedDictFactory.generate_dict_from_db(res, description)
                else:
                    data += res
                if len(data) > cls.MAX_ROW_COUNT:
                    logger.warning("The records count in the table exceeds the limit!")
                if len(res) < cls.FETCH_SIZE:
                    break
            return data
        except sqlite3.Error as err:
            logger.error(err)
            return []
        finally:
            curs.row_factory = None

    @classmethod
    def insert_data_into_table(cls, conn: sqlite3.Connection, table_name: str, data: list) -> None:
        """
        insert data into certain table
        """
        index = 0
        if not data:
            return
        sql = "insert into {table_name} values ({value_form})".format(
            table_name=table_name, value_form="?, " * (len(data[0]) - 1) + "?")
        while index < len(data):
            if not cls.executemany_sql(conn, sql, data[index:index + cls.INSERT_SIZE]):
                raise RuntimeError("Failed to insert data into profiler db file.")
            index += cls.INSERT_SIZE

    @classmethod
    def insert_data_into_db(cls, db_path: str, table_name: str, data: list):
        conn, curs = cls.create_connect_db(db_path)
        if not (conn and curs):
            logger.warning(f"Failed to connect to db file: {db_path}")
            return
        cls.insert_data_into_table(conn, table_name, data)
        cls.destroy_db_connect(conn, curs)

    @classmethod
    def check_columns_exist(cls, curs: any, table_name: str, columns: set) -> any:
        """
        check columns exist in table, return empty set if none of them exist, else return the set of existing columns
        """
        if not isinstance(curs, sqlite3.Cursor):
            return None
        try:
            curs.execute(f"PRAGMA table_info({table_name})")
            table_columns = {col[1] for col in curs.fetchall()}
            return columns & table_columns
        except sqlite3.Error as err:
            logger.error(err)
            return None


class CustomizedDictFactory:
    @staticmethod
    def generate_dict_from_db(data_result: any, description: any) -> any:
        description_set = [i[0] for i in description]
        res = []
        for data in data_result:
            data_dict = dict(zip(description_set, data))
            res.append(data_dict)
        return res
