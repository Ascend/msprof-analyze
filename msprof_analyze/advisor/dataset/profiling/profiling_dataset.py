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

import yaml
from msprof_analyze.prof_common.constant import Constant
from msprof_analyze.advisor.common.profiling.ge_info import GeInfo
from msprof_analyze.advisor.common.profiling.msprof import Msprof, MsprofDB
from msprof_analyze.advisor.common.profiling.op_summary import OpSummary, OpSummaryDB
from msprof_analyze.advisor.common.profiling.tasktime import TaskTime
from msprof_analyze.advisor.common.enum_params_parser import EnumParamsParser
from msprof_analyze.advisor.dataset.dataset import Dataset
from msprof_analyze.advisor.dataset.profiling.device_info import DeviceInfoParser
from msprof_analyze.advisor.utils.utils import join_prof_path
from msprof_analyze.advisor.utils.utils import singleton
from msprof_analyze.prof_common.file_manager import FileManager


logger = get_logger()


@singleton
class ProfilingDataset(Dataset):
    LEGAL_CLASS_NAME = ["OpSummary", "Msprof", "MsprofDB", "OpSummaryDB", "GeInfo", "TaskTime"]
    prof_type = ""

    def __init__(self, collection_path, data: dict, **kwargs) -> None:
        self.cann_version = kwargs.get(Constant.CANN_VERSION, EnumParamsParser().get_default(Constant.CANN_VERSION))
        self.prof_type = kwargs.get(
            Constant.PROFILING_TYPE_UNDER_LINE, EnumParamsParser().get_default(Constant.PROFILING_TYPE_UNDER_LINE))
        self.patterns = self.parse_pattern()
        self.current_version_pattern = {}
        self._info = None
        super().__init__(collection_path, data)

    def build_from_pattern(self, dirs_pattern, current_path, depth):
        if depth > Constant.DEPTH_LIMIT:
            logger.error("Recursion depth exceeds limit!")
            return
        depth += 1
        if isinstance(dirs_pattern, dict):
            for key, value in dirs_pattern.items():
                self.build_from_pattern(value, join_prof_path(current_path, key), depth)
        elif isinstance(dirs_pattern, list):
            for item in dirs_pattern:
                if hasattr(self, item) and getattr(self, item):
                    # 避免重复构建kernel_details.csv, op_summary.csv的数据对象
                    continue
                file_pattern_list = self.current_version_pattern.get('file_attr').get(item)
                class_name = self.current_version_pattern.get('class_attr').get(item)
                if class_name not in self.LEGAL_CLASS_NAME:
                    logger.error(f"Invalid class name for parse profiling data.")
                    continue
                data_class = globals()[class_name]
                if not hasattr(data_class, "file_pattern_list"):
                    continue
                setattr(data_class, "file_pattern_list", self.current_version_pattern.get('file_attr').get(item))
                data_object = data_class(current_path)
                is_success = data_object.parse_data()
                if is_success:
                    setattr(self, item, data_object)
                elif current_path:
                    logger.info("Skip parse %s with file pattern %s from local path %s", 
                                self.current_version_pattern.get('class_attr').get(item),
                                file_pattern_list, current_path
                    )
        else:
            logger.warning(f"Unsupported arguments : %s to build %s", dirs_pattern, self.__class__.__name__)

    def get_current_data_pattern(self):
        """
        get data pattern by version and data_type
        """
        for config_dict in self.patterns['versions']:
            if (config_dict['version'] == self.cann_version and
                    config_dict['data_type'] == self.data_type):
                return config_dict
        return dict()

    def parse_pattern(self, config_path="config/profiling_data_version_config.yaml"):

        if not os.path.isabs(config_path):
            config_path = os.path.join(os.path.dirname(__file__),
                                     "../", "../", config_path)

        if not os.path.exists(config_path):
            logger.warning("Skip parse profiling dataset, because %s does not exist.", config_path)
            return []

        patterns = FileManager.read_yaml_file(config_path)

        return patterns if patterns else []

    def collection_path(self):
        """collection_path"""
        return self.collection_path
    
    def _parse(self):
        self.current_version_pattern = self.get_current_data_pattern()
        info = DeviceInfoParser(self.collection_path)
        if info.parse_data():
            self._info = info
        ret = False
        dirs_pattern = self.current_version_pattern.get("dirs_pattern")
        if dirs_pattern is not None:
            self.build_from_pattern(dirs_pattern, self.collection_path, 0)
            ret = True

        return ret
