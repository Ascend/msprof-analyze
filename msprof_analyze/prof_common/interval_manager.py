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


class IntervalManager:
    def __init__(self):
        pass

    def merge_intervals(self, intervals: list) ->list:
        """
        :param:
            intervals: list of intervals are tuples(start, end)
        :return:
            list: merged intervals
        """
        if not intervals:
            return []
        # Check whether the elements in the list are tuples and have a length of 2.
        for interval in intervals:
            if not isinstance(interval, tuple) or len(interval) != 2:
                raise ValueError("Each element in the list must be a tuple of length 2.")

            # Check if the elements in the tuple are numbers
            if not (isinstance(interval[0], (int, float)) and isinstance(interval[1], (int, float))):
                raise TypeError("The elements in the tuple must be numbers.")
        # Standard + sorting
        normalize = [(min(x, y), max(x, y)) for x, y in intervals]
        normalize.sort(key=lambda x: x[0])

        # Merge process
        merged = [normalize[0]]
        if len(intervals) < 2:
            return merged
        for current in normalize[1:]:
            last = merged[-1]
            if current[0] <= last[1]:
                merged[-1] = (last[0], max(last[1], current[1]))
            else:
                merged.append(current)
        return merged

    def compute_uncovered_durations(self, communication_lst: list, summary_lst: list) -> list:
        """
        :param:
            communication_lst and summary_lst
        :return:
            List of floats/integers for each uncovered duration values
        """
        uncovered_durations = []
        try:
            communication_merge_lst = self.merge_intervals(communication_lst)
            summary_merge_lst = self.merge_intervals(summary_lst)
        except (TypeError, ValueError) as e:
            raise

        for a_start, a_end in communication_merge_lst:
            if a_start >= a_end:
                uncovered_durations.append(0)
                continue
            total_cover = 0
            a_length = a_end - a_start
            for b_start, b_end in summary_merge_lst:
                if b_end <= a_start or b_start >= a_end:
                    continue
                # compute
                inner_start = max(a_start, b_start)
                inner_end = min(a_end, b_end)
                total_cover += inner_end - inner_start
            uncovered_durations.append(a_length - total_cover)

        return uncovered_durations