# Copyright (c) 2023, Huawei Technologies Co., Ltd.
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
from abc import ABC
import os
import multiprocessing
from msprof_analyze.prof_common.logger import get_logger

import pandas as pd

from msprof_analyze.prof_common.path_manager import PathManager
from msprof_analyze.advisor.advisor_backend.compute_advice.compute_advice_base import ComputeAdviceBase
from msprof_analyze.advisor.advisor_backend.compute_advice.npu_fused.op_perf import OpPerfFactory
from msprof_analyze.advisor.advisor_backend.common_func_advisor.constant import Constant, PerfColor
from msprof_analyze.advisor.advisor_backend.common_func_advisor.trace_view_json import TraceViewJson

logger = get_logger()


class NpuSlowAdvice(ComputeAdviceBase, ABC):
    OP_PERF_SHEET = "op_perf"

    def __init__(self, collection_path: str):
        super().__init__(collection_path)
        self.kernel_details_path = ""
        self.data = pd.DataFrame()
    
    @staticmethod
    def save_to_excel(data: pd.DataFrame, file_path: str) -> None:
        PathManager.check_output_directory_path(os.path.dirname(file_path))
        with pd.ExcelWriter(file_path, engine="xlsxwriter", mode="w") as writer:
            data.index.name = Constant.TITLE.INDEX
            data.to_excel(writer, index=True, sheet_name=NpuSlowAdvice.OP_PERF_SHEET)
            NpuSlowAdvice.color_sheet(data, writer.book, writer.sheets[NpuSlowAdvice.OP_PERF_SHEET])
            writer.sheets[NpuSlowAdvice.OP_PERF_SHEET].freeze_panes = "A2"

    @staticmethod
    def color_sheet(data: pd.DataFrame, workbook, worksheet):
        color_rgb = {
            PerfColor.GREEN.name: workbook.add_format({'bg_color': '#C6EFCE'}),
            PerfColor.YELLOW.name: workbook.add_format({'bg_color': '#FFEB9C'}),
            PerfColor.RED.name: workbook.add_format({'bg_color': '#FFC7CE'}),
        }
        for row in data.iterrows():
            color = row[1][Constant.TITLE.COLOR]
            fill_format = color_rgb.get(color)
            if not fill_format:
                continue
            worksheet.set_row(row[0] + 1, None, fill_format)
    
    @staticmethod
    def update_op_row(row: tuple):
        return OpPerfFactory.build(row[1]).update()
    
    def get_call_stack(self, data: pd.DataFrame, index_id: int, ts_col: str) -> str:
        if not self.has_callstack():
            logger.warning("There is no call stack info, please set 'with_stack=True'")
            return ""
        trace_json = TraceViewJson(self.trace_view_path)
        return trace_json.get_call_stack(data, index_id, ts_col)
    
    def run(self):
        if not self.path_check():
            return self.data
        self.process()
        return self.data
    
    def process(self):
        PathManager.check_input_file_path(self.kernel_details_path)
        PathManager.check_file_size(self.kernel_details_path)
        self.data = pd.read_csv(self.kernel_details_path, dtype={"Start Time(us)": str})
        # 去除末尾的\t分隔符
        self.data["Start Time(us)"] = self.data["Start Time(us)"].apply(lambda x: x[:-1])
        with multiprocessing.Pool(multiprocessing.cpu_count()) as pool:
            result = pool.map(self.update_op_row, self.data.iterrows())
        self.data = pd.DataFrame(result)
