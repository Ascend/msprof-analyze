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

import csv
import os
import re
from abc import abstractmethod
from typing import List, Dict
import pandas as pd

from msprof_analyze.prof_common.constant import Constant
from msprof_analyze.prof_common.db_manager import DBManager
from msprof_analyze.advisor.dataset.profiling.info_collection import logger
from msprof_analyze.advisor.utils.utils import get_file_path_from_directory, SafeOpen, format_excel_title
from msprof_analyze.prof_common.file_manager import FileManager


class ProfilingParser:
    """
    profiling
    """

    FILE_PATTERN_MSG = ""
    FILE_INFO = ""

    file_pattern_list = []

    def __init__(self, path: str) -> None:
        self._path = path
        self._raw_data: Dict = dict()
        self._file_name = ""
        self._file_path = ""

    @property
    def path(self):
        """
        path
        """
        return self._path

    @property
    def file_path(self):
        return self._file_path

    @staticmethod
    def file_match_func(pattern):
        """file match function"""
        return lambda x: re.search(re.compile(pattern), x)

    @staticmethod
    def get_float(data) -> float:
        """
        get float or 0.0
        """
        try:
            return float(data)
        except (FloatingPointError, ValueError):
            return 0.0

    @staticmethod
    def _check_csv_file_format(csv_file_name: str, csv_content: List[List[str]]):
        if not csv_content:
            logger.error("%s is empty", csv_file_name)
            return False
        return True

    @staticmethod
    def _get_csv_title(data: List, number=0, title_index=0):
        """
        number = 0 replace (us) (ns)..
        other replace " " to "_"
        title_index: position of title default 0
        """
        title_dict: Dict[int, str] = {}
        for idx, title in enumerate(data[title_index]):
            if number == 0:
                title_dict[idx] = format_excel_title(title)
            else:
                title_dict[idx] = title.replace(" ", "_")
        return title_dict

    @staticmethod
    def _execute_sql(db_path, sql, tables_to_check=None):
        if not db_path or not sql:
            return pd.DataFrame()
        conn, cursor = None, None
        try:
            conn, cursor = DBManager.create_connect_db(db_path, Constant.ANALYSIS)
            # check table existence first if necessary
            if tables_to_check and any(not DBManager.judge_table_exists(cursor, table) for table in tables_to_check):
                logger.debug("Tables not exist: %s", tables_to_check)
                return pd.DataFrame()
            # query sql and return dataframe
            data = pd.read_sql(sql, conn)
            return data
        except Exception as e:
            logger.error("File %s read failed error: %s", db_path, e)
            return pd.DataFrame()
        finally:
            if conn and cursor:
                DBManager.destroy_db_connect(conn, cursor)

    @staticmethod
    def _check_table_column_exists(db_path, table, column):
        conn, cursor = None, None
        try:
            conn, cursor = DBManager.create_connect_db(db_path, Constant.ANALYSIS)
            cols = DBManager.get_table_columns_name(cursor, table)
            return column in cols
        except Exception as e:
            logger.error("Check %s existence in table %s error: %s", column, table, e)
            return False
        finally:
            if conn and cursor:
                DBManager.destroy_db_connect(conn, cursor)

    @abstractmethod
    def parse_from_file(self, file: str):
        """
        parse from file as a static method
        """
        # 实现解析文件的逻辑，这里可以根据需要进行扩展
        return False

    def parse_data(self) -> bool:
        """
        Parse task time file
        :return: true or false
        """
        if self._parse_from_file():
            return True
        return False

    def get_raw_data(self):
        """
        get raw file name and data
        """
        return self._file_name, self._raw_data

    def _parse_from_file(self):
        if not isinstance(self.file_pattern_list, list):
            self.file_pattern_list = [self.file_pattern_list]

        for file_pattern in self.file_pattern_list:
            file_list = get_file_path_from_directory(self._path, self.file_match_func(file_pattern))
            if not file_list:
                continue
            # get last file
            self._file_path = file_list[-1]
            if len(file_list) > 1:
                logger.warning("Multiple copies of %s were found, use %s", self.FILE_INFO, self._file_path)
            return self.parse_from_file(self._file_path)
        return False

    def _parse_csv(self, file, check_csv=True) -> bool:
        logger.debug("Parse file %s", file)
        try:
            FileManager.check_file_size(file)
        except RuntimeError as e:
            logger.error("File size check failed: %s", e)
            return False
        self._file_name = os.path.splitext(os.path.basename(file))[0]
        with SafeOpen(file, encoding="utf-8") as csv_file:
            try:
                csv_content = csv.reader(csv_file)
                for row in csv_content:
                    self._raw_data.append(row)
                if check_csv and not self._check_csv_file_format(file, self._raw_data):
                    logger.error("Invalid csv file : %s", file)
                    return False
            except OSError as error:
                logger.error("Read csv file failed : %s", error)
                return False

        if not csv_file:
            return False
        if not self._raw_data:
            logger.warning("File %s has no content", file)
            return False
        return True

    def _parse_json(self, file) -> bool:
        logger.debug("Parse file %s", file)
        self._file_name = os.path.splitext(os.path.basename(file))[0]
        try:
            self._raw_data = FileManager.read_json_file(file)
        except RuntimeError as error:
            logger.error("Parse json file %s failed : %s", file, error)
            return False
        return True
