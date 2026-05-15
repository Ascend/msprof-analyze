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
from msprof_analyze.prof_common.logger import get_logger

from msprof_analyze.prof_common.constant import Constant
from msprof_analyze.prof_common.file_manager import FileManager
from msprof_analyze.prof_common.path_manager import PathManager

logger = get_logger()


class EnvironmentVariableDataset:
    def __init__(self, collection_path, data: dict, **kwargs):
        self.collection_path = collection_path
        self.env_data = {}
        self.read_data()

    @staticmethod
    def get_env_data_file(collection_path: str) -> str:
        for root, _, files in PathManager.limited_depth_walk(collection_path):
            for file_name in files:
                if file_name == Constant.PROFILER_METADATA:
                    return os.path.join(root, file_name)
        return ""

    @classmethod
    def get_key(cls):
        return cls.__module__.rsplit('.', maxsplit=1)[-1]

    def read_data(self):
        data_path = self.get_env_data_file(self.collection_path)
        if not data_path:
            return
        try:
            self.env_data = FileManager.read_json_file(data_path)
        except RuntimeError as e:
            logger.error("Read json failed. %s", str(e))
