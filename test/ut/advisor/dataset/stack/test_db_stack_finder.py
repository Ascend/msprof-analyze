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

import unittest
from unittest.mock import patch
import pandas as pd
from msprof_analyze.advisor.dataset.stack.db_stack_finder import DBStackFinder
from msprof_analyze.cluster_analyse.common_func.empty_class import EmptyClass


class TestDBStackFinder(unittest.TestCase):

    @patch("pandas.read_sql")
    @patch("os.path.exists", return_value=True)
    @patch("msprof_analyze.prof_common.db_manager.DBManager.create_connect_db",
           return_value=(EmptyClass("empty conn"), EmptyClass("empty curs")))
    @patch("msprof_analyze.prof_common.db_manager.DBManager.check_tables_in_db", return_value=True)
    def test_get_task_stack_by_op_name_return_stack_info_when_op_stack_info_exists(self,
        mock_check_tables_in_db, mock_create_connect_db, mock_exists, mock_read_sql):
        mock_read_sql.return_value = pd.DataFrame(
            {
                "op_name": ["aclnnMul_MulAiCore_Mul"],
                "task_id": [3],
                "task_type": ["AI_VECTOR_CORE"],
                "api_name": ["aclnnMul"],
                "ts": [1],
                "dur": [2.2],
                "call_stack": ["/test/test.py(16):test"]
            }
        )
        db_stack_finder = DBStackFinder("")
        stack_info = db_stack_finder.get_task_stack_by_op_name(["aclnnMul_MulAiCore_Mul"], "AI_VECTOR_CORE")
        self.assertEqual(stack_info, [[3, "aclnnMul_MulAiCore_Mul", "AI_VECTOR_CORE", "/test/test.py(16):test"]])

    @patch("pandas.read_sql")
    @patch("os.path.exists", return_value=True)
    @patch("msprof_analyze.prof_common.db_manager.DBManager.create_connect_db",
           return_value=(EmptyClass("empty conn"), EmptyClass("empty curs")))
    @patch("msprof_analyze.prof_common.db_manager.DBManager.check_tables_in_db", return_value=True)
    def test_get_task_stack_by_op_name_return_stack_info_when_op_stack_info_not_exists(self,
        mock_check_tables_in_db, mock_create_connect_db, mock_exists, mock_read_sql):
        mock_read_sql.return_value = pd.DataFrame()
        db_stack_finder = DBStackFinder("")
        stack_info = db_stack_finder.get_task_stack_by_op_name(["aclnnMul_MulAiCore_Mul"], "AI_VECTOR_CORE")
        self.assertEqual(stack_info, [])

    @patch("pandas.read_sql")
    @patch("os.path.exists", return_value=True)
    @patch("msprof_analyze.prof_common.db_manager.DBManager.create_connect_db",
           return_value=(EmptyClass("empty conn"), EmptyClass("empty curs")))
    @patch("msprof_analyze.prof_common.db_manager.DBManager.check_tables_in_db", return_value=True)
    def test_get_api_stack_by_api_index_return_stack_info_when_stack_info_exists(self,
        mock_check_tables_in_db, mock_create_connect_db, mock_exists, mock_read_sql):
        mock_read_sql.return_value = pd.DataFrame(
            {
                "dataset_index": [15],
                "name": ["aten::rand"],
                "task_type": ["AI_VECTOR_CORE"],
                "ts": [1],
                "dur": [2.2],
                "call_stack": ["/test/test.py(16):test"]
            }
        )
        db_stack_finder = DBStackFinder("")
        stack_info = db_stack_finder.get_api_stack_by_api_index([15])
        self.assertEqual(stack_info, {15: "/test/test.py(16):test"})
