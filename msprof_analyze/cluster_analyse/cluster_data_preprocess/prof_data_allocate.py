# Copyright (c) 2025, Huawei Technologies Co., Ltd.
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
from collections import defaultdict
import re
from typing import List, Dict

from msprof_analyze.cluster_analyse.cluster_data_preprocess.data_preprocessor import DataPreprocessor
from msprof_analyze.cluster_analyse.cluster_data_preprocess.mindspore_data_preprocessor import MindsporeDataPreprocessor
from msprof_analyze.cluster_analyse.cluster_data_preprocess.pytorch_data_preprocessor import PytorchDataPreprocessor
from msprof_analyze.cluster_analyse.cluster_data_preprocess.msprof_data_preprocessor import MsprofDataPreprocessor
from msprof_analyze.prof_common.path_manager import PathManager
from msprof_analyze.prof_common.constant import Constant
from msprof_analyze.prof_common.logger import get_logger

logger = get_logger()


class ProfDataAllocate:
    DB_PATTERNS = {
        Constant.PYTORCH: re.compile(r'^ascend_pytorch_profiler(?:_(\d+))?\.db$'),
        Constant.MINDSPORE: re.compile(r'^ascend_mindspore_profiler(?:_(\d+))?\.db$'),
        Constant.MSPROF: re.compile(r'^msprof_\d{14}\.db$'),
        Constant.MSMONITOR: re.compile(r'^msmonitor_(\d+)_\d{17}_(-1|\d+)\.db$')
    }

    ASCEND_PT = "ascend_pt"
    ASCEND_MS = "ascend_ms"
    PROF = "PROF_"
    DEFAULT_RANK_ID = -1

    def __init__(self, profiling_path):
        self.profiling_path = profiling_path
        self.data_type = ""
        self.data_map = {}
        self.prof_type = ""

        self._msmonitor_data_map = {}

    @staticmethod
    def match_file_pattern_in_dir(dir_name, file_pattern):
        for file_name in os.listdir(dir_name):
            if file_pattern.match(file_name):
                return file_name
        return ""

    @staticmethod
    def _extract_rank_id_from_profiler_db(file_name: str, prof_type: str):
        """从profiler_db文件名中提取rank_id，传入的file_name已经过正则匹配"""
        if prof_type not in [Constant.PYTORCH, Constant.MINDSPORE, Constant.MSMONITOR]:
            logger.error(f"Unsupported prof_type {prof_type}. Can not extract rank_id from profile db.")
            return None

        pattern = ProfDataAllocate.DB_PATTERNS[prof_type]
        match = pattern.match(file_name)

        if not match:
            return None

        try:
            if prof_type == Constant.MSMONITOR:
                # msmonitor格式：第二个捕获组是rank_id
                rank_str = match.group(2)
            else:
                # pytorch和mindspore格式：第一个捕获组是rank_id
                rank_str = match.group(1)

            # 处理特殊情况：ascend_pytorch_profiler.db（捕获组为None）
            if rank_str is None:
                logger.warning(f"No rank_id for {file_name}. Using default value {ProfDataAllocate.DEFAULT_RANK_ID}.")
                return ProfDataAllocate.DEFAULT_RANK_ID

            return int(rank_str)

        except (IndexError, ValueError) as e:
            logger.error(f"Failed to extract rank_id from {file_name}: {str(e)}")
            return None

    @staticmethod
    def _postprocess_data_maps(data_maps: Dict):
        """后处理数据映射"""
        return (
            DataPreprocessor.postprocess_data_map(data_maps[Constant.PYTORCH], Constant.PYTORCH),
            DataPreprocessor.postprocess_data_map(data_maps[Constant.MINDSPORE], Constant.MINDSPORE),
            DataPreprocessor.postprocess_data_map(data_maps[Constant.MSMONITOR], Constant.MSMONITOR)
        )

    def allocate_prof_data(self):
        if self.allocate_db_prof_data() and self.prof_type in [Constant.PYTORCH, Constant.MINDSPORE]:
            return True
        if self.allocate_text_prof_data():
            return True
        if self._msmonitor_data_map:
            self._set_prof_data(Constant.MSMONITOR, Constant.DB, self._msmonitor_data_map)
            return True
        logger.error(f"Failed to allocate profiling data!")
        return False

    def allocate_db_prof_data(self):
        data_maps = {
            Constant.PYTORCH: defaultdict(list),
            Constant.MINDSPORE: defaultdict(list),
            Constant.MSMONITOR: defaultdict(list)
        }
        # 处理输入路径，搜索路径下所有文件夹与文件，max_depth=10
        for root, dirs, files in PathManager.limited_depth_walk(self.profiling_path):
            self._scan_dirs_for_profiler_db(root, dirs, data_maps)
            self._scan_files_for_msmonitor_db(root, files, data_maps[Constant.MSMONITOR])

        # 处理输入路径为msmonitor db文件的情况
        if os.path.isfile(self.profiling_path):
            root, file_name = os.path.split(self.profiling_path)
            self._scan_files_for_msmonitor_db(root, [file_name], data_maps[Constant.MSMONITOR])

        # data_map: Dict[int, List[str]] --> Dict[int, str] 卡号路径一一对应
        pytorch_data_map, mindspore_data_map, msmonitor_data_map = self._postprocess_data_maps(data_maps)

        if not (pytorch_data_map or mindspore_data_map or msmonitor_data_map):
            return False

        # 检查是否多种类型文件同时存在
        if pytorch_data_map and mindspore_data_map:
            logger.error(f"Can not analysis PyTorch and MindSpore at the same time!")
            self.prof_type = Constant.INVALID
            return False

        # 确定采集类型prof_type
        if msmonitor_data_map:
            self._msmonitor_data_map = msmonitor_data_map
        if pytorch_data_map:
            self._set_prof_data(Constant.PYTORCH, Constant.DB, pytorch_data_map)
        if mindspore_data_map:
            self._set_prof_data(Constant.MINDSPORE, Constant.DB, mindspore_data_map)
        return True

    def allocate_text_prof_data(self):
        if self.prof_type == Constant.INVALID:
            return False

        ascend_pt_dirs = []
        ascend_ms_dirs = []
        prof_dirs = []

        def classify_dir(root, dir_name):
            """根据文件夹名称分类"""
            dir_path = os.path.join(root, dir_name)
            if dir_name.endswith(self.ASCEND_PT):
                ascend_pt_dirs.append(dir_path)
            elif dir_name.endswith(self.ASCEND_MS):
                ascend_ms_dirs.append(dir_path)
            elif dir_name.startswith(self.PROF):
                prof_dirs.append(dir_path)

        # 单独处理输入路径
        parent_dir = os.path.dirname(self.profiling_path)
        current_dir_name = os.path.basename(self.profiling_path)
        classify_dir(parent_dir, current_dir_name)
        # 递归处理子路径
        for root, dirs, _ in PathManager.limited_depth_walk(self.profiling_path):
            for dir_name in dirs:
                classify_dir(root, dir_name)

        pytorch_processor = PytorchDataPreprocessor(ascend_pt_dirs)
        pt_data_map = pytorch_processor.get_data_map()
        ms_processor = MindsporeDataPreprocessor(ascend_ms_dirs)
        ms_data_map = ms_processor.get_data_map()
        if pt_data_map and ms_data_map:
            logger.error("Can not analyze PyTorch and MindSpore meantime.")
            self.prof_type = Constant.INVALID
            return False
        if pt_data_map:
            self._set_prof_data(Constant.PYTORCH, Constant.TEXT, pt_data_map)
            return True
        if ms_data_map:
            self._set_prof_data(Constant.MINDSPORE, Constant.TEXT, ms_data_map)
            return True

        # 统一处理msprof数据
        msprof_processor = MsprofDataPreprocessor(prof_dirs)
        msprof_data_map = msprof_processor.get_data_map()
        msprof_data_type = msprof_processor.get_data_type()
        if msprof_data_map and msprof_data_type != Constant.INVALID:
            self._set_prof_data(Constant.MSPROF, msprof_data_type, msprof_data_map)
            return True
        return False

    def _scan_dirs_for_profiler_db(self, root: str, dirs: List[str], data_maps: Dict):
        if Constant.ASCEND_PROFILER_OUTPUT not in dirs:
            return
        profiler_dir = os.path.join(root, Constant.ASCEND_PROFILER_OUTPUT)
        for prof_type in [Constant.PYTORCH, Constant.MINDSPORE]:
            file_name = self.match_file_pattern_in_dir(profiler_dir, self.DB_PATTERNS[prof_type])
            if not file_name:
                continue
            rank_id = self._extract_rank_id_from_profiler_db(file_name, prof_type)
            if rank_id is not None:
                data_maps[prof_type][rank_id].append(root)

    def _scan_files_for_msmonitor_db(self, root: str, files: List[str], msmonitor_map: Dict):
        msmonitor_pattern = self.DB_PATTERNS[Constant.MSMONITOR]
        for file_name in files:
            if file_name.endswith(".db") and msmonitor_pattern.match(file_name):
                rank_id = self._extract_rank_id_from_profiler_db(file_name, Constant.MSMONITOR)
                if rank_id is not None:
                    msmonitor_map[rank_id].append(os.path.join(root, file_name))

    def _set_prof_data(self, prof_type, data_type, data_map):
        if prof_type != Constant.MSMONITOR and self._msmonitor_data_map:
            logger.warning(f"Find {prof_type} and msmonitor data at the same time! Just analysis {prof_type} data!")
        self.prof_type = prof_type
        self.data_type = data_type
        self.data_map = data_map

