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
import os
import re
from msprof_analyze.prof_common.logger import get_logger
import yaml

from msprof_analyze.advisor.dataset.timeline_event_dataset import ScheduleAnalysisDataset
from msprof_analyze.advisor.result.result import OptimizeResult
from msprof_analyze.advisor.result.item import OptimizeItem, OptimizeRecord
from msprof_analyze.prof_common.additional_args_manager import AdditionalArgsManager
from msprof_analyze.prof_common.file_manager import FileManager

logger = get_logger()


class DataloaderChecker:

    def __init__(self):

        self.dataloader_issues = False
        self.optimization_item = []
        self.desc = ""
        self.suggestions = []
        self.dataloader_duration_threshold = None
        self._init_rule()

    def check_slow_dataloader(self, event_dataset: ScheduleAnalysisDataset):
        """
        :Param event_dataset: dataset of timeline event
        """
        if not hasattr(event_dataset, "dataloader") or not getattr(event_dataset, "dataloader"):
            logger.debug("Skip slow dataloader checker, because no dataloader duration larger than %s",
                         self.dataloader_duration_threshold)
            return
        for event in event_dataset.dataloader:

            dataloader_duration = float(event.dur)
            if dataloader_duration < self.dataloader_duration_threshold:
                continue
            self.desc = self.desc.format(dataloader_duration=dataloader_duration,
                                         dataloader_duration_threshold=self.dataloader_duration_threshold)
            self.dataloader_issues = True

            if re.search("singleprocess", event.name.lower()):
                self.suggestions = self._reset_suggestions(["I/O", "num_workers"])

    def make_record(self, result: OptimizeResult):
        """
        make record for what and how to optimize
        """
        if not self.dataloader_issues:
            return

        self.optimization_item.append(OptimizeItem("Slow Dataloader Issues", self.desc, self.suggestions))
        for optimization in self.optimization_item:
            result.add(OptimizeRecord(optimization))

    def make_render(self, html_render, **kwargs):
        if not self.dataloader_issues:
            return
        priority = kwargs.get("priority")
        html_render.render_template(key="dataloader",
                                    template_dir="templates",
                                    template_name="slow_dataloader.html",
                                    desc=self.desc,
                                    suggestions=self.suggestions,
                                    priority_background_color=priority,
                                    rank=kwargs.get("rank"))

    def _init_rule(self):
        language = AdditionalArgsManager().language
        dataloader_rule_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(__file__)))),
            "rules",
            language,
            "dataloader.yaml"
        )
        dataloader_rule = FileManager.read_yaml_file(dataloader_rule_path)

        self.dataloader_duration_threshold = dataloader_rule.get("dataloader_duration_threshold")
        self.desc = dataloader_rule.get("problem")
        self.suggestions = dataloader_rule.get("solutions")

    def _reset_suggestions(self, suggestion_pattern_list):

        suggestions = []
        for solution in self.suggestions:
            for suggestion_pattern in suggestion_pattern_list:
                if re.search(suggestion_pattern, solution):
                    suggestions.append(solution)
        return suggestions
