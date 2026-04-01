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


import unittest
from msprof_analyze.prof_common.interval_manager import IntervalManager


class TestIntervalManager(unittest.TestCase):
    def setUp(self):
        self.interval_manager = IntervalManager()

    def test_merge_intervals_empty_list(self):
        """Test merging an empty list of intervals."""
        intervals = []
        result = self.interval_manager.merge_intervals(intervals)
        self.assertEqual(result, [])

    def test_merge_intervals_single_interval(self):
        """Test merging a list with a single interval."""
        intervals = [(1, 5)]
        result = self.interval_manager.merge_intervals(intervals)
        self.assertEqual(result, [(1, 5)])

    def test_merge_intervals_no_overlap(self):
        """Test merging intervals that do not overlap."""
        intervals = [(1, 3), (4, 5), (6, 9)]
        result = self.interval_manager.merge_intervals(intervals)
        self.assertEqual(result, [(1, 3), (4, 5), (6, 9)])

    def test_merge_intervals_with_overlap(self):
        """Test merging intervals that overlap."""
        intervals = [(1, 3), (2, 4), (5, 7), (6, 8)]
        result = self.interval_manager.merge_intervals(intervals)
        self.assertEqual(result, [(1, 4), (5, 8)])

    def test_merge_intervals_invalid_input(self):
        """Test merging intervals with invalid input."""
        intervals = [(1, 3), (2, 4, 5)]
        with self.assertRaises(ValueError):
            self.interval_manager.merge_intervals(intervals)

    def test_merge_intervals_non_numeric_input(self):
        """Test merging intervals with non-numeric input."""
        intervals = [(1, "a"), (2, 4)]
        with self.assertRaises(TypeError):
            self.interval_manager.merge_intervals(intervals)

    def test_compute_uncovered_durations_empty_lists(self):
        """Test computing uncovered durations with empty lists."""
        communication_lst = []
        summary_lst = []
        result = self.interval_manager.compute_uncovered_durations(communication_lst, summary_lst)
        self.assertEqual(result, [])

    def test_compute_uncovered_durations_no_overlap(self):
        """Test computing uncovered durations with no overlap."""
        communication_lst = [(1, 5)]
        summary_lst = [(6, 10)]
        result = self.interval_manager.compute_uncovered_durations(communication_lst, summary_lst)
        self.assertEqual(result, [4]) # No overlap, full duration is uncovered

    def test_compute_uncovered_durations_full_overlap(self):
        """Test computing uncovered durations with full overlap."""
        communication_lst = [(1, 5)]
        summary_lst = [(1, 5)]
        result = self.interval_manager.compute_uncovered_durations(communication_lst, summary_lst)
        self.assertEqual(result, [0]) # Full overlap, no uncovered duration

    def test_compute_uncovered_durations_partial_overlap(self):
        """Test computing uncovered durations with partial overlap."""
        communication_lst = [(1, 5)]
        summary_lst = [(2, 4)]
        result = self.interval_manager.compute_uncovered_durations(communication_lst, summary_lst)
        self.assertEqual(result, [2]) # Partial overlap, uncovered duration is 2

    def test_compute_uncovered_durations_multiple_intervals(self):
        """Test computing uncovered durations with multiple intervals."""
        communication_lst = [(1, 5), (6, 10)]
        summary_lst = [(2, 4), (7, 9)]
        result = self.interval_manager.compute_uncovered_durations(communication_lst, summary_lst)
        self.assertEqual(result, [2, 2])

    def test_compute_uncovered_durations_invalid_input(self):
        """Test computing uncovered durations with invalid input."""
        communication_lst = [(1, 3), (2, 4, 5)]
        summary_lst = [(1, 5)]
        with self.assertRaises(ValueError):
            self.interval_manager.compute_uncovered_durations(communication_lst, summary_lst)


if __name__ == "__main__":
    unittest.main()
