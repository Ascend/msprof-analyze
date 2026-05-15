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
import re
from msprof_analyze.prof_common.logger import get_logger

from msprof_analyze.advisor.dataset.timeline_event_dataset import ScheduleAnalysisDataset, MemCollector
from msprof_analyze.advisor.result.result import OptimizeResult
from msprof_analyze.advisor.result.item import OptimizeItem, OptimizeRecord


logger = get_logger()


class MemoryOpsChecker:

    def __init__(self):

        self.memory_issues = False
        self.optimization_item = []
        self.desc = ""
        self.suggestions = []
        self.memory_ops_duration_threshold = None
        self.max_mem_op_dur = 0

    def check_memory_ops(self, event_dataset: ScheduleAnalysisDataset):
        """
        :Param event_dataset: dataset of timeline event
        """
        if not hasattr(event_dataset, "memory_ops") or not getattr(event_dataset, "memory_ops") or \
                not event_dataset.memory_ops.mem_op_info:
            logger.debug("Skip slow memory ops checker, because no memory ops: %s", MemCollector.MEMORY_OP_NAME)
            return

        rule = event_dataset.memory_ops.rule
        max_dur_thres = rule.get("max_total_duration")
        raw_problem = rule.get("problem")

        for memory_op_name, memory_op_info in event_dataset.memory_ops.mem_op_info.items():
            op_dur = memory_op_info.get("total_dur")
            op_count = memory_op_info.get("count")
            if op_dur < max_dur_thres:
                continue
            if op_dur > self.max_mem_op_dur:
                self.max_mem_op_dur = op_dur

            self.memory_issues = True
            self.desc += raw_problem.format(memory_op_num=op_count, memory_op_name=memory_op_name,
                                            memory_op_dur=op_dur) + " "
            for solution in rule.get("solutions", []):
                if memory_op_name not in solution:
                    continue
                suggestions = solution.get(memory_op_name, {}).get("desc")
                for suggestion in suggestions:
                    self.suggestions.append(f"For {memory_op_name}: {suggestion}")

    def make_record(self, result: OptimizeResult):
        """
        make record for what and how to optimize
        """
        if not self.memory_issues:
            return

        self.optimization_item.append(OptimizeItem("Memory Operator Issues", self.desc, self.suggestions))
        for optimization in self.optimization_item:
            result.add(OptimizeRecord(optimization))

    def make_render(self, html_render, **kwargs):
        if not self.memory_issues:
            return
        priority = kwargs.get("priority")
        html_render.render_template(key="memory",
                                    template_dir="templates",
                                    template_name="memory.html",
                                    desc=self.desc,
                                    suggestions=self.suggestions,
                                    priority_background_color=priority,
                                    rank=kwargs.get("rank"))
