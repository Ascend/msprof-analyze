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

from msprof_analyze.advisor.analyzer.base_analyzer import BaseAnalyzer
from msprof_analyze.advisor.result.result import OptimizeResult
from msprof_analyze.advisor.analyzer.schedule.conjectured_gc.conjectured_gc_checker import ConjecturedGcChecker
from msprof_analyze.advisor.display.html.render import HTMLRender
from msprof_analyze.advisor.dataset.timeline_event_dataset import ScheduleAnalysisDataset
from msprof_analyze.advisor.display.html.priority_background_color import PriorityBackgroundColor


class ConjecturedGcAnalyzer(BaseAnalyzer):
    dataset_cls_list = [ScheduleAnalysisDataset]

    def __init__(self, collection_path, **kwargs):
        super().__init__(collection_path, **kwargs)
        self.result = OptimizeResult()
        self.html_render = HTMLRender()
        key = ScheduleAnalysisDataset.get_key()
        self.timeline_event_dataset = self.get_first_data_by_key(self.dataset_list, key)

    @BaseAnalyzer.check_data((ScheduleAnalysisDataset.get_key(),))
    def optimize(self, **kwargs):
        gc_checker = ConjecturedGcChecker()
        gc_checker.check_gc(self.timeline_event_dataset, rank=kwargs.get("rank"), stage=kwargs.get("stage"))
        gc_checker.make_record(self.result)
        gc_checker.make_render(self.html_render, priority=self.get_priority(), rank=kwargs.get("rank"))
        return self.result

    def get_priority(self, max_mem_op_dur=0):
        return PriorityBackgroundColor.medium
