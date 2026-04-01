# Copyright (c) 2026, Huawei Technologies Co., Ltd.
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
import glob
import importlib
import os
import pandas as pd
import sys
import torch
import torch_npu
from datetime import datetime, timezone
from xlsxwriter import Workbook

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from msprof_analyze.prof_common.constant import Constant
from msprof_analyze.prof_common.file_manager import FileManager
from msprof_analyze.prof_common.logger import get_logger
from msprof_analyze.prof_common.path_manager import PathManager
from msprof_analyze.prof_exports.inductor_triton_export import InductorTritonExport

logger = get_logger()


class ComparisonGenerator:
    DB_PATTERN = "*_ascend_pt/ASCEND_PROFILER_OUTPUT/ascend_pytorch_profiler.db"
    MSTX_MESSAGE = "inductor_triton"
    TRITON_OP_PREFIX = "triton_unk_fused"
    COL_MESSAGE = "message"
    COL_NAME = "Name"
    COL_DURATION = "Duration(us)"
    COL_TRITON_OP = "Triton Op"
    COL_TRITON_DURATION = "Triton Op Duration(us)"
    COL_ORIGINAL_DURATION = "Original Op Duration(us)"
    COL_ORIGINAL_TOTAL_DURATION = "Original Op Total Duration(us)"
    COL_DURATION_DIFF_RATIO = "Duration Diff Ratio"
    EXCLUDE_OPS = ["aclnnIsClose_IsCloseAiCore_IsClose", "aclnnAll_ReduceAll_ReduceAll"]
    DEFAULT = {"font_name": "Arial", 'font_size': 11, 'align': 'left', 'valign': 'vcenter', 'border': True,
               'num_format': '#,##0'}
    DEFAULT_FLOAT = {'text_wrap': True, "font_name": "Arial", 'font_size': 11, 'align': 'left', 'valign': 'vcenter', 'border': True,
                     'num_format': '#,##0.00'}
    DEFAULT_RATIO = {"font_name": "Arial", 'font_size': 11, 'align': 'left', 'valign': 'vcenter',
                     'border': True, 'num_format': '0.00%'}
    RED_RATIO = {"font_name": "Arial", 'font_size': 11, 'align': 'left', 'valign': 'vcenter',
                 'border': True, 'num_format': '0.00%', "fg_color": Constant.RED_COLOR}
    BOLD_STR = {"font_name": "Arial", 'font_size': 11, 'align': 'left', 'valign': 'vcenter', 'border': True,
                'bold': True}
    BLUE_BOLD = {"font_name": "Arial", 'font_size': 11, 'fg_color': Constant.BLUE_COLOR, 'align': 'left',
                 'valign': 'vcenter', 'bold': True, 'border': True}
    GREEN_BOLD = {"font_name": "Arial", 'font_size': 11, 'fg_color': Constant.GREEN_COLOR, 'align': 'left',
                  'valign': 'vcenter', 'bold': True, 'border': True}
    YELLOW_BOLD = {"font_name": "Arial", 'font_size': 11, 'fg_color': Constant.YELLOW_COLOR, 'align': 'left',
                   'valign': 'vcenter', 'bold': True, 'border': True}

    def __init__(self, params):
        self.fx_graph_path = params.fx_graph_path
        self.output_path = params.output_path
        self.profiling_data_path = os.path.join(params.output_path, self.MSTX_MESSAGE)
        self._result_data = None

    def process_group(self, group: pd.DataFrame):
        triton_op_mask = group[self.COL_NAME].str.startswith(self.TRITON_OP_PREFIX, na=False)
        triton_op_rows = group[triton_op_mask].copy()
        original_op_rows = group[~triton_op_mask].copy().sort_values(by=self.COL_DURATION, ascending=False)
        if triton_op_rows.empty:
            logger.warning(f"{group.name}: No triton operator found")
            return None
        if original_op_rows.empty:
            logger.warning(f"{group.name}: No original operators found")
            return None
        triton_op_name = triton_op_rows[self.COL_NAME].iloc[0]
        triton_op_duration = triton_op_rows[self.COL_DURATION].sum()
        original_op_total_duration = original_op_rows[self.COL_DURATION].sum()
        original_op_duration = '\n'.join([
            f"{row[self.COL_NAME]}:{row[self.COL_DURATION]:.2f}"
            for _, row in original_op_rows.iterrows()
        ])
        return pd.Series(
            [triton_op_name, triton_op_duration, original_op_duration, original_op_total_duration],
            index=[self.COL_TRITON_OP, self.COL_TRITON_DURATION,self.COL_ORIGINAL_DURATION,
                   self.COL_ORIGINAL_TOTAL_DURATION]
        )

    def get_all_fx_graph(self):
        sys.path.append(self.fx_graph_path)
        fx_graph_modules = []
        for dir_name in os.listdir(self.fx_graph_path):
            sub_dir_fullpath = os.path.join(self.fx_graph_path, dir_name)
            if not os.path.isdir(sub_dir_fullpath):
                continue
            target_py_path = os.path.join(sub_dir_fullpath, f"{dir_name}.py")
            if not os.path.isfile(target_py_path):
                continue
            module_name = f"{dir_name}.{dir_name}"
            try:
                fx_module = importlib.import_module(module_name)
                fx_graph_modules.append(fx_module)
            except ImportError as err:
                logger.error(f"Import error for '{module_name}': {err}")
            except Exception as err:
                logger.error(f"Unexpected error for '{module_name}': {err}", exc_info=True)
        return fx_graph_modules

    def get_prof_config(self):
        experimental_config = torch_npu.profiler._ExperimentalConfig(
            export_type=[
                torch_npu.profiler.ExportType.Db
            ],
            profiler_level=torch_npu.profiler.ProfilerLevel.Level0,
            mstx=True,
        )
        prof = torch_npu.profiler.profile(
            activities=[
                torch_npu.profiler.ProfilerActivity.NPU
            ],
            on_trace_ready=torch_npu.profiler.tensorboard_trace_handler(self.profiling_data_path),
            experimental_config=experimental_config)
        return prof

    def generate_compare_result(self):
        res = glob.glob(os.path.join(self.profiling_data_path, self.DB_PATTERN))
        if not res:
            logger.error(f"Invalid profiling data: {self.output_path}, "
                         f"please check if the ascend_pytorch_profiler.db file exists.")
            return
        db_path = res[0]
        FileManager.check_file_size(db_path)
        PathManager.check_input_file_path(db_path)
        df = InductorTritonExport(db_path).read_export_db()
        if df is None or df.empty:
            logger.error(f"Invalid profiling data, the db path is {db_path}")
            return
        filtered_df = df[~df[self.COL_NAME].isin(self.EXCLUDE_OPS)]
        grouped_df = filtered_df.groupby(self.COL_MESSAGE).apply(self.process_group).reset_index(drop=True)
        grouped_df.dropna(inplace=True)
        grouped_df[self.COL_DURATION_DIFF_RATIO] = (grouped_df[self.COL_TRITON_DURATION] /
                                                    grouped_df[self.COL_ORIGINAL_TOTAL_DURATION])
        self._result_data = grouped_df

    def generate_view(self):
        if self._result_data is None or self._result_data.empty:
            logger.error("Invalid comparison result, please check if the comparison result exists.")
            return
        file_path = os.path.join(self.output_path,
            f"inductor_triton_performance_comparison_result_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}.xlsx")
        num_metrics = 2
        data_cols = [
            self.COL_TRITON_OP,
            self.COL_TRITON_DURATION,
            self.COL_ORIGINAL_DURATION,
            self.COL_ORIGINAL_TOTAL_DURATION,
            self.COL_DURATION_DIFF_RATIO
        ]
        last_col_idx = len(data_cols) - 1
        str_col_indices  = [0, 2]
        with Workbook(file_path) as workbook:
            worksheet = workbook.add_worksheet()
            str_format = workbook.add_format(self.BOLD_STR)
            green_format = workbook.add_format(self.GREEN_BOLD)
            yellow_format = workbook.add_format(self.YELLOW_BOLD)
            default_ratio_format = workbook.add_format(self.DEFAULT_RATIO)
            red_ratio_format = workbook.add_format(self.RED_RATIO)
            float_format = workbook.add_format(self.DEFAULT_FLOAT)
            # write header
            r_idx = 0
            worksheet.set_column(0, last_col_idx, 27)
            for c_idx in str_col_indices:
                worksheet.set_column(c_idx, c_idx, 60)
            for c_idx, header in enumerate(data_cols):
                if c_idx < num_metrics:
                    worksheet.write(r_idx, c_idx, header, green_format)
                elif c_idx < num_metrics * 2:
                    worksheet.write(r_idx, c_idx, header, yellow_format)
                else:
                    worksheet.write(r_idx, c_idx, header, str_format)
            r_idx += 1
            # write data
            for _, row in self._result_data.iterrows():
                for c_idx, cell_data in enumerate(row):
                    cell_format = float_format
                    if c_idx == last_col_idx and cell_data:
                        cell_format = red_ratio_format if cell_data > 1 else default_ratio_format
                        cell_data = "INF" if cell_data == float('inf') else cell_data
                    worksheet.write(r_idx, c_idx, cell_data, cell_format)
                r_idx += 1
        os.chmod(file_path, Constant.FILE_AUTHORITY)
        logger.info(f"Generate comparison result successfully: {file_path}")

    def run(self):
        PathManager.remove_path_safety(self.profiling_data_path)
        fx_graph_modules = self.get_all_fx_graph()
        prof = self.get_prof_config()
        stream = torch_npu.npu.current_stream()
        prof.start()
        for index, fx_module in enumerate(fx_graph_modules):
            range_id = torch_npu.npu.mstx.range_start(f"{self.MSTX_MESSAGE}_{index}", stream)
            try:
                fx_module.run()
            except Exception as err:
                logger.error(f"Unexpected error for '{fx_module}': {err}", exc_info=True)
            torch_npu.npu.mstx.range_end(range_id)
        prof.stop()
        try:
            self.generate_compare_result()
            self.generate_view()
        except Exception as err:
            logger.error(f"Failed to generate comparison result: {err}", exc_info=True)