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
