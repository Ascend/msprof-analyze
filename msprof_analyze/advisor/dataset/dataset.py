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

"""
dataset module
"""

from msprof_analyze.prof_common.logger import get_logger
import os
import re

from msprof_analyze.prof_common.constant import Constant
from msprof_analyze.prof_common.path_manager import PathManager
from msprof_analyze.advisor.config.config import Config

logger = get_logger()


class Dataset:
    """
    :param collection_path: dataSet absolute path
    dataset base class
    """

    PYTORCH_DB_PATTERN = re.compile(r'ascend_pytorch_profiler(?:_\d+)?\.db$')
    MINDSPORE_DB_PATTERN = re.compile(r'ascend_mindspore_profiler(?:_\d+)?\.db$')

    def __init__(self, collection_path, data=None, **kwargs) -> None:
        if data is None:
            data = {}
        self.collection_path = os.path.abspath(os.path.join(Config().work_path, collection_path))
        self.output_path = kwargs.get("output_path", None)
        self.data_type = self.get_data_type()
        if not self.output_path:
            self.output_path = self.collection_path
        logger.debug("init %s with %s", self.__class__.__name__, self.collection_path)
        if self._parse():
            key = self.get_key()
            if key not in data:
                data[key] = []
            data[key].append(self)

    def _parse(self):
        return None

    @classmethod
    def get_key(cls):
        """
        get key of dataset
        :return: key
        """
        return cls.__name__.rsplit('.', maxsplit=1)[-1]

    def get_data_type(self):
        # 递归搜索ASCEND_PROFILER_PATH文件夹
        for root, dirs, _ in PathManager.limited_depth_walk(self.collection_path):
            if Constant.ASCEND_PROFILER_OUTPUT in dirs:
                profiler_dir = os.path.join(root, Constant.ASCEND_PROFILER_OUTPUT)

                # 检查profiler目录下的文件
                for file in os.listdir(profiler_dir):
                    if self.PYTORCH_DB_PATTERN.match(file) or self.MINDSPORE_DB_PATTERN.match(file):
                        return Constant.DB  # 找到任意一种.db文件即返回

        return Constant.TEXT
