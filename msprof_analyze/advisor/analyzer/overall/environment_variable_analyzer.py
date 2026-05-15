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
from msprof_analyze.advisor.analyzer.base_analyzer import BaseAnalyzer
from msprof_analyze.prof_common.logger import get_logger
from msprof_analyze.prof_common.path_manager import PathManager
from msprof_analyze.advisor.dataset.environment_variable_dataset import EnvironmentVariableDataset
from msprof_analyze.advisor.analyzer.overall.environment_variable_checker import EnvironmentVariableChecker
from msprof_analyze.advisor.display.html.priority_background_color import PriorityBackgroundColor

logger = get_logger()


class EnvironmentVariableAnalyzer(BaseAnalyzer):
    dataset_cls_list = [EnvironmentVariableDataset]

    def __init__(self, collection_path: str, n_processes: int = 1, **kwargs):
        super().__init__(collection_path, n_processes, **kwargs)
        self.dataset = self.get_first_data_by_key(self.dataset_list, EnvironmentVariableDataset.get_key())

    @BaseAnalyzer.check_data((EnvironmentVariableDataset.get_key(),))
    def optimize(self, **kwargs):
        if "mindspore" in self.profiling_type:
            logger.info("The analyzer %s does not support MindSpore.", self.__class__.__name__)
            return self.result
        try:
            PathManager.check_input_directory_path(self.collection_path)
        except RuntimeError as e:
            logger.error("Invalid path: %s", str(e))
            return self.result
        self.collection_path = PathManager.get_realpath(self.collection_path)
        checker = EnvironmentVariableChecker()
        checker.format_env_suggest(self.dataset)
        checker.make_record(self.result)
        checker.make_render(self.html_render)
        return self.result

    def get_priority(self, max_mem_op_dur=None):
        return PriorityBackgroundColor.high

    def make_record(self):
        pass

    def make_render(self):
        pass
