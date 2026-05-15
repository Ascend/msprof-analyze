#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# Copyright (C) 2024-2024. Huawei Technologies Co., Ltd. All rights reserved.
# Licensed under the Apache License, Version 2.0 (the "License");
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
        flag = (cls._SUPPORT_VERSIONS.__contains__(cann_version))
        if not flag:
            logger.debug("class type is %s, which is not support current CANN version %s", cls.__name__, cann_version)
        return flag

    def get_support_version(self) -> List[str]:
        """
            Acquire the CANN software version
        :return: supported CANN software version
        """
        return self._SUPPORT_VERSIONS
