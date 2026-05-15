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

"""
profiling base
"""
from msprof_analyze.prof_common.logger import get_logger
from typing import Dict, List

from msprof_analyze.advisor.dataset.profiling.profiling_parser import ProfilingParser
from msprof_analyze.advisor.utils.utils import join_prof_path

logger = get_logger()


class ProfilingBuilderBase:
    """
    profiling base
    """
    DATA_LIST: List[Dict] = []

    def __init__(self, path) -> None:
        self._path = path

    def parse_data(self) -> bool:
        """
        parse data for file in data_dir
        """
        if isinstance(self, ProfilingParser):
            return True
        ret = False
        for data in self.DATA_LIST:
            class_name = data.get("class_name")
            if class_name is not None:
                if data.get("subdir_name"):
                    data_class = data.get("class_name")(join_prof_path(self._path, data.get("subdir_name")))
                else:
                    data_class = data.get("class_name")(self._path)
                if data_class.parse_data():
                    setattr(self, str(data.get("attr_name")), data_class)
                    ret = True
        return ret
