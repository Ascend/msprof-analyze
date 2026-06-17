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
