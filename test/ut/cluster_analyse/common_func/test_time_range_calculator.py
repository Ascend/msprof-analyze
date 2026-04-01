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

import unittest
import pandas as pd

from msprof_analyze.cluster_analyse.common_func.time_range_calculator import RangeCaculator, TimeRange, \
    CommunicationTimeRange


class TestTimeRangeCalculator(unittest.TestCase):
    def test_time_range_initialization(self):
        time_range = TimeRange()
        self.assertEqual(time_range.start_ts, -1)
        self.assertEqual(time_range.end_ts, -1)

        custom_range = TimeRange(10, 20)
        self.assertEqual(custom_range.start_ts, 10)
        self.assertEqual(custom_range.end_ts, 20)

    def test_communication_time_range_initialization(self):
        comm_range = CommunicationTimeRange()
        self.assertEqual(comm_range.start_ts, -1)
        self.assertEqual(comm_range.end_ts, -1)

    def test_generate_time_range(self):
        time_range = RangeCaculator.generate_time_range(10, 20)
        self.assertEqual(time_range.start_ts, 10)
        self.assertEqual(time_range.end_ts, 20)
        self.assertIsInstance(time_range, TimeRange)

        comm_range = RangeCaculator.generate_time_range(10, 20, CommunicationTimeRange)
        self.assertEqual(comm_range.start_ts, 10)
        self.assertEqual(comm_range.end_ts, 20)
        self.assertIsInstance(comm_range, CommunicationTimeRange)

    def test_merge_continuous_intervals(self):
        # 测试空列表
        self.assertEqual(RangeCaculator.merge_continuous_intervals([]), [])

        # 测试无重叠区间
        range1 = TimeRange(1, 2)
        range2 = TimeRange(3, 4)
        self.assertEqual(RangeCaculator.merge_continuous_intervals([range1, range2]), [range1, range2])

        # 测试有重叠区间
        range3 = TimeRange(1, 3)
        range4 = TimeRange(2, 4)
        merged = RangeCaculator.generate_time_range(1, 4)
        self.assertEqual(RangeCaculator.merge_continuous_intervals([range3, range4]), [merged])

        # 测试有包含关系的区间
        range5 = TimeRange(1, 5)
        range6 = TimeRange(2, 3)
        self.assertEqual(RangeCaculator.merge_continuous_intervals([range5, range6]), [range5])

    def test_compute_pipeline_overlap(self):
        # 测试空列表
        pure_comm, free_time = RangeCaculator.compute_pipeline_overlap([], [])
        self.assertEqual(pure_comm, [])
        self.assertEqual(free_time, [])

        # 测试无重叠区间
        comm_range1 = CommunicationTimeRange()
        comm_range1.start_ts, comm_range1.end_ts = 1, 2
        compute_range1 = TimeRange()
        compute_range1.start_ts, compute_range1.end_ts = 3, 4
        pure_comm, free_time = RangeCaculator.compute_pipeline_overlap([comm_range1], [compute_range1])
        self.assertEqual(len(pure_comm), 1)
        self.assertEqual(pure_comm[0].start_ts, 1)
        self.assertEqual(pure_comm[0].end_ts, 2)
        self.assertEqual(len(free_time), 1)
        self.assertEqual(free_time[0].start_ts, 2)
        self.assertEqual(free_time[0].end_ts, 3)

        # 测试有重叠区间
        comm_range2 = CommunicationTimeRange()
        comm_range2.start_ts, comm_range2.end_ts = 1, 3
        compute_range2 = TimeRange()
        compute_range2.start_ts, compute_range2.end_ts = 2, 4
        pure_comm, free_time = RangeCaculator.compute_pipeline_overlap([comm_range2], [compute_range2])
        self.assertEqual(len(pure_comm), 1)
        self.assertEqual(pure_comm[0].start_ts, 1)
        self.assertEqual(pure_comm[0].end_ts, 2)
        self.assertEqual(len(free_time), 0)

    def test_generate_free_intervals_when_tasks_overlap_then_merge_and_return_intervals(self):
        tasks_df = pd.DataFrame({
            'task_start': [1100, 1150, 1300],
            'task_end': [1200, 1250, 1400]
        })
        result = RangeCaculator.generate_free_intervals(
            1000, 2000, tasks_df, start_col='task_start', end_col='task_end')
        # 前两个任务重叠，应该合并为 [1100, 1250]
        self.assertEqual(result, [[1000, 1100], [1250, 1300], [1400, 2000]])

    def test_generate_free_intervals_when_tasks_cover_with_gaps_then_return_gap_intervals(self):
        tasks_df = pd.DataFrame({
            'start': [1000, 1200, 1400, 1600],
            'end': [1100, 1300, 1500, 1700]
        })
        result = RangeCaculator.generate_free_intervals(1000, 2000, tasks_df)
        self.assertEqual(result, [[1100, 1200], [1300, 1400], [1500, 1600], [1700, 2000]])

    def test_generate_free_intervals_when_tasks_unsorted_then_sort_and_process(self):
        tasks_df = pd.DataFrame({
            'start': [1500, 1100, 1300],
            'end': [1600, 1200, 1400]
        })
        result = RangeCaculator.generate_free_intervals(1000, 2000, tasks_df)
        # 应该按 start 排序后处理
        self.assertEqual(result, [[1000, 1100], [1200, 1300], [1400, 1500], [1600, 2000]])


if __name__ == '__main__':
    unittest.main()
