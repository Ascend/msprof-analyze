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
import re
from abc import abstractmethod

from msprof_analyze.prof_common.constant import Constant
from msprof_analyze.prof_common.logger import get_logger

logger = get_logger()


class DataPreprocessor:
    PROFILER_INFO_HEAD = 'profiler_info_'
    PROFILER_INFO_EXTENSION = '.json'
    TIME_POSITION_DICT = {
        Constant.PYTORCH: -3,
        Constant.MINDSPORE: -3,
        Constant.MSMONITOR: -2,
        Constant.MSPROF: -2
    }
    PROFILING_DIR_FORMAT = {
        Constant.PYTORCH: "{worker_name}_{timestamp}_ascend_pt",
        Constant.MINDSPORE: "{worker_name}_{timestamp}_ascend_ms",
        Constant.MSPROF: "PROF_{number}_{timestamp}_{string}",
        Constant.MSMONITOR: "msmonitor_{pid}_{timestamp}_{rank_id}.db"
    }

    def __init__(self, path_list: list):
        self.path_list = path_list
        self.data_map = {}
        self.data_type = None

    @property
    @abstractmethod
    def db_pattern(self):
        pass

    @staticmethod
    def postprocess_data_map(data_map, prof_type):
        if not data_map:
            return {}

        timestamp_position = DataPreprocessor.TIME_POSITION_DICT.get(prof_type, None)
        if timestamp_position is None:
            logger.error(f'Unsupported profiling type: {prof_type}. '
                         f'Unable to determine timestamp position for path processing.')
            return {}

        valid_data_map = {}
        invalid_ranks = []

        for rank_id, path_list in data_map.items():
            if not path_list:
                continue
            if len(path_list) == 1:
                valid_data_map[rank_id] = path_list[0]
                continue

            # 处理多个路径的情况，选择时间戳最新的路径
            try:
                sorted_paths = sorted(path_list, key=lambda x: int(x.split('_')[timestamp_position]), reverse=True)
                latest_path = sorted_paths[0]
                valid_data_map[rank_id] = latest_path
                logger.info(f"Rank {rank_id}: Multiple profiling paths detected. "
                             f"Selected latest timestamp path: {latest_path}")
            except Exception as e:
                invalid_ranks.append(rank_id)

        if invalid_ranks:
            logger.warning(
                "Failed to process multiple profiling paths for some ranks. "
                f"Affected rank_id: {invalid_ranks}. "
                f"Expected path formats: {DataPreprocessor.PROFILING_DIR_FORMAT.get(prof_type)}"
            )

        return valid_data_map

    @abstractmethod
    def get_data_map(self):
        pass

    @staticmethod
    def get_rank_id(dir_name: str) -> int:
        files = os.listdir(dir_name)
        for file_name in files:
            if file_name.startswith(DataPreprocessor.PROFILER_INFO_HEAD) and file_name.endswith(DataPreprocessor.PROFILER_INFO_EXTENSION):
                rank_id_str = file_name[len(DataPreprocessor.PROFILER_INFO_HEAD): -1 * len(DataPreprocessor.PROFILER_INFO_EXTENSION)]
                try:
                    rank_id = int(rank_id_str)
                except ValueError:
                    rank_id = -1
                return rank_id
        return -1

    def get_data_type(self):
        if self.data_type is not None:
            return self.data_type
        data_type_record = set()
        for _, dir_name in self.data_map.items():
            ascend_profiler_output = os.path.join(dir_name, Constant.ASCEND_PROFILER_OUTPUT)
            data_type = Constant.DB if self._check_db_type(ascend_profiler_output) else Constant.TEXT
            data_type_record.add(data_type)
        if len(data_type_record) == 1:
            return data_type_record.pop()
        return Constant.INVALID

    def _check_db_type(self, dir_name):
        for file_name in os.listdir(dir_name):
            if re.match(self.db_pattern, file_name):
                return True
        return False
