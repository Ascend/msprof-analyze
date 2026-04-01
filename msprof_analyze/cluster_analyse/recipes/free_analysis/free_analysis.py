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

import os
import pandas as pd

from msprof_analyze.cluster_analyse.common_func.utils import ensure_numeric_columns
from msprof_analyze.cluster_analyse.common_func.time_range_calculator import RangeCaculator
from msprof_analyze.cluster_analyse.recipes.base_recipe_analysis import BaseRecipeAnalysis
from msprof_analyze.prof_common.constant import Constant
from msprof_analyze.prof_common.logger import get_logger
from msprof_analyze.prof_common.utils import convert_ns_to_us, convert_ns_to_us_str
from msprof_analyze.prof_exports import free_analysis_export
from msprof_analyze.prof_exports.free_analysis_export import DeviceTaskLinkCannPytorchExport

logger = get_logger()


class FreeReason:
    def __init__(self, start_ns, end_ns, rank_id):
        self.start_ns = start_ns
        self.end_ns = end_ns
        self.rank_id = rank_id
        self.reason = None
        self.pytorch_idle_time = None
        self.cann_idle_time = None


class FreeAnalysis(BaseRecipeAnalysis):

    DEFAULT_TOP_NUM = 10
    TOP_NUM = "top_num"
    DIFF_WAIT_THRESHOLD_NS = 50 * 1000  # 50 us

    def __init__(self, params):
        super().__init__(params)
        logger.info("Free Analysis init.")
        top_num = self._extra_args.get(self.TOP_NUM, self.DEFAULT_TOP_NUM)
        self.top_num = int(top_num) if isinstance(top_num, str) and top_num.isdigit() else self.DEFAULT_TOP_NUM

    @property
    def base_dir(self):
        return os.path.basename(os.path.dirname(__file__))

    @classmethod
    def add_parser_argument(cls, parser):
        parser.add_argument("--top_num", type=str, help="Duration cost top count", default=cls.DEFAULT_TOP_NUM)

    def run(self, context):
        mapper_res = self.mapper_func(context)
        free_time_df = self.reducer_func(mapper_res)
        if free_time_df is None or free_time_df.empty:
            logger.info("No free time data found.")
            return

        if self._export_type == Constant.DB:
            self.save_db(free_time_df)
        elif self._export_type == Constant.TEXT:
            self.save_csv(free_time_df)
        else:
            logger.error("Free analysis is not supported for notebook export type.")

    def reducer_func(self, mapper_res):
        """汇总所有rank的free分析结果"""
        if not mapper_res:
            return None
        
        all_results = []
        for rank_id, free_reasons in mapper_res:
            if not free_reasons:
                continue
            for free_reason in free_reasons:
                result_dict = {
                    'rankId': free_reason.rank_id,
                    'startTime(us)': convert_ns_to_us_str(free_reason.start_ns),
                    'endTime(us)': convert_ns_to_us_str(free_reason.end_ns),
                    'duration(us)': convert_ns_to_us(free_reason.end_ns - free_reason.start_ns),
                    'pytorchIdleTime(us)': convert_ns_to_us(free_reason.pytorch_idle_time),
                    'cannIdleTime(us)': convert_ns_to_us(free_reason.cann_idle_time),
                    'reason': free_reason.reason
                }
                all_results.append(result_dict)
        
        if not all_results:
            return None
        
        result_df = pd.DataFrame(all_results)
        return result_df

    def obtain_top_free_time(self, profiler_db_path, analysis_class, rank_id):
        # obtain busy time
        busy_df = free_analysis_export.BusyTimeOverlapExport(profiler_db_path, analysis_class).read_export_db()
        if busy_df is None or busy_df.empty:
            logger.info(f"No busy overlap data found for rank {rank_id}. Find BusyTimeOnlyComputing.")
            return None

        # compute the free time
        free_df = pd.DataFrame()
        free_df["start_ns"] = busy_df['end_ns'].iloc[0:len(busy_df['start_ns']) - 1].values
        free_df['end_ns'] = busy_df['start_ns'].iloc[1:len(busy_df['start_ns'])].values
        free_df['duration'] = free_df['end_ns'] - free_df['start_ns']
        if free_df is None or free_df.empty:
            return None

        # sort the free time in descending order
        free_df = free_df.sort_values(by='duration', ascending=False)
        return free_df.head(self.top_num)

    def analyze_free_reason(self, rank_id, free_start_ns, free_end_ns, link_df):
        free_reason = FreeReason(free_start_ns, free_end_ns, rank_id)

        # 基于预先查询好的 link_df，过滤出 free 区间内 device 上是否有任务在执行
        task_df = link_df[
            (link_df["task_ts"] > free_start_ns) & (link_df["task_end"] < free_end_ns)
        ]
    
        if not task_df.empty:
            # 有任务在执行，分析剩余free时间段
            self._analyze_device_task_remaining_free(task_df, free_reason)
            return free_reason

        # 找到 free 区间前后的最近任务
        before_df = link_df[link_df["task_end"] <= free_start_ns]
        after_df = link_df[link_df["task_ts"] >= free_end_ns]
        prev_task = before_df.sort_values("task_end").iloc[-1] if not before_df.empty else None
        next_task = after_df.sort_values("task_ts").iloc[0]  if not after_df.empty else None
        if prev_task is None or next_task is None:
            free_reason.reason = f"Skip free analysis due to no prev or next task."
            return free_reason
        if not prev_task.pytorch_ts or not next_task.pytorch_ts:
            free_reason.reason = f"Skip free analysis due to no pytorch dispatch time."
            return free_reason

        free_reason.pytorch_idle_time = next_task.pytorch_end - prev_task.pytorch_end
        free_reason.cann_idle_time = next_task.cann_end - prev_task.cann_end

        prev_wait = prev_task.cann_ts - prev_task.pytorch_end
        next_wait = next_task.cann_ts - next_task.pytorch_end
        # Pytorch层无任务下发
        if next_wait - prev_wait < self.DIFF_WAIT_THRESHOLD_NS:
            free_reason.reason = (f"Idle Pytorch layer: no task dispatched in "
                                  f"{convert_ns_to_us(free_reason.pytorch_idle_time)} us")
            return free_reason

        # CANN层下发瓶颈
        prev_launch_dur = prev_task.cann_end - prev_task.cann_ts
        next_launch_dur = next_task.cann_end - next_task.cann_ts
        idle_gap = next_task.cann_ts - prev_task.cann_end

        max_dur = max(prev_launch_dur, next_launch_dur, idle_gap)
        if max_dur == idle_gap:
            free_reason.reason = (f"Abnormal CANN layer: long time between two node@launch "
                                  f"{convert_ns_to_us(idle_gap)} us")
        else:
            free_reason.reason = (f"Abnormal CANN layer: long node@launch "
                                  f"{convert_ns_to_us(max(prev_launch_dur, next_launch_dur))} us")

        return free_reason

    def save_db(self, free_time_df):
        if free_time_df is None or free_time_df.empty:
            logger.info("No free time data to save.")
            return

        self.dump_data(
            free_time_df,
            Constant.DB_CLUSTER_COMMUNICATION_ANALYZER,
            "FreeAnalysis",
            index=False
        )
    
    def save_csv(self, free_time_df):
        if free_time_df is None or free_time_df.empty:
            logger.info("No free time data to save.")
            return
        
        column_mapping = {
            'rankId': 'Rank ID',
            'startTime(us)': 'Start Time(us)',
            'endTime(us)': 'End Time(us)',
            'duration(us)': 'Duration(us)',
            'pytorchIdleTime(us)': 'Pytorch Idle Time(us)',
            'cannIdleTime(us)': 'Cann Idle Time(us)',
            'reason': 'Reason'
        }
        csv_df = free_time_df.rename(columns=column_mapping)
        self.dump_data(csv_df, "free_analysis.csv", index=False)

    def _mapper_func(self, data_map, analysis_class):
        rank_id = data_map.get(Constant.RANK_ID)
        profiler_db_path = data_map.get(Constant.PROFILER_DB_PATH)

        if not profiler_db_path:
            logger.warning(f"No profiler db path for rank {rank_id}")
            return rank_id, []

        # 1. obtain_free_time：获取每个db文件中最大的Free时间段
        top_free_df = self.obtain_top_free_time(profiler_db_path, analysis_class, rank_id)

        if top_free_df is None or top_free_df.empty:
            logger.info(f"No free time found for rank {rank_id}")
            return rank_id, []

        # 2. 预先查询 device-task / CANN / PyTorch 关联信息，供后续按时间过滤使用
        link_df = DeviceTaskLinkCannPytorchExport(profiler_db_path, analysis_class).read_export_db()
        link_df = ensure_numeric_columns(link_df, ["task_ts", "task_end", "pytorch_end", "cann_ts", "cann_end"])
        if link_df is None or link_df.empty:
            logger.info(f"Failed to get task dispatch time for rank {rank_id}")
            return rank_id, []

        # 3. locate_anomaly_reasons：对于每个free，分析原因
        free_reasons = []
        for row in top_free_df.itertuples():
            free_reason = self.analyze_free_reason(
                rank_id, row.start_ns, row.end_ns, link_df
            )
            free_reasons.append(free_reason)

        return rank_id, free_reasons

    def _analyze_device_task_remaining_free(self, task_df, free_reason):
        # 记录任务类型与数量
        counts = task_df['task_type'].value_counts()
        types_desc = ', '.join([f"{v} {k} tasks" for k, v in counts.items()])

        # 使用通用函数计算抛去这些task后剩余的free时间段
        remaining_free_intervals = RangeCaculator.generate_free_intervals(
            free_reason.start_ns, free_reason.end_ns, task_df, start_col='task_ts', end_col='task_end')

        # 剩余free时间段的最大duration
        if remaining_free_intervals:
            max_remaining_free = max(interval_end - interval_start
                                     for interval_start, interval_end in remaining_free_intervals)
            free_reason.reason = (f"Device task running: {types_desc}, "
                                  f"max remaining free {convert_ns_to_us(max_remaining_free)} us")
        else:
            free_reason.reason = f"Device task running: {types_desc}."



