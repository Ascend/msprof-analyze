# Copyright (c) 2025, Huawei Technologies Co., Ltd.
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
from typing import List, Dict, Optional

import pandas as pd
from msprof_analyze.prof_common.path_manager import PathManager

from msprof_analyze.prof_common.logger import get_logger

logger = get_logger()


class ExcelUtils:
    DEFAULT_FORMAT = {
        'valign': 'vcenter',
        'border': 1,
        'font_name': 'Times New Roman'
    }
    DEFAULT_HEADER_FORMAT = {
        'valign': 'vcenter',
        'bold': True,
        'border': 1,
        'bg_color': '#AFEEEE',
        'font_name': 'Times New Roman'
    }

    def __init__(self):
        self.workbook = None
        self.writer = None
        self.worksheet = None
        self.df = None
        self._formats_cache = {}

    def clear(self) -> None:
        if self.writer:
            self.writer.close()
        self.workbook = None
        self.writer = None
        self.worksheet = None
        self.df = None
        self._formats_cache = {}

    def create_excel_writer(self,
                            output_path: str,
                            file_name: str,
                            df: pd.DataFrame,
                            sheet_name: str = 'Sheet1',
                            format_config: Optional[Dict[str, Dict]] = None) -> None:
        """
        初始化ExcelWriter并写入原始数据
        Args:
            output_path: 输出目录路径
            file_name: 输出文件名
            df: 要写入的DataFrame数据
            sheet_name: 工作表名称 (可选，默认为'Sheet1')
            format_config: 格式化配置字典 (可选)
                - header: 标题行格式 (可选)
                - column: 数据列格式 (可选)
        """
        PathManager.check_path_writeable(output_path)
        self.writer = pd.ExcelWriter(os.path.join(output_path, file_name), engine='xlsxwriter')
        self.workbook = self.writer.book
        self.worksheet = self.workbook.add_worksheet(sheet_name)
        self.df = df

        # 写入标题行
        format_config = format_config or {}
        header_fmt = self._get_format(format_config.get('header', self.DEFAULT_HEADER_FORMAT))
        for col_idx, col_name in enumerate(df.columns):
            self.worksheet.write(0, col_idx, col_name, header_fmt)

        # 写入数据行
        default_fmt = self._get_format(format_config.get('column', self.DEFAULT_FORMAT))
        for row_idx, row in df.iterrows():
            for col_idx, col_name in enumerate(df.columns):
                self.worksheet.write(row_idx + 1, col_idx, row[col_name], default_fmt)

    def save_and_close(self):
        if self.writer:
            self.writer.close()
            self.writer = None
            self.workbook = None
            self.worksheet = None

    def set_column_width(self, columns_config: Dict[str, int]):
        if not self.worksheet:
            raise Exception("Worksheet has not been initialized!")

        for col, width in columns_config.items():
            col_idx = list(columns_config.keys()).index(col)
            self.worksheet.set_column(col_idx, col_idx, width)

    def set_row_height(self, row: int, height: int):
        if not self.worksheet:
            raise Exception("Worksheet not initialized")
        self.worksheet.set_row(row, height)

    def freeze_panes(self, row: int = 1, col: int = 0):
        if not self.worksheet:
            raise Exception("Worksheet has not been initialized!")
        self.worksheet.freeze_panes(row, col)

    def merge_duplicate_cells(
            self,
            columns_to_merge: List[str],
            merge_format: Optional[Dict] = None,
            header_format: Optional[Dict] = None
    ):
        """
        合并连续相同值的单元格
        参数:
            df: 输入的 DataFrame
            columns_to_merge: 需要合并的列名列表
            merge_format: 合并单元格的格式字典
            header_format: 标题行的格式字典
        """
        if not self.workbook or not self.worksheet:
            raise Exception("Worksheet has not been initialized!")

        # 设置格式
        merge_fmt = self._get_format(merge_format if merge_format else self.DEFAULT_FORMAT)
        header_fmt = self._get_format(header_format if header_format else self.DEFAULT_HEADER_FORMAT)

        # 应用标题行格式
        for col_num, value in enumerate(self.df.columns.values):
            self.worksheet.write(0, col_num, value, header_fmt)

        # 遍历需要合并的列
        for col in columns_to_merge:
            if col not in self.df.columns:
                logger.warning(f"Invalid column: {col}, not in dataframe!")
                continue

            col_idx = self.df.columns.get_loc(col)
            current_value = None
            start_row = 1  # 第一行是标题，从第二行开始
            merge_count = 0

            for i in range(len(self.df)):
                excel_row = i + 1

                if self.df[col].iloc[i] == current_value:
                    continue
                else:
                    if current_value is not None and (excel_row - 1) > start_row:
                        self.worksheet.merge_range(
                            start_row, col_idx, excel_row - 1, col_idx,
                            current_value,
                            merge_fmt
                        )
                        merge_count += 1

                    current_value = self.df[col].iloc[i]
                    start_row = excel_row

            # 处理最后一组连续相同的值
            if current_value is not None and (len(self.df)) > start_row:
                self.worksheet.merge_range(
                    start_row, col_idx, len(self.df), col_idx,
                    current_value,
                    merge_fmt
                )
                merge_count += 1

    def _get_format(self, format_dict: Dict):
        format_key = frozenset(format_dict.items())
        if format_key not in self._formats_cache:
            self._formats_cache[format_key] = self.workbook.add_format(format_dict)
        return self._formats_cache[format_key]