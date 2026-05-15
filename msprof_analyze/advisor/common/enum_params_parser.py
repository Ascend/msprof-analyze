#!/usr/bin/env python3
# -*- coding: utf-8 -*-

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

import os
from msprof_analyze.prof_common.logger import get_logger
import typing

from msprof_analyze.advisor.common.timeline.event import AdvisorDict
from msprof_analyze.prof_common.singleton import singleton
from msprof_analyze.prof_common.file_manager import FileManager

logger = get_logger()


@singleton
class EnumParamsParser():
    # 枚举变量抽象成yaml文件，统一管理，便于第三方服务对接advisor时调用当前类查询所有枚举变量参数的默认值和可选值

    ARGUMENTS = "arguments"
    ENVS = "envs"
    OPTIONS = "options"
    DEFAULT = "default"
    TYPE = "type"
    STR_TYPE = "str"
    LIST_TYPE = "list"
    INT_TYPE = "int"
    BOOLEAN_TYPE = "boolean"

    def __init__(self):
        enum_params_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config",
                                        "enum_parameters.yaml")
        self.enum_params = FileManager.read_yaml_file(enum_params_path)
        self._set_value()

    def get_keys(self):
        return list(self.get_arguments_keys()) + list(self.get_envs_keys())

    def get_arguments_keys(self):
        return list(self.enum_params.get(self.ARGUMENTS, {}).keys())

    def get_envs_keys(self):
        return list(self.enum_params.get(self.ENVS, {}).keys())

    def get_options(self, key, filter_func=None):
        options = []
        for param_type in [self.ARGUMENTS, self.ENVS]:
            if key not in self.enum_params.get(param_type, {}):
                continue
            options = self.enum_params.get(param_type, {}).get(key, {}).get(self.OPTIONS, [])

        if not options:
            logger.error("Key %s not exists, optionals are %s", key, self.get_keys())

        if filter_func is not None and callable(filter_func):
            options = [value for value in options if filter_func(value)]

        return options

    def get_value_type(self, key):
        for param_type in [self.ARGUMENTS, self.ENVS]:
            if key not in self.enum_params.get(param_type, {}):
                continue
            value_type = self.enum_params.get(param_type, {}).get(key, {}).get(self.TYPE, self.STR_TYPE)
            return value_type
        return self.STR_TYPE

    def get_default(self, key):
        default_value = None
        for param_type in [self.ARGUMENTS, self.ENVS]:
            if key not in self.enum_params.get(param_type, {}):
                continue
            default_value = self.enum_params.get(param_type, {}).get(key, {}).get(self.DEFAULT, [])

        if not default_value:
            logger.error("Key %s not exists, optionals are %s", key, self.get_keys())

        return default_value

    def _set_value(self):

        for key in self.get_keys():

            if not hasattr(self, key):
                setattr(self, str(key), AdvisorDict())

            options = self.get_options(key)

            for value in options:
                if not isinstance(value, typing.Hashable):
                    continue
                getattr(self, key)[str(value)] = value
