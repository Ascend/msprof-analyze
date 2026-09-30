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
from msprof_analyze.advisor.result.result import OptimizeResult
from msprof_analyze.advisor.result.item import OptimizeItem, OptimizeRecord
from msprof_analyze.prof_common.additional_args_manager import AdditionalArgsManager
from msprof_analyze.prof_common.file_manager import FileManager

logger = get_logger()


class SyncBNChecker:
    def __init__(self):
        self.optimization_item = []
        self.syncbn_issues = False
        self.desc = ""
        self.suggestions = []
        self.solutions = None
        self.max_syncbn_num = None
        self._init_rule()

    def check_syncbn(self, event_dataset: ScheduleAnalysisDataset):
        """
        :Param event_dataset: dataset of timeline event
        """
        if not hasattr(event_dataset, "sync_batchnorm") or not getattr(event_dataset, "sync_batchnorm"):
            logger.debug("Skip syncbn checker, because no syncbn found")
            return

        syncbn_num = len(event_dataset.sync_batchnorm)
        self.syncbn_issues = syncbn_num >= self.max_syncbn_num
        self.desc = self.desc.format(syncbn_num=syncbn_num)

    def make_record(self, result: OptimizeResult):
        """
        make record for what and how to optimize
        """
        if not self.syncbn_issues:
            return

        self.optimization_item.append(OptimizeItem("SyncBatchNorm Issues", self.desc, self.suggestions))
        for optimization in self.optimization_item:
            result.add(OptimizeRecord(optimization))

    def make_render(self, html_render, **kwargs):
        if not self.syncbn_issues:
            return

        priority = kwargs.get("priority")
        rank = kwargs.get("rank")
        html_render.render_template(
            key="schedule",
            template_dir="templates",
            template_name="sync_batchnorm.html",
            desc=self.desc,
            solutions=self.solutions,
            priority_background_color=priority,
            rank=rank,
        )

    def _init_rule(self):
        language = AdditionalArgsManager().language
        syncbn_rule_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))),
            "rules",
            language,
            "sync_batchnorm.yaml",
        )

        syncbn_rule = FileManager.read_yaml_file(syncbn_rule_path)

        self.max_syncbn_num = syncbn_rule.get("max_syncbn_num")
        self.desc = syncbn_rule.get("problem")

        self.solutions = syncbn_rule.get("solutions")
        for solution in self.solutions:
            for key, val in solution.items():
                self.suggestions.append(f"{key}, {val.get('desc')}")
