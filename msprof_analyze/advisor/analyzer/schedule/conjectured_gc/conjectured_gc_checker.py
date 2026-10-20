# -------------------------------------------------------------------------
# This file is part of the MindStudio project.
# Copyright (c) 2024 Huawei Technologies Co.,Ltd.
#
# MindStudio is licensed under Mulan PSL v2.
# You can use this software according to the terms and conditions of the Mulan PSL v2.
# You may obtain a copy of Mulan PSL v2 at:
#
#          http://license.coscl.org.cn/MulanPSL2
#
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND,
# EITHER EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT,
# MERCHANTABILITY OR FIT FOR A PARTICULAR PURPOSE.
# See the Mulan PSL v2 for more details.
# -------------------------------------------------------------------------
import os

from msprof_analyze.advisor.dataset.timeline_event_dataset import ScheduleAnalysisDataset
from msprof_analyze.advisor.result.result import OptimizeResult
from msprof_analyze.advisor.result.item import OptimizeItem, OptimizeRecord
from msprof_analyze.advisor.utils.utils import convert_to_float, convert_to_int, safe_division
from msprof_analyze.prof_common.additional_args_manager import AdditionalArgsManager
from msprof_analyze.prof_common.constant import Constant
from msprof_analyze.prof_common.file_manager import FileManager


class AbnormalGcStatistic:
    def __init__(self):
        self._count = 0
        self._duration = 0
        self._events = []

    @property
    def count(self):
        return self._count

    @count.setter
    def count(self, value):
        self._count = value

    @property
    def duration(self):
        return self._duration

    @duration.setter
    def duration(self, value):
        self._duration = value

    @property
    def events(self):
        return self._events

    def export(self):
        res = []
        for free_event in self.events:
            res.append(
                [
                    round(convert_to_float(free_event.get("ts", 0)), 2),
                    round(convert_to_float(free_event.get("free time", 0)), 4),
                ]
            )
        return res


class ConjecturedGcChecker:
    ACL_EVENT_DUR = "acl_event_dur"
    ACL_EVENT_COUNT = "acl_event_count"
    HEADERS = ["timestamp", "duration(us)"]

    def __init__(self):
        self.stage = None
        self.rank = None
        self.optimization_item = []
        self.gc_problem_with_free = ""
        self.desc = ""
        self.suggestions = []
        self.solutions = None
        self.gc_threshold = 0
        self.gc_topk_num = 0
        self.gc_statistic = AbnormalGcStatistic()
        self._init_rule()

    def check_gc(self, event_dataset: ScheduleAnalysisDataset, rank=None, stage=None):
        """
        Param event_dataset: dataset of timeline event
              rank: rank id
              stage: a stage of a model that is assigned to specific computational device
        """
        if event_dataset.gc_events:
            return

        self.rank = rank
        self.stage = stage

        # 当用户cann和pta版本不支持采集gc信息时，通过timeline中的free和cann层acl事件 综合判断是否可能存在free
        acl_events = getattr(event_dataset, "acl_events", [])
        large_free_events = getattr(event_dataset, "large_free_events", [])
        # 如果acl_events为空，则没有采集cann信息，不基于free+acl events进行gc分析
        if acl_events and large_free_events:
            self.get_free_events_include_gc(large_free_events, acl_events)
            if not self.gc_statistic.count:
                return
            self.desc = self.gc_problem_with_free.format(free_duration_time=self.gc_statistic.duration)

    def make_record(self, result: OptimizeResult):
        """
        make record for what and how to optimize
        """
        if not self.gc_statistic.count:
            return

        self.optimization_item.append(OptimizeItem("Conjectured Gc", self.desc, self.suggestions))
        result.add(OptimizeRecord(self.optimization_item[-1]))
        headers = self.HEADERS
        if self.rank is not None:
            headers = ["Rank id"] + headers
        sub_table_name = "ConjecturedGcAnalysis" if not self.stage else f"Stage-{self.stage}: ConjecturedGcAnalysis"
        result.add_detail(sub_table_name, headers=headers)

        for row in self.gc_statistic.export():
            if self.rank is not None:
                row = [self.rank] + row
            result.add_detail(sub_table_name, detail=row)

    def make_render(self, html_render, **kwargs):
        if not self.gc_statistic.count:
            return
        priority = kwargs.get("priority")
        rank = kwargs.get("rank")
        show_num = min(self.gc_topk_num, self.gc_statistic.count)
        html_render.render_template(
            key="schedule",
            template_dir="templates",
            template_name="gc.html",
            title="Conjectured GC Analysis",
            desc=self.desc,
            solutions=self.solutions,
            headers=self.HEADERS,
            data_list=self.gc_statistic.export()[:show_num],
            num=show_num,
            priority_background_color=priority,
            rank=rank,
        )

    def get_free_events_include_gc(self, large_free_events, acl_events):
        free_event_index, acl_event_index = 0, 0
        free_include_acl_events = {}

        while free_event_index < len(large_free_events):
            free_event = large_free_events[free_event_index]
            free_event_name = f"{Constant.FREE}-{free_event_index}"
            free_event_start_time = convert_to_float(free_event.ts)
            free_event_end_time = free_event_start_time + convert_to_float(free_event.dur)
            if free_event_name not in free_include_acl_events:
                free_include_acl_events[free_event_name] = {"ts": free_event.ts}

            while acl_event_index < len(acl_events):
                acl_event = acl_events[acl_event_index]
                acl_event_start_time = convert_to_float(acl_event.ts)
                acl_event_end_time = acl_event_start_time + convert_to_float(acl_event.dur)

                if acl_event_end_time < free_event_start_time:
                    acl_event_index += 1
                    continue
                if acl_event_start_time > free_event_end_time:
                    break

                if self.ACL_EVENT_COUNT not in free_include_acl_events[free_event_name]:
                    free_include_acl_events[free_event_name][self.ACL_EVENT_COUNT] = 0
                free_include_acl_events[free_event_name][self.ACL_EVENT_COUNT] += 1

                if self.ACL_EVENT_DUR not in free_include_acl_events[free_event_name]:
                    free_include_acl_events[free_event_name][self.ACL_EVENT_DUR] = 0.0
                free_include_acl_events[free_event_name][self.ACL_EVENT_DUR] += convert_to_float(acl_event.dur)

                acl_event_index += 1

            free_event_index += 1

        # 按free持续时间降序排列，优先判断持续时间最长的free
        event_indexs = range(len(large_free_events))
        for index, free_event in sorted(zip(event_indexs, large_free_events), key=lambda x: x[1].dur, reverse=True):
            free_event_name = f"{Constant.FREE}-{index}"
            free_duration = convert_to_float(free_event.dur)
            free_include_acl_events[free_event_name]["free time"] = free_duration
            acl_event_dur = free_include_acl_events.get(free_event_name, {}).get(self.ACL_EVENT_DUR, 0.0)
            acl_event_count = free_include_acl_events.get(free_event_name, {}).get(self.ACL_EVENT_COUNT, 0)
            if (
                safe_division(acl_event_dur, free_duration) < self.max_acl_event_time_ratio
                and safe_division(acl_event_count, free_duration) < self.max_acl_event_num_ratio
            ):
                self.gc_statistic.count += 1
                self.gc_statistic.duration += free_duration
                self.gc_statistic.events.append(free_include_acl_events.get(free_event_name, {}))

    def _init_rule(self):
        language = AdditionalArgsManager().language
        gc_rule_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))),
            "rules",
            language,
            "conjectured_gc.yaml",
        )

        gc_rule = FileManager.read_yaml_file(gc_rule_path)

        self.gc_topk_num = convert_to_int(gc_rule.get("top_num", 0))
        self.gc_problem_with_free = gc_rule.get("gc_problem_with_free", "")
        self.max_acl_event_num_ratio = convert_to_float(gc_rule.get("max_acl_event_num_ratio"))
        self.max_acl_event_time_ratio = convert_to_float(gc_rule.get("max_acl_event_time_ratio"))

        self.solutions = gc_rule.get("solutions", [])
        for solution in self.solutions:
            for key, val in solution.items():
                self.suggestions.append(f"{key}, {val.get('desc')}")
