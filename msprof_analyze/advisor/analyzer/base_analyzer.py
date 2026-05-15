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
import os
from functools import wraps
from typing import Dict, List, Union
from abc import abstractmethod, ABCMeta

from msprof_analyze.prof_common.constant import Constant
from msprof_analyze.advisor.common.enum_params_parser import EnumParamsParser
from msprof_analyze.advisor.common.version_control import VersionControl
from msprof_analyze.advisor.dataset.dataset import Dataset
from msprof_analyze.advisor.result.result import OptimizeResult
from msprof_analyze.advisor.display.html.render import HTMLRender
from msprof_analyze.advisor.display.html.priority_background_color import PriorityBackgroundColor
from msprof_analyze.advisor.utils.utils import safe_division
from msprof_analyze.prof_common.file_manager import FileManager
from msprof_analyze.prof_common.path_manager import PathManager

logger = get_logger()

ASCEND_PT = "ascend_pt"
ASCEND_MS = "ascend_ms"
PROFILER_INFO_HEAD = "profiler_info_"
PROFILER_INFO_EXTENSION = ".json"
MS_VERSION = "ms_version"


class BaseAnalyzer(VersionControl, metaclass=ABCMeta):
    _SUPPORT_VERSIONS = EnumParamsParser().get_options(Constant.CANN_VERSION)
    ANALYZER_HIGH_PRIORITY_TIME_RATIO = 0.05
    ANALYZER_MEDIUM_PRIORITY_TIME_RATIO = 0.03

    dataset_cls_list = []

    def __init__(self, collection_path, n_processes: int = 1, **kwargs):
        self.n_processes = n_processes
        self.kwargs = kwargs
        self.collection_path = collection_path
        self.output_path = kwargs.get("output_path", None)
        self.cann_version = kwargs.get(Constant.CANN_VERSION, EnumParamsParser().get_default(Constant.CANN_VERSION))
        self.profiling_type = self.identify_profiling_type(
            EnumParamsParser().get_options(Constant.PROFILING_TYPE_UNDER_LINE))
        self.profiling_version = self.identify_profiling_version()
        self.html_render = HTMLRender()
        self.dataset_list: Dict[str, List[Dataset]] = {}
        self.init_dataset_list()
        self.result = OptimizeResult()
        self.record_list: Dict[str, List] = {}

    @staticmethod
    def get_first_data_by_key(data, key) -> Union[Dataset, None]:
        """
        get the first member from data with key
        :param data: input data
        :param key: data key
        :return: the first dataset in dataset list
        """
        if key in data and len(data[key]) > 0:
            return data[key][0]
        return None

    @classmethod
    def check_data(cls, data_list: tuple):
        """
        check if all data in data list is contained
        :param data_list: data list to check
        :return: func ptr if check success
        """

        def decorate(func):

            @wraps(func)
            def wrapper(self, **kwargs):
                data = self.dataset_list
                if data is None:
                    return None
                for data_key in data_list:
                    if data_key not in data:
                        return None

                logger.info("Start analysis %s with %s", self.__class__.__name__, ",".join(data_list))
                return func(self, **kwargs)

            return wrapper

        return decorate

    @abstractmethod
    def optimize(self, **kwargs):
        pass

    @abstractmethod
    def get_priority(self, max_mem_op_dur):
        pass

    def identify_profiling_type(self, profiling_type_list):
        profiling_type = ""
        if not profiling_type_list:
            return profiling_type
        if self.collection_path.endswith(ASCEND_MS):
            profiling_type = [elem for elem in profiling_type_list if Constant.MINDSPORE in elem][0]
        elif self.collection_path.endswith(ASCEND_PT):
            profiling_type = [elem for elem in profiling_type_list if Constant.PYTORCH in elem][0]
        else:
            for _, dirs, __ in PathManager.limited_depth_walk(self.collection_path):
                is_found_type = False
                for direction in dirs:
                    if direction.endswith(ASCEND_MS):
                        profiling_type = [elem for elem in profiling_type_list if Constant.MINDSPORE in elem][0]
                        is_found_type = True
                        break
                    elif direction.endswith(ASCEND_PT):
                        profiling_type = [elem for elem in profiling_type_list if Constant.PYTORCH in elem][0]
                        is_found_type = True
                        break
                if is_found_type:
                    break
        if self.kwargs.get(Constant.PROFILING_TYPE_UNDER_LINE) and self.kwargs.get(
                Constant.PROFILING_TYPE_UNDER_LINE) != profiling_type:
            logger.warning("%s The input profiling type %s is inconsistent with the actual profiling type %s.",
                           self.__class__.__name__, self.kwargs.get(Constant.PROFILING_TYPE_UNDER_LINE), profiling_type)
        if not profiling_type:
            logger.warning("Unknown profiling type, the default value is set pytorch.")
            profiling_type = profiling_type_list[0]
        return profiling_type

    def identify_profiling_version(self):
        profiling_version = ""
        if Constant.MINDSPORE in self.profiling_type:
            ascend_dirs = []
            if self.collection_path.endswith(ASCEND_MS):
                ascend_dirs.append(self.collection_path)
            else:
                for root, dirs, _ in PathManager.limited_depth_walk(self.collection_path):
                    for direction in dirs:
                        if direction.endswith(ASCEND_MS):
                            ascend_dirs.append(os.path.join(root, direction))
            if ascend_dirs:
                ascend_dir = ascend_dirs[0]
                for file_name in os.listdir(ascend_dir):
                    if file_name.startswith(PROFILER_INFO_HEAD) and file_name.endswith(PROFILER_INFO_EXTENSION):
                        file_path = os.path.join(ascend_dir, file_name)
                        config = FileManager.read_json_file(file_path)
                        profiling_version = config.get(MS_VERSION, "")
                        break
            if profiling_version and self.kwargs.get(Constant.MINDSPORE_VERSION):
                if profiling_version != self.kwargs.get(Constant.MINDSPORE_VERSION):
                    logger.warning("%s The input version %s is inconsistent with the actual version %s.",
                                   self.__class__.__name__, self.kwargs.get(Constant.MINDSPORE_VERSION),
                                   profiling_version)
        elif Constant.PYTORCH in self.profiling_type:
            profiling_version = self.kwargs.get(Constant.TORCH_VERSION,
                                                EnumParamsParser().get_default(Constant.TORCH_VERSION))
            if self.kwargs.get(Constant.TORCH_VERSION) and profiling_version != self.kwargs.get(Constant.TORCH_VERSION):
                logger.warning("%s The input version %s is inconsistent with the actual version %s.",
                               self.__class__.__name__, self.kwargs.get(Constant.TORCH_VERSION), profiling_version)
        return profiling_version

    def init_dataset_list(self) -> None:
        dataset_cls_list = self.dataset_cls_list
        if len(dataset_cls_list) == 0:
            logger.warning(f"Analyser: %s don't rely on any dataset!", self.__class__.__name__)
            return

        for dataset_cls in dataset_cls_list:
            if dataset_cls and callable(dataset_cls):
                try:
                    dataset = dataset_cls(collection_path=self.collection_path, data=self.dataset_list, **self.kwargs)
                except Exception as e:
                    logger.error(e)
                    continue
                key = dataset_cls.get_key()
                if key not in self.dataset_list:
                    self.dataset_list[key] = []
                    self.dataset_list[key].append(dataset)

    def get_priority_by_time_ratio(self, dur, step_dur):
        time_ratio = safe_division(dur, step_dur)
        if time_ratio >= self.ANALYZER_HIGH_PRIORITY_TIME_RATIO:
            return PriorityBackgroundColor.high
        elif time_ratio >= self.ANALYZER_MEDIUM_PRIORITY_TIME_RATIO:
            return PriorityBackgroundColor.medium
        else:
            return PriorityBackgroundColor.low
