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
from msprof_analyze.advisor.analyzer.computation.ai_core_freq.ai_core_freq_checker import AICoreFreqChecker
from msprof_analyze.advisor.display.html.priority_background_color import PriorityBackgroundColor
from msprof_analyze.advisor.display.html.render import HTMLRender
from msprof_analyze.advisor.dataset.timeline_event_dataset import ComputationAnalysisDataset
from msprof_analyze.advisor.dataset.profiling.device_info import DeviceInfoParser
from msprof_analyze.advisor.config.config import Config

logger = get_logger()


class AICoreFreqAnalyzer(BaseAnalyzer):
    dataset_cls_list = [ComputationAnalysisDataset]

    def __init__(self, collection_path, n_processes: int = 1, **kwargs) -> None:
        super().__init__(collection_path, n_processes, **kwargs)
        key = ComputationAnalysisDataset.get_key()
        self.dataset = self.get_first_data_by_key(self.dataset_list, key)
        self.result = OptimizeResult()
        self.html_render = HTMLRender()
        self.html = None
        info = DeviceInfoParser(collection_path)
        info.parse_data()

    @BaseAnalyzer.check_data((ComputationAnalysisDataset.get_key(),))
    def optimize(self, **kwargs):
        if not Config().get_config("aic_frequency"):
            logger.warning("Can not find ai core frequency in info.json*, please check data integrity.")
            return self.result

        add_render_list = kwargs.get("add_render_list", True)
        ai_core_freq_checker = AICoreFreqChecker()
        ai_core_freq_checker.check_ai_core_freq(self.dataset, rank=kwargs.get("rank"), stage=kwargs.get("stage"))
        ai_core_freq_checker.make_record(self.result)
        self.html = ai_core_freq_checker.make_render(self.html_render, add_render_list, priority=self.get_priority(),
                                                     rank=kwargs.get("rank"))
        return self.result

    def get_priority(self, max_mem_op_dur=None):
        return PriorityBackgroundColor.high