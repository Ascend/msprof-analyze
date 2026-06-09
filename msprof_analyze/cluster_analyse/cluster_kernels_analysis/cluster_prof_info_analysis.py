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

import argparse
import re
import os
import stat
import warnings
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from plotly.offline import plot

from msprof_analyze.prof_common.logger import get_logger
from msprof_analyze.prof_common.path_manager import PathManager
from msprof_analyze.prof_common.additional_args_manager import AdditionalArgsManager

logger = get_logger()

MAX_READ_FILE_BYTES = 64 * 1024 * 1024


class FormDataProcessor:
    def __init__(self, path, form_name):
        self.form_name = form_name
        self.files = self.get_files_with_prefix_recursive(path, form_name)

    @staticmethod
    def get_device_id(dir_path):
        device_id = re.search(r'device_(\d+)', dir_path).group(1)
        return device_id

    @staticmethod
    def get_node_id(dir_path):
        node_id = re.search(r'node(\d+)', dir_path).group(1)
        return int(node_id)

    @staticmethod
    def get_files_with_prefix_recursive(csv_path, match_str):
        matched_ir_files = list(Path(csv_path).rglob(match_str))
        if not matched_ir_files:
            msg = f"Didn't find any file in folder {csv_path} that matches {match_str}"
            raise RuntimeError(msg)
        return [str(item) for item in matched_ir_files]

    def read_summary_data(self, columns_to_keep):
        # 存储所有合并后的数据
        all_data = pd.DataFrame()
        for f in self.files:
            if "mindstudio_profiler_output" in f:
                continue
            # 判断csv文件大小
            PathManager.check_file_size(f)
            PathManager.check_input_file_path(f)
            # 读取CSV文件
            df = pd.read_csv(f)
            # 保留需要的列
            try:
                df = df[columns_to_keep]
            except KeyError:
                logger.info(
                    "%s文件没有所需的列，请确认profiling数据的正确性:\n,以下列可能不存在%s\n", f, columns_to_keep
                )
                continue
            # 从文件名提取设备ID
            try:
                df['device_id'] = self.get_device_id(f)
            except Exception:
                logger.info(
                    "文件 \"%s\" 的路径或者是文件夹名没有按照要求，请确保存在[device_]这一级文件夹,"
                    "具体操作指导见readme\n",
                    f,
                )
                continue
            # 添加新列 "device_id"
            try:
                df['node_id'] = self.get_node_id(f)
            except Exception:
                logger.info(
                    "文件 \"%s\" 的路径或者是文件夹名没有按照要求，请确保存在[node*]这一级文件夹,"
                    "具体操作指导见readme\n",
                    f,
                )
                continue
            # 将数据添加到最终的数据框中
            all_data = pd.concat([all_data, df])
        return all_data

    def get_chip_type(self):
        file = self.files[0]
        PathManager.check_file_size(file)
        PathManager.check_input_file_path(file)
        df = pd.read_csv(file)
        if 'aiv_time(us)' in df.columns:
            return "ASCEND_NEW"
        return "ASCEND_OTHER"

    def get_rank_num(self):
        return len(self.files)


# 表驱动，获取不同芯片类型不同交付件的所需的列
class ViewInfoManager:
    def __init__(self, chip_type):
        self.chip_type = chip_type
        self.op_summary_columns_dict = {}
        self.set_op_summary_columns_params()

    def set_op_summary_columns_params(self):
        # 有些数据除了用表格的列进行分组之外，还添加了其他属性对数据进行分类，这部分数据放在extend_attr_to_group里面
        self.op_summary_columns_dict = {
            'ASCEND_NEW': {
                'TimeToCsvAnalyzer': {
                    'columns_to_group': ["Op Name", "Input Shapes", "Input Data Types", "Output Shapes"],
                    'extend_attr_to_group': ["device_id", "node_id"],
                    'columns_to_view': ["Task Duration(us)"],
                    'calculate_fun': ['mean', 'var', 'max', 'min'],
                },
                'StatisticalInfoToHtmlAnalyzer': {
                    'columns_to_group': ["Op Name", "Input Shapes", "Input Data Types", "Output Shapes"],
                    "columns_to_view": [
                        "Task Duration(us)",
                        "aiv_time(us)",
                        "aiv_vec_ratio",
                        "aiv_scalar_ratio",
                        "aiv_mte2_ratio",
                        "aiv_mte3_ratio",
                        "aicore_time(us)",
                        "aic_mac_ratio",
                        "aic_scalar_ratio",
                        "aic_mte1_ratio",
                        "aic_mte2_ratio",
                        "aic_fixpipe_ratio",
                    ],
                    'calculate_fun': ['mean', 'var', 'max', 'min'],
                },
            },
            'ASCEND_OTHER': {
                'TimeToCsvAnalyzer': {
                    'columns_to_group': ["Op Name", "Input Shapes", "Input Data Types", "Output Shapes"],
                    'extend_attr_to_group': ["device_id", "node_id"],
                    "columns_to_view": ["Task Duration(us)"],
                    'calculate_fun': ['mean', 'var', 'max', 'min'],
                },
                'StatisticalInfoToHtmlAnalyzer': {
                    'columns_to_group': ["Op Name", "Input Shapes", "Input Data Types", "Output Shapes"],
                    "columns_to_view": [
                        "aicore_time(us)",
                        "Task Duration(us)",
                        "mac_ratio",
                        "vec_ratio",
                        "scalar_ratio",
                        "mte1_ratio",
                        "mte2_ratio",
                        "mte3_ratio",
                    ],
                    'calculate_fun': ['mean', 'var', 'max', 'min'],
                },
            },
        }

    def get_columns_info(self, analyzer_type):
        return self.op_summary_columns_dict.get(self.chip_type, {}).get(analyzer_type)


class OpSummaryAnalyzerBase:
    def __init__(self, chip_type, analyzer_type, dir_path):
        self.chip_type = chip_type
        view_info = ViewInfoManager(chip_type).get_columns_info(analyzer_type)
        self.columns_to_view = view_info['columns_to_view']
        self.calculate_fun = view_info['calculate_fun']
        self.columns_to_group = view_info['columns_to_group']
        self.attrs_to_group = self.columns_to_group.copy()
        if 'extend_attr_to_group' in view_info:
            extend_attr_to_group = view_info['extend_attr_to_group']
            self.attrs_to_group.extend(extend_attr_to_group)
        # 创建结果文件
        self.result_dir = os.path.join(dir_path, "result")
        PathManager.check_path_length(self.result_dir)
        PathManager.remove_path_safety(self.result_dir)
        PathManager.check_output_directory_path(dir_path)
        PathManager.make_dir_safety(self.result_dir)
        PathManager.check_output_directory_path(self.result_dir)

    @staticmethod
    def on_rm_error(func, path, exc_info):
        # path contains the path of the file that couldn't be removed
        # let's just assume that it's read-only and unlink it.
        os.chmod(path, stat.S_IWRITE)
        os.unlink(path)

    def get_columns_to_group(self):
        return self.columns_to_group

    def get_columns_to_view(self):
        return self.columns_to_view

    def calculate_view_data(self, summary_data):
        # 存储所有合并后的数据
        calculate_dict = {self.columns_to_view[i]: self.calculate_fun for i in range(len(self.columns_to_view))}
        view_data = summary_data.groupby(self.attrs_to_group).agg(calculate_dict).reset_index()
        return view_data


class TimeToCsvAnalyzer(OpSummaryAnalyzerBase):
    def __init__(self, chip_type, dir_path):
        super().__init__(chip_type, "TimeToCsvAnalyzer", dir_path)

    def generate_deliverable(self, summary_data, rank_num):
        view_data = self.calculate_view_data(summary_data)
        # 规范化列名
        view_data.columns = [''.join(col) if col[1] == "" else '_'.join(col) for col in view_data.columns]
        try:
            for column in self.columns_to_view:
                view_data[column + '_range'] = view_data[column + '_max'] - view_data[column + '_min']
        except Exception as e:
            raise RuntimeError("Invalid view data!") from e
        save_path = os.path.join(self.result_dir, "cluster_duration_time_analysis.csv")
        PathManager.check_path_length(save_path)
        view_data.to_csv(save_path, index=False)
        # 该文件权限设置为只读权限，不允许修改
        os.chmod(save_path, stat.S_IROTH)
        return view_data


class StatisticalInfoToHtmlAnalyzer(OpSummaryAnalyzerBase):
    def __init__(self, chip_type, top_n, dir_path):
        super().__init__(chip_type, "StatisticalInfoToHtmlAnalyzer", dir_path)
        self.top_n = top_n
        # top_n 如果不符合要求，报警告

    def generate_deliverable(self, summary_data, rank_num):
        view_data = self.calculate_view_data(summary_data)
        # 规范化列名 op_name/ --> op_name   time/var 这种不变
        view_data.columns = [''.join(col) if col[1] == "" else col for col in view_data.columns]

        # 对使用到的变量进行初始设置
        self.top_n = min(max(self.top_n, 1), len(view_data))
        top_n_data = view_data.sort_values(("Task Duration(us)", 'var'), ascending=False).head(self.top_n)

        for column in self.columns_to_view:
            # 分别给每一种特性画图
            self.draw_plotly(column, summary_data, top_n_data, rank_num)

    def draw_plotly(self, column, summary_data, top_n_data, rank_num):
        col_num = self.get_cal_num(rank_num)
        row_num = self.top_n // col_num if self.top_n % col_num == 0 else (self.top_n + 1) // col_num
        fig = make_subplots(rows=row_num, cols=col_num, vertical_spacing=0.03)
        for i, (_, operation) in enumerate(top_n_data.iterrows()):
            op_data = summary_data[
                (summary_data["Op Name"] == operation["Op Name"])
                & (summary_data["Input Shapes"] == operation["Input Shapes"])
                & (summary_data["Input Data Types"] == operation["Input Data Types"])
            ]
            op_data = op_data.sort_values(by=["node_id", "device_id"])
            node_ids = op_data['node_id'].unique()
            device_ids = op_data['device_id'].unique()

            for node_id in node_ids:
                for device_id in device_ids:
                    draw_data = op_data[(op_data['node_id'] == node_id) & (op_data['device_id'] == device_id)]
                    fig.add_trace(
                        go.Box(
                            y=draw_data[column], name=f'{node_id}_{device_id}', marker_color='green', showlegend=False
                        ),
                        (i // col_num) + 1,
                        (i % col_num) + 1,
                    )

            fig.update_xaxes(
                title_text=f'{operation["Op Name"]}-{operation["Input Shapes"]}',
                row=(i // col_num) + 1,
                col=(i % col_num) + 1,
            )
        fig.update_layout(
            margin=dict(l=20, r=20, t=20, b=20),
            height=int(500 * row_num),
            width=int(rank_num * 100 * col_num),
            title_text="Op Performance Comparison",
        )
        save_plot_path = os.path.join(self.result_dir, column + "_Info.html")
        PathManager.check_path_length(save_plot_path)
        plot(fig, filename=save_plot_path)
        # 该文件权限设置为只读权限，不允许修改
        os.chmod(save_plot_path, stat.S_IROTH)

    def get_cal_num(self, rank_num):
        # 计算每行应该画多少个子图
        if rank_num <= 16:
            return 2
        else:
            return 1


class DeliverableGenerator:
    def __init__(self, params):
        self.dirs = params.get('dir')
        self.form_process = FormDataProcessor(self.dirs, 'op_summary*.csv')
        self.analyzers = []
        self.columns_to_keep = []
        self.set_analyzers(params)
        self.set_columns_to_keep()

    def run(self):
        summary_data = self.form_process.read_summary_data(self.columns_to_keep)
        # 判断summarydata 数据是否为空，如果是空， 说明所有csv读取数据都失败了
        if summary_data.empty:
            logger.info("没有符合要求的csv表格数据，请排查您的PROFILING数据")
            return
        rank_num = self.form_process.get_rank_num()
        for analyzer in self.analyzers:
            analyzer.generate_deliverable(summary_data, rank_num)

    def set_analyzers(self, params):
        chip_type = self.form_process.get_chip_type()
        # 判断该路径是不是软链接，并修改为绝对路径
        if os.path.islink(params.get('dir')):
            logger.warning("The file: \"%s\" is link. Please check the path.", params.get('dir'))
        prof_path = os.path.abspath(params.get('dir'))
        PathManager.input_path_common_check(prof_path)
        if params.get('type') == "all":
            self.analyzers = [
                TimeToCsvAnalyzer(chip_type, prof_path),
                StatisticalInfoToHtmlAnalyzer(chip_type, params.get("top_n"), prof_path),
            ]
        elif params.get('type') == "html":
            self.analyzers = [StatisticalInfoToHtmlAnalyzer(chip_type, params.get("top_n"), prof_path)]
        elif params.get('type') == "csv":
            self.analyzers = [TimeToCsvAnalyzer(chip_type, prof_path)]
        else:
            warnings.warn("参数错误，请输入 all html csv 这三种类型")  # 发出一个警告信息

    def set_columns_to_keep(self):
        columns_to_keep = []
        for analyzer in self.analyzers:
            columns_to_keep.extend(analyzer.get_columns_to_group())
            columns_to_keep.extend(analyzer.get_columns_to_view())
        self.columns_to_keep = list(set(columns_to_keep))


def main():
    # 解析命令行参数
    parser = argparse.ArgumentParser()
    parser.add_argument("--dir", "-d", default=None, help="root dir of PROF_* data")
    parser.add_argument("--top_n", "-n", default=10, help="how many operators to show", type=int)
    parser.add_argument("--type", "-t", default='html', help="compare ratio or aicore-time", type=str)
    parser.add_argument(
        "--force",
        action='store_true',
        help="Indicates whether to skip verification of the owner, size, and permissions.",
    )
    args = parser.parse_args()
    params = {"dir": args.dir, "top_n": args.top_n, "type": args.type, "force": args.force}
    AdditionalArgsManager().init(params)
    deviverable_gen = DeliverableGenerator(params)
    deviverable_gen.run()


if __name__ == "__main__":
    main()
