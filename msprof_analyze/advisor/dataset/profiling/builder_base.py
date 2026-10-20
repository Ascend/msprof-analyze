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
