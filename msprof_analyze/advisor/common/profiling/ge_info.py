#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# Copyright (C) 2024-2024. Huawei Technologies Co., Ltd. All rights reserved.
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

from msprof_analyze.prof_common.logger import get_logger
import os
from typing import Any, List

from msprof_analyze.prof_common.db_manager import DBManager

from msprof_analyze.advisor.dataset.profiling.db_manager import ConnectionManager
from msprof_analyze.advisor.dataset.profiling.profiling_parser import ProfilingParser
from msprof_analyze.advisor.utils.utils import check_path_valid

logger = get_logger()


class GeInfo(ProfilingParser):
    """
    ge info file
    """
    FILE_PATTERN_MSG = "ge_info.db"
    FILE_INFO = "ge info"
    STATIC_OP_STATE = "0"
    DYNAMIC_OP_STATE = "1"

    file_pattern_list = [r"ge_info.db"]

    def __init__(self, path: str) -> None:
        super().__init__(path)
        self.op_state_info_list = None

    def parse_from_file(self, file: str):
        """
        ge info
        """
        db_path, db_file = os.path.split(file)
        check_path_valid(db_path)
        if not ConnectionManager.check_db_exists(db_path, [db_file]):
            return False
        conn, cursor = DBManager.create_connect_db(db_path)
        if DBManager.judge_table_exists(cursor, 'TaskInfo'):
            sql = "select op_name, op_state from TaskInfo"
            self.op_state_info_list = DBManager.fetch_all_data(cursor, sql)
        DBManager.destroy_db_connect(conn, cursor)
        return True

    def get_static_shape_operators(self) -> List[Any]:
        return [op for op, state in self.op_state_info_list if state == self.STATIC_OP_STATE]

    def get_dynamic_shape_operators(self) -> List[Any]:
        return [op for op, state in self.op_state_info_list if state == self.DYNAMIC_OP_STATE]
