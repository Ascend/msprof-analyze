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
from msprof_analyze.prof_common.logger import get_logger
import os

from msprof_analyze.advisor.dataset.timeline_event_dataset import ScheduleAnalysisDataset
from msprof_analyze.advisor.display.prompt.base_prompt import BasePrompt
from msprof_analyze.advisor.result.result import OptimizeResult
from msprof_analyze.advisor.result.item import OptimizeItem, OptimizeRecord
from msprof_analyze.advisor.utils.utils import convert_to_float, convert_to_int
from msprof_analyze.prof_common.additional_args_manager import AdditionalArgsManager
from msprof_analyze.prof_common.file_manager import FileManager

logger = get_logger()


class GcChecker:
    def __init__(self):
        self.stage = None
        self.rank = None
        self.optimization_item = []
        self.gc_issues = False
        self.gc_problem_with_count = ""
        self.desc = ""
        self.suggestions = []
        self.solutions = None
        self.gc_threshold = 0
        self.gc_topk_num = 0
        self.abnormal_gc_count = 0
        self.abnormal_gc_duration = 0
        self.abnormal_gc_list = []
        self.headers = ["timestamp", "duration(us)"]
        self._init_rule()

    def check_gc(self, event_dataset: ScheduleAnalysisDataset, rank=None, stage=None):
        """
        :Param event_dataset: dataset of timeline event
        """
        self.rank = rank
        self.stage = stage

        # 当用户cann和pta版本不支持采集gc信息时，跳过该分析器
        if not event_dataset.gc_events:
            return

        for gc_event in event_dataset.gc_events:
            if convert_to_float(gc_event.dur) >= self.gc_threshold:
                self.gc_issues = True
                self.abnormal_gc_count += 1
                self.abnormal_gc_duration += convert_to_float(gc_event.dur)
                self.abnormal_gc_list.append([gc_event.ts, gc_event.dur])
        self.abnormal_gc_duration = round(self.abnormal_gc_duration / 1000, 4)
        self.abnormal_gc_list.sort(key=lambda x: x[1], reverse=True)
        self.desc = self.gc_problem_with_count.format(
            gc_count=self.abnormal_gc_count, gc_total_time=self.abnormal_gc_duration
        )

    def make_record(self, result: OptimizeResult):
        """
        make record for what and how to optimize
        """
        if not self.gc_issues:
            return

        self.optimization_item.append(OptimizeItem(self.problem, self.desc, self.suggestions))
        for optimization in self.optimization_item:
            result.add(OptimizeRecord(optimization))
        headers = self.headers
        if self.rank is not None:
            headers = ["Rank id"] + headers

        sub_table_name = BasePrompt.get_sub_table_name(self.problem, self.stage)
        result.add_detail(sub_table_name, headers=headers)

        for row in self.abnormal_gc_list:
            if self.rank is not None:
                row = [self.rank] + row
            result.add_detail(sub_table_name, detail=row)

    def make_render(self, html_render, **kwargs):
        if not self.gc_issues:
            return
        priority = kwargs.get("priority")
        rank = kwargs.get("rank")
        show_num = min(self.gc_topk_num, self.abnormal_gc_count)
        html_render.render_template(
            key="schedule",
            template_dir="templates",
            template_name="gc.html",
            title="GC Analysis",
            desc=self.desc,
            solutions=self.solutions,
            headers=self.headers,
            data_list=self.abnormal_gc_list[:show_num],
            num=show_num,
            priority_background_color=priority,
            rank=rank,
        )

    def _init_rule(self):
        language = AdditionalArgsManager().language
        gc_rule_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))),
            "rules",
            language,
            "gc.yaml",
        )
        gc_rule = FileManager.read_yaml_file(gc_rule_path)

        self.problem = gc_rule.get("problem")
        self.gc_threshold = convert_to_float(gc_rule.get("gc_threshold", 0))
        self.gc_topk_num = convert_to_int(gc_rule.get("top_num", 0))
        self.gc_problem_with_count = gc_rule.get("gc_problem_with_count", "")
        self.solutions = gc_rule.get("solutions", [])
        for solution in self.solutions:
            for key, val in solution.items():
                self.suggestions.append(f"{key}, {val.get('desc')}")
