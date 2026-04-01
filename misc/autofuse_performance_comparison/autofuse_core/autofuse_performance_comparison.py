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
    COL_MESSAGE = "message"
    COL_NAME = "Name"
    COL_DURATION = "Duration(us)"
    COL_AIC_SCALAR_TIME = "aic_scalar_time(us)"
    COL_AIC_MTE2_TIME = "aic_mte2_time(us)"
    COL_AIV_SCALAR_TIME = "aiv_scalar_time(us)"
    COL_AIV_VEC_TIME = "aiv_vec_time(us)"
    COL_AIV_MTE2_TIME = "aiv_mte2_time(us)"
    COL_AIV_MTE3_TIME = "aiv_mte3_time(us)"
    COL_DURATION_DIFF_RATIO = "Duration Diff Ratio"
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
        self.output_path = params.output_path
        self.autofuse_enabled_path = os.path.join(params.output_path, "autofuse_enabled")
        self.autofuse_disabled_path = os.path.join(params.output_path, "autofuse_disabled")
        self._result_data = None

    def generate_compare_result(self):
        res_autofuse_disabled = glob.glob(os.path.join(self.autofuse_disabled_path, self.DB_PATTERN))
        res_autofuse_enabled = glob.glob(os.path.join(self.autofuse_enabled_path, self.DB_PATTERN))
        if not res_autofuse_disabled or not res_autofuse_enabled:
            logger.error(f"Invalid profiling data: {self.output_path}, "
                         f"please check if the ascend_pytorch_profiler.db file exists.")
            return
        db_autofuse_disabled = res_autofuse_disabled[0]
        db_autofuse_enabled = res_autofuse_enabled[0]
        FileManager.check_file_size(db_autofuse_disabled)
        PathManager.check_input_file_path(db_autofuse_disabled)
        FileManager.check_file_size(db_autofuse_enabled)
        PathManager.check_input_file_path(db_autofuse_enabled)
        df_autofuse_disabled = AutofuseExport(db_autofuse_disabled).read_export_db()
        if df_autofuse_disabled is None or df_autofuse_disabled.empty:
            logger.error(f"Invalid profiling data, the db path is {db_autofuse_disabled}")
            return
        df_autofuse_enabled = AutofuseExport(db_autofuse_enabled).read_export_db()
        if df_autofuse_enabled is None or df_autofuse_enabled.empty:
            logger.error(f"Invalid profiling data, the db path is {db_autofuse_enabled}")
            return
        agg_params = {
            self.COL_NAME: 'first',
            self.COL_DURATION: 'sum',
            self.COL_AIC_SCALAR_TIME: 'sum',
            self.COL_AIC_MTE2_TIME: 'sum',
            self.COL_AIV_SCALAR_TIME: 'sum',
            self.COL_AIV_VEC_TIME: 'sum',
            self.COL_AIV_MTE2_TIME: 'sum',
            self.COL_AIV_MTE3_TIME: 'sum'
        }
        df_autofuse_disabled = df_autofuse_disabled.groupby(self.COL_MESSAGE, as_index=False).agg(agg_params)
        df_autofuse_enabled = df_autofuse_enabled.groupby(self.COL_MESSAGE, as_index=False).agg(agg_params)
        df_merge = pd.merge(
            df_autofuse_disabled.drop(columns=[self.COL_NAME]),
            df_autofuse_enabled,
            on=self.COL_MESSAGE,
            how='outer',
            suffixes=('_disabled', '_enabled')
        ).drop(columns=[self.COL_MESSAGE])
        df_merge[self.COL_DURATION_DIFF_RATIO] = df_merge['Duration(us)_enabled'] / df_merge['Duration(us)_disabled']
        cols = df_merge.columns.tolist()
        cols.remove(self.COL_NAME)
        df_merge = df_merge[[self.COL_NAME] + cols]
        self._result_data = df_merge

    def generate_view(self):
        if self._result_data is None or self._result_data.empty:
            logger.error("Invalid comparison result, please check if the comparison result exists.")
            return
        file_path = os.path.join(self.output_path,
            f"autofuse_performance_comparison_result_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}.xlsx")
        data_cols = [
            self.COL_DURATION,
            self.COL_AIC_SCALAR_TIME,
            self.COL_AIC_MTE2_TIME,
            self.COL_AIV_SCALAR_TIME,
            self.COL_AIV_VEC_TIME,
            self.COL_AIV_MTE2_TIME,
            self.COL_AIV_MTE3_TIME
        ]
        num_metrics = len(data_cols)
        total_cols_num = num_metrics * 2 + 2
        if total_cols_num != self._result_data.shape[1]:
            logger.error("Please verify the structure of the input data and column definitions.")
            return
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
            start_col_disabled = 1
            end_col_disabled = start_col_disabled + num_metrics - 1
            worksheet.merge_range(r_idx, start_col_disabled, r_idx, end_col_disabled, "autofuse_disabled", green_format)
            start_col_enabled = end_col_disabled + 1
            end_col_enabled = start_col_enabled + num_metrics - 1
            worksheet.merge_range(r_idx, start_col_enabled, r_idx, end_col_enabled, "autofuse_enabled", yellow_format)
            r_idx += 2
            duration_diff_ratio_col = end_col_enabled + 1
            worksheet.set_column(0, 0, 30)
            worksheet.set_column(start_col_disabled, duration_diff_ratio_col, 17)
            for c_idx, header in enumerate([self.COL_NAME] + data_cols * 2 + [self.COL_DURATION_DIFF_RATIO]):
                if c_idx < start_col_disabled:
                    worksheet.write(r_idx, c_idx, header, str_format)
                elif start_col_disabled <= c_idx <= end_col_disabled:
                    worksheet.write(r_idx, c_idx, header, green_format)
                elif start_col_enabled <= c_idx <= end_col_enabled:
                    worksheet.write(r_idx, c_idx, header, yellow_format)
                elif c_idx == duration_diff_ratio_col:
                    worksheet.write(r_idx, c_idx, header, str_format)
            r_idx += 1
            # write data
            for _, row in self._result_data.iterrows():
                for c_idx, cell_data in enumerate(row):
                    cell_format = float_format
                    if c_idx == duration_diff_ratio_col and cell_data:
                        cell_format = red_ratio_format if cell_data > 1 else default_ratio_format
                        cell_data = "INF" if cell_data == float('inf') else cell_data
                    worksheet.write(r_idx, c_idx, cell_data, cell_format)
                r_idx += 1
        os.chmod(file_path, Constant.FILE_AUTHORITY)
        logger.info(f"Generate comparison result successfully: {file_path}")

    def run(self):
        PathManager.remove_path_safety(self.autofuse_disabled_path)
        PathManager.remove_path_safety(self.autofuse_enabled_path)
        msprof_bin = shutil.which("msprof")
        py_path = os.path.join((os.path.dirname(os.path.abspath(__file__))), "execute_graph.py")
        if msprof_bin is None:
            logger.info("msprof: command not found")
            return
        # Execute msprof to collect performance data when disabling autofuse and enabling autofuse
        os.environ["AUTOFUSE_FLAGS"] = "--enable_autofuse=false"
        cmd = ["python3", py_path, "-f", self.whole_graph, "-d", self.subgraph_dir, "-p", self.dump_path,
               "-o", self.autofuse_disabled_path]
        if subprocess_cmd(cmd):
            logger.info("Collected profiling data with autofuse disabled.")
        else:
            logger.error("Failed to collect profiling data with autofuse disabled.")
            return
        os.environ["AUTOFUSE_FLAGS"] = "--enable_autofuse=true"
        cmd = ["python3", py_path, "-f", self.whole_graph, "-d", self.subgraph_dir, "-p", self.dump_path,
               "-o", self.autofuse_enabled_path]
        if subprocess_cmd(cmd):
            logger.info("Collected profiling data with autofuse enabled.")
        else:
            logger.error("Failed to collect profiling data with autofuse enabled.")
            return
        try:
            self.generate_compare_result()
            self.generate_view()
        except Exception as err:
            logger.error(f"Failed to generate comparison result: {err}", exc_info=True)


if __name__ == "__main__":
    start_time = datetime.now(timezone.utc)
    args = parse_args()
    ComparisonGenerator(args).run()
    end_time = datetime.now(timezone.utc)
    logger.info(f'The comparison task has been completed in a total time of {end_time - start_time}')
