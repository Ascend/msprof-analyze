# -------------------------------------------------------------------------
# This file is part of the MindStudio project.
# Copyright (c) 2025 Huawei Technologies Co.,Ltd.
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
import subprocess
import os
import re
import logging
import sqlite3
import pandas as pd

COMMAND_SUCCESS = 0
ST_DATA_PATH = os.getenv("MSPROF_ANALYZE_ST_DATA_PATH", "/data/msprof-analyze-st-data")


def execute_cmd(cmd):
    logging.info('Execute command:%s', " ".join(cmd))
    completed_process = subprocess.run(cmd, shell=False, stderr=subprocess.PIPE, check=False)
    if completed_process.returncode != COMMAND_SUCCESS:
        logging.error(completed_process.stderr.decode())
    return completed_process.returncode


def execute_script(cmd):
    logging.info('Execute command:%s', " ".join(cmd))
    with subprocess.Popen(cmd, shell=False, stdout=subprocess.PIPE, stderr=subprocess.STDOUT) as process:
        while process.poll() is None:
            line = process.stdout.readline().strip()
            if line:
                logging.debug(line)
        return process.returncode


def check_result_file(out_path):
    files = os.listdir(out_path)
    newest_file = None
    re_match_exp = r"^performance_comparison_result_\d{1,20}\.xlsx"
    for file_name in files:
        if re.match(re_match_exp, file_name):
            file_time = file_name.split(".")[0].split("_")[-1]
            if not newest_file or file_time > newest_file.split(".")[0].split("_")[-1]:
                newest_file = file_name

    return newest_file


def select_count(db_path: str, query: str):
    """
    Execute a SQL query to count the number of records in the database.
    """
    conn, cursor = create_connect_db(db_path)
    cursor.execute(query)
    count = cursor.fetchone()
    destroy_db_connect(conn, cursor)
    return count[0]


def select_by_query(db_path: str, query: str, db_class):
    """
    Execute a SQL query and return the first record as an instance of db_class.
    """
    conn, cursor = create_connect_db(db_path)
    cursor.execute(query)
    rows = cursor.fetchall()
    dbs = [db_class(*row) for row in rows]
    destroy_db_connect(conn, cursor)
    return dbs[0]


def read_sql(db_path: str, query: str):
    """
    Execute a SQL query and return the result as a pandas DataFrame.
    """
    conn, cursor = create_connect_db(db_path)
    try:
        return pd.read_sql(query, conn)
    finally:
        destroy_db_connect(conn, cursor)


def create_connect_db(db_file: str) -> tuple:
    """
    Create a connection to the SQLite database.
    """
    try:
        conn = sqlite3.connect(db_file)
        curs = conn.cursor()
        return conn, curs
    except sqlite3.Error as e:
        logging.error("Unable to connect to database: %s", e)
        return None, None


def destroy_db_connect(conn: any, curs: any) -> None:
    """
    Close the database connection and cursor.
    """
    try:
        if isinstance(curs, sqlite3.Cursor):
            curs.close()
    except sqlite3.Error as err:
        logging.error("%s", err)
    try:
        if isinstance(conn, sqlite3.Connection):
            conn.close()
    except sqlite3.Error as err:
        logging.error("%s", err)
