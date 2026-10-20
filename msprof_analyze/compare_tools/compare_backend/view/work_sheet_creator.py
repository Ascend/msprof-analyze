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

from msprof_analyze.compare_tools.compare_backend.utils.excel_config import ExcelConfig, CellFormatType


class WorkSheetCreator:
    def __init__(self, work_book: Workbook, sheet_name: str, data: dict, args: any):
        self._work_book = work_book
        self._sheet_name = sheet_name
        self._data = data
        self._args = args
        self._work_sheet = None
        self._row_id = 1
        self._field_format = {}
        self._diff_ratio_index = []
        self._col_ids = "ABCDEFGHIJKLMNOPQRSTUVW"

    def create_sheet(self):
        if not self._data.get("rows", []):
            return
        self._work_sheet = self._work_book.add_worksheet(self._sheet_name)
        self._write_headers()
        if "row_style" in self._data:
            self._write_data_with_row_style()
        else:
            self._write_data()

    def _write_headers(self):
        base_header_format = self._work_book.add_format(CellFormatType.GREEN_BOLD)
        com_header_format = self._work_book.add_format(CellFormatType.YELLOW_BOLD)
        com_index_range = [-1, -1]
        overhead = self._data.get("overhead", [])
        if len(overhead) >= 2:
            base_path = f"Base Profiling: {self._args.base_profiling_path}"
            self._work_sheet.merge_range(overhead[0], base_path, base_header_format)
            com_index_range = [
                self._col_ids.index(overhead[1].split(":")[0][0]),
                self._col_ids.index(overhead[1].split(":")[1][0]),
            ]
            comparison_path = f"Comparison Profiling: {self._args.comparison_profiling_path}"
            self._work_sheet.merge_range(overhead[1], comparison_path, com_header_format)
            self._row_id += 2
        for index, header in enumerate(self._data.get("headers")):
            if index in range(com_index_range[0], com_index_range[1] + 1):
                header_format = com_header_format
            else:
                header_format = base_header_format
            col_id = self._col_ids[index]
            self._work_sheet.set_column(f"{col_id}:{col_id}", header.get("width"))
            self._work_sheet.write(f"{col_id}{self._row_id}", header.get("name"), header_format)
            self._field_format[index] = header.get("type")
            ratio_white_list = [
                ExcelConfig.DIFF_RATIO,
                ExcelConfig.DIFF_TOTAL_RATIO,
                ExcelConfig.DIFF_AVG_RATIO,
                ExcelConfig.DIFF_CALLS_RATIO,
                ExcelConfig.DIFF_SELF_RATIO,
            ]
            if header.get("name") in ratio_white_list:
                self._diff_ratio_index.append(index)
        self._row_id += 1

    def _write_data(self):
        red_ratio_format = self._work_book.add_format(CellFormatType.RED_RATIO)
        for data in self._data.get("rows"):
            for index, cell_data in enumerate(data):
                cell_format = self._work_book.add_format(self._field_format.get(index))
                if index in self._diff_ratio_index and cell_data and cell_data > 1:
                    cell_format = red_ratio_format
                    cell_data = "INF" if cell_data == float('inf') else cell_data
                self._work_sheet.write(f"{self._col_ids[index]}{self._row_id}", cell_data, cell_format)
            self._row_id += 1

    def _write_data_with_row_style(self):
        """
        带行样式及缩进的sheet
        """
        red_ratio_format = self._work_book.add_format(CellFormatType.RED_RATIO)
        rows = self._data.get("rows")
        row_style = self._data.get("row_style")  # 行样式

        for data, row_style in zip(rows, row_style):
            for index, cell_data in enumerate(data):
                cell_style = {**self._field_format.get(index), **row_style}
                if index == 0:  # 0 for Index field
                    cell_style["indent"] = cell_data.count("\t")
                cell_format = self._work_book.add_format(cell_style)
                if index in self._diff_ratio_index and cell_data and cell_data > 1:
                    cell_format = red_ratio_format
                    cell_data = "INF" if cell_data == float('inf') else cell_data
                self._work_sheet.write(f"{self._col_ids[index]}{self._row_id}", cell_data, cell_format)
            self._row_id += 1
