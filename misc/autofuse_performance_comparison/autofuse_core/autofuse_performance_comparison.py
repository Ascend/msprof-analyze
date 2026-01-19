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
import glob
import os
import shutil
import sys
import pandas as pd
from datetime import datetime, timezone
from xlsxwriter import Workbook

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
from misc.autofuse_performance_comparison.utils.utils import subprocess_cmd
from misc.autofuse_performance_comparison.utils.utils import parse_args
from msprof_analyze.prof_common.constant import Constant
from msprof_analyze.prof_common.file_manager import FileManager
from msprof_analyze.prof_common.logger import get_logger
from msprof_analyze.prof_common.path_manager import PathManager
from msprof_analyze.prof_exports.autofuse_export import AutofuseExport

logger = get_logger()


class ComparisonGenerator:
    DB_PATTERN = "*_ascend_pt/ASCEND_PROFILER_OUTPUT/ascend_pytorch_profiler.db"
    DEFAULT = {"font_name": "Arial", 'font_size': 11, 'align': 'left', 'valign': 'vcenter', 'border': True,
               'num_format': '#,##0'}
    DEFAULT_FLOAT = {"font_name": "Arial", 'font_size': 11, 'align': 'left', 'valign': 'vcenter', 'border': True,
                     'num_format': '#,##0.000'}
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
        self.whole_graph = params.whole_graph
        self.subgraph_dir = params.subgraph_dir
        self.dump_path = params.dump_path
        self.output = params.output
        self.autofuse_enabled_path = os.path.join(params.output, "autofuse_enabled")
        self.autofuse_disabled_path = os.path.join(params.output, "autofuse_disabled")
        self._result_data = None

    def generate_compare_result(self):
        res_autofuse_disabled = glob.glob(os.path.join(self.autofuse_disabled_path, self.DB_PATTERN))
        res_autofuse_enabled = glob.glob(os.path.join(self.autofuse_enabled_path, self.DB_PATTERN))
        if not res_autofuse_disabled or not res_autofuse_enabled:
            logger.error("Invalid profiling data, please check if the ascend_pytorch_profiler.db file exists.")
            return
        db_autofuse_disabled = res_autofuse_disabled[0]
        db_autofuse_enabled = res_autofuse_enabled[0]
        FileManager.check_file_size(db_autofuse_disabled)
        PathManager.check_input_file_path(db_autofuse_disabled)
        FileManager.check_file_size(db_autofuse_enabled)
        PathManager.check_input_file_path(db_autofuse_enabled)
        df_autofuse_disabled = AutofuseExport(db_autofuse_disabled).read_export_db()
        df_autofuse_enabled = AutofuseExport(db_autofuse_enabled).read_export_db()
        agg_params = {
            'Name': 'first',
            'Duration(us)': 'sum',
            'aic_scalar_time(us)': 'sum',
            'aic_mte2_time(us)': 'sum',
            'aiv_scalar_time(us)': 'sum',
            'aiv_vec_time(us)': 'sum',
            'aiv_mte2_time(us)': 'sum',
            'aiv_mte3_time(us)': 'sum'
        }
        df_autofuse_disabled = df_autofuse_disabled.groupby('message', as_index=False).agg(agg_params)
        df_autofuse_enabled = df_autofuse_enabled.groupby('message', as_index=False).agg(agg_params)
        df_merge = pd.merge(
            df_autofuse_disabled.drop(columns=['Name']),
            df_autofuse_enabled,
            on='message',
            how='outer',
            suffixes=('_disabled', '_enabled')
        ).drop(columns=['message'])
        df_merge['Duration(us) Diff Ratio'] = df_merge['Duration(us)_enabled'] / df_merge['Duration(us)_disabled']
        cols = df_merge.columns.tolist()
        cols.remove('Name')
        df_merge = df_merge[['Name'] + cols]
        self._result_data = df_merge

    def generate_view(self):
        if self._result_data is None or self._result_data.empty:
            logger.error("Invalid comparison result, please check if the comparison result exists.")
            return
        file_path = os.path.join(self.output,
            f"autofuse_performance_comparison_result_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}.xlsx")
        data_cols = [
            "Duration(us)",
            "aic_scalar_time(us)",
            "aic_mte2_time(us)",
            "aiv_scalar_time(us)",
            "aiv_vec_time(us)",
            "aiv_mte2_time(us)",
            "aiv_mte3_time(us)"
        ]
        num_metrics = len(data_cols)
        total_cols_num = num_metrics * 2 + 2
        if total_cols_num != self._result_data.shape[1]:
            logger.error("Please verify the structure of the input data and column definitions.")
            return
        with Workbook(file_path) as workbook:
            worksheet = workbook.add_worksheet()
            str_format = workbook.add_format(self.BOLD_STR)
            green_foramt = workbook.add_format(self.GREEN_BOLD)
            yellow_foramt = workbook.add_format(self.YELLOW_BOLD)
            red_ratio_format = workbook.add_format(self.RED_RATIO)
            float_format = workbook.add_format(self.DEFAULT_FLOAT)
            # write header
            r_idx = 0
            start_col_disabled = 1
            end_col_disabled = start_col_disabled + num_metrics - 1
            worksheet.merge_range(r_idx, start_col_disabled, r_idx, end_col_disabled, "autofuse_disabled", green_foramt)
            start_col_enabled = end_col_disabled + 1
            end_col_enabled = start_col_enabled + num_metrics - 1
            worksheet.merge_range(r_idx, start_col_enabled, r_idx, end_col_enabled, "autofuse_enabled", yellow_foramt)
            r_idx += 2
            duration_diff_ratio_col = end_col_enabled + 1
            worksheet.set_column(0, 0, 30)
            worksheet.set_column(start_col_disabled, duration_diff_ratio_col, 17)
            for c_idx, header in enumerate(["Name"] + data_cols * 2 + ["Duration Diff Ratio"]):
                if c_idx < start_col_disabled:
                    worksheet.write(r_idx, c_idx, header, str_format)
                elif start_col_disabled <= c_idx <= end_col_disabled:
                    worksheet.write(r_idx, c_idx, header, green_foramt)
                elif start_col_enabled <= c_idx <= end_col_enabled:
                    worksheet.write(r_idx, c_idx, header, yellow_foramt)
                elif c_idx == duration_diff_ratio_col:
                    worksheet.write(r_idx, c_idx, header, str_format)
            r_idx += 1
            # write data
            for _, row in self._result_data.iterrows():
                for c_idx, cell_data in enumerate(row):
                    cell_format = float_format
                    if c_idx == duration_diff_ratio_col and cell_data and cell_data > 1:
                        cell_format = red_ratio_format
                        cell_data = "INF" if cell_data == float('inf') else cell_data
                    worksheet.write(r_idx, c_idx, cell_data, cell_format)
                r_idx += 1
        os.chmod(file_path, Constant.FILE_AUTHORITY)

    def run(self):
        PathManager.check_input_file_path(self.whole_graph)
        PathManager.check_input_directory_path(self.subgraph_dir)
        PathManager.check_input_directory_path(self.dump_path)
        if not os.path.exists(self.output):
            PathManager.make_dir_safety(self.output)
        PathManager.check_output_directory_path(self.output)
        PathManager.remove_path_safety(self.autofuse_disabled_path)
        PathManager.remove_path_safety(self.autofuse_enabled_path)
        msprof_bin = shutil.which("msprof")
        py_path = os.path.join((os.path.dirname(os.path.abspath(__file__))), "execute_graph.py")
        if msprof_bin is None:
            logger.info("msprof: command not found")
            return
        # Execute msprof to collect performance data when disabling autofuse and enabling autofuse
        os.environ["AUTOFUSE_FLAGS"] = "--enable_autofuse=false"
        cmd = ["python3", py_path, "-f", self.whole_graph, "-d", self.subgraph_dir, "-m", self.dump_path,
               "-o", self.autofuse_disabled_path]
        if subprocess_cmd(cmd):
            logger.info("Collected profiling data with autofuse disabled.")
        else:
            logger.error("Failed to collect profiling data with autofuse disabled.")
            return
        os.environ["AUTOFUSE_FLAGS"] = "--enable_autofuse=true"
        cmd = ["python3", py_path, "-f", self.whole_graph, "-d", self.subgraph_dir, "-m", self.dump_path,
               "-o", self.autofuse_enabled_path]
        if subprocess_cmd(cmd):
            logger.info("Collected profiling data with autofuse enabled.")
        else:
            logger.error("Failed to collect profiling data with autofuse enabled.")
            return
        try:
            self.generate_compare_result()
            self.generate_view()
            logger.info("Generate comparison result successfully")
        except Exception as e:
            logger.error(e)


if __name__ == "__main__":
    args = parse_args()
    ComparisonGenerator(args).run()
