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
from msprof_analyze.prof_common.logger import get_logger

from msprof_analyze.advisor.analyzer.base_analyzer import BaseAnalyzer
from msprof_analyze.advisor.result.result import OptimizeResult
from msprof_analyze.advisor.analyzer.schedule.syncbn.syncbn_checker import SyncBNChecker
from msprof_analyze.advisor.display.html.priority_background_color import PriorityBackgroundColor
from msprof_analyze.advisor.display.html.render import HTMLRender
from msprof_analyze.advisor.dataset.timeline_event_dataset import ScheduleAnalysisDataset

logger = get_logger()


class SyncBNAnalyzer(BaseAnalyzer):
    dataset_cls_list = [ScheduleAnalysisDataset]

    def __init__(self, collection_path, **kwargs):
        super().__init__(collection_path, **kwargs)
        self.result = OptimizeResult()
        self.html_render = HTMLRender()
        key = ScheduleAnalysisDataset.get_key()
        self.timeline_event_dataset = self.get_first_data_by_key(self.dataset_list, key)

    @BaseAnalyzer.check_data((ScheduleAnalysisDataset.get_key(),))
    def optimize(self, **kwargs):
        syncbn_checker = SyncBNChecker()
        syncbn_checker.check_syncbn(self.timeline_event_dataset)
        syncbn_checker.make_record(self.result)
        syncbn_checker.make_render(self.html_render, priority=self.get_priority(), rank=kwargs.get("rank"))
        return self.result

    def get_priority(self, max_mem_op_dur=None):
        return PriorityBackgroundColor.high