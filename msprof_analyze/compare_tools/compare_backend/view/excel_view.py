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

from xlsxwriter import Workbook

from msprof_analyze.compare_tools.compare_backend.view.base_view import BaseView
from msprof_analyze.compare_tools.compare_backend.view.work_sheet_creator import WorkSheetCreator


class ExcelView(BaseView):
    def __init__(self, data_dict: dict, file_path: str, args: any):
        super().__init__(data_dict)
        self._file_path = file_path
        self._args = args

    def generate_view(self):
        with Workbook(self._file_path) as workbook:
            for sheet_name, data in self._data_dict.items():
                WorkSheetCreator(workbook, sheet_name, data, self._args).create_sheet()
