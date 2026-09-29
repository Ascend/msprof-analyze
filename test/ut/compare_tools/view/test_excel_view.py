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
import os
import unittest
from unittest.mock import patch

from msprof_analyze.compare_tools.compare_backend.view.excel_view import ExcelView


class TestExcelView(unittest.TestCase):
    file_path = "./test.xlsx"

    def tearDown(self) -> None:
        if not os.path.exists(self.file_path):
            raise RuntimeError("ut failed.")
        os.remove(self.file_path)

    def test_generate_view(self):
        with patch("msprof_analyze.compare_tools.compare_backend.view.work_sheet_creator."
                   "WorkSheetCreator.create_sheet"):
            ExcelView({"table1": {}, "table2": {}}, self.file_path, {}).generate_view()
