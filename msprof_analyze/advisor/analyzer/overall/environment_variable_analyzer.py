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
