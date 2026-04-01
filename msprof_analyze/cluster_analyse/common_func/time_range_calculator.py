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

from dataclasses import dataclass
import pandas as pd

DEFAULT_INT_VALUE = -1


@dataclass
class TimeRange:
    start_ts: int = DEFAULT_INT_VALUE
    end_ts: int = DEFAULT_INT_VALUE


class CommunicationTimeRange(TimeRange):

    def __init__(self):
        super().__init__()


class RangeCaculator:

    @staticmethod
    def generate_time_range(start, end, class_range=TimeRange):
        time_range = class_range()
        time_range.start_ts, time_range.end_ts = start, end
        return time_range

    @staticmethod
    def merge_continuous_intervals(time_range_list: list):
        result = []
        if not time_range_list:
            return result
        time_range_list.sort(key=lambda x: x.start_ts)
        current_range = time_range_list[0]
        for time_range in time_range_list:
            if time_range.start_ts <= current_range.end_ts:
                current_range.end_ts = max(current_range.end_ts, time_range.end_ts)
            else:
                result.append(current_range)
                current_range = time_range
        result.append(current_range)
        return result

    @staticmethod
    def compute_pipeline_overlap(communication_range, compute_range):
        free_time_range = []
        pure_communication_range = []
        time_range_list = sorted(communication_range + compute_range, key=lambda x: x.start_ts)
        if not time_range_list:
            return pure_communication_range, free_time_range

        min_range = time_range_list.pop(0)
        for time_range in time_range_list:
            if min_range.end_ts - time_range.start_ts < 0:
                free_time_range.append(
                    RangeCaculator.generate_time_range(min_range.end_ts, time_range.start_ts)
                )
                if isinstance(min_range, CommunicationTimeRange):
                    pure_communication_range.append(
                        RangeCaculator.generate_time_range(min_range.start_ts, min_range.end_ts)
                    )
                min_range = time_range
                continue
            if min_range.end_ts - time_range.end_ts < 0:
                if isinstance(min_range, CommunicationTimeRange):
                    pure_communication_range.append(
                        RangeCaculator.generate_time_range(min_range.start_ts, time_range.start_ts)
                    )
                    min_range = RangeCaculator.generate_time_range(min_range.end_ts, time_range.end_ts)
                if isinstance(time_range, CommunicationTimeRange):
                    min_range = RangeCaculator.generate_time_range(
                        min_range.end_ts, time_range.end_ts, class_range=CommunicationTimeRange
                    )
            else:
                if isinstance(min_range, CommunicationTimeRange):
                    pure_communication_range.append(
                        RangeCaculator.generate_time_range(min_range.start_ts, time_range.start_ts)
                    )
                    min_range = RangeCaculator.generate_time_range(
                        time_range.end_ts, min_range.end_ts, class_range=CommunicationTimeRange
                    )
                if isinstance(time_range, CommunicationTimeRange):
                    min_range = RangeCaculator.generate_time_range(time_range.end_ts, min_range.end_ts)
        if isinstance(min_range, CommunicationTimeRange):
            pure_communication_range.append(min_range)
        return pure_communication_range, free_time_range

    @staticmethod
    def generate_free_intervals(start, end, tasks_df, start_col="start", end_col="end"):
        """
        给定时间段内去除tasks后的剩余free时间段
        Args:
            start: 目标时间段的开始时间
            end: 目标时间段的结束时间
            tasks_df: DataFrame，包含任务时间段的DataFrame
            start_col: tasks_df中开始时间列名，默认为'start'
            end_col: tasks_df中结束时间列名，默认为'end'
        Returns:
            剩余free时间段列表: 每个元素是[start, end]的列表
        """
        if tasks_df is None or tasks_df.empty:
            # 如果没有任务，整个时间段都是free
            return [[start, end]]
        
        # 1. 合并重叠的任务时间段
        task_intervals = tasks_df[[start_col, end_col]].sort_values(start_col).values
        merged_intervals = []
        for task_start, task_end in task_intervals:
            if not merged_intervals:
                merged_intervals.append([task_start, task_end])
            else:
                last_end = merged_intervals[-1][1]
                if task_start <= last_end:
                    # 重叠，合并
                    merged_intervals[-1][1] = max(last_end, task_end)
                else:
                    # 不重叠，添加新区间
                    merged_intervals.append([task_start, task_end])
        
        # 2. 从目标时间段中减去这些任务时间段，得到剩余的free时间段
        free_intervals = []
        current_start = start
        
        for task_start, task_end in merged_intervals:
            # 确保任务时间段在目标时间段内
            task_start = max(task_start, start)
            task_end = min(task_end, end)
            
            # 如果任务时间段完全在目标时间段外，跳过
            if task_end <= start or task_start >= end:
                continue
            
            if current_start < task_start:
                # 有剩余free时间段
                free_intervals.append([current_start, task_start])
            current_start = max(current_start, task_end)
        
        # 检查最后一段
        if current_start < end:
            free_intervals.append([current_start, end])
        
        return free_intervals
