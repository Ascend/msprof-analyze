#!/usr/bin/env python3
# -------------------------------------------------------------------------
# This file is part of the MindStudio project.
# Copyright (c) 2026 Huawei Technologies Co.,Ltd.
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

from msprof_analyze.prof_common.logger import get_logger
from typing import List

logger = get_logger()


class VersionControl:
    _SUPPORT_VERSIONS = []

    @classmethod
    def is_supported(cls, cann_version: str) -> bool:
        """
        Check whether the CANN software version is supported, which can be viewed by executing the following command:
        'cat /usr/local/Ascend/ascend-toolkit/latest/aarch64-linux/ascend_toolkit_install.info'
        """
        flag = cann_version in cls._SUPPORT_VERSIONS
        if not flag:
            logger.debug("class type is %s, which is not support current CANN version %s", cls.__name__, cann_version)
        return flag

    def get_support_version(self) -> List[str]:
        """
            Acquire the CANN software version
        :return: supported CANN software version
        """
        return self._SUPPORT_VERSIONS
