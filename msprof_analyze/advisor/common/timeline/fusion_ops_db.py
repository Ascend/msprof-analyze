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

from msprof_analyze.prof_common.logger import get_logger
import os

from msprof_analyze.prof_common.constant import Constant
from msprof_analyze.advisor.common.enum_params_parser import EnumParamsParser
from msprof_analyze.advisor.common.timeline.fusion_ops_rule import OpRule
from msprof_analyze.advisor.common.timeline.fusion_ops_rule_handler import TimelineOpRuleHandler
from msprof_analyze.advisor.utils.utils import get_file_path_by_walk
from msprof_analyze.prof_common.file_manager import FileManager

logger = get_logger()


def init_timeline_ops_db(cann_version=None, profiling_type=None, profiling_version=None):
    logger.debug("init operators database")

    return FusionOperatorDB(cann_version=cann_version,
                            profiling_type=profiling_type,
                            profiling_version=profiling_version)


def get_timeline_fusion_ops_yaml_path():
    # 环境变量 ADVISOR_RULE_PATH 不为空且该路径存在, os.walk遍历其下文件, 若存在相应的规则文件则返回路径
    advisor_rule_path = os.getenv(Constant.ADVISOR_RULE_PATH)
    if advisor_rule_path and os.path.exists(advisor_rule_path):
        specified_file_path = get_file_path_by_walk(advisor_rule_path, Constant.TIMELINE_FUSION_OPS_YAML_NAME)
        if len(specified_file_path.strip()) and os.path.exists(specified_file_path):
            logger.debug("Successfully find The %s file which is specified by the environment variable: %s.",
                         specified_file_path, Constant.ADVISOR_RULE_PATH)
            return specified_file_path
        logger.warning("The %s does not exist in path: %s. Try to use cloud or default local YAML file.",
                       Constant.TIMELINE_FUSION_OPS_YAML_NAME, os.path.normpath(advisor_rule_path))
    # 检查云文件默认保存路径文件夹下是否存在相应文件, 默认路径 ~/rules/cloud/
    cloud_file_path = os.path.join(os.path.expanduser("~"), Constant.CLOUD_RULE_PATH,
                                   Constant.TIMELINE_FUSION_OPS_YAML_NAME)
    if os.path.exists(cloud_file_path):
        logger.debug("Successfully find The cloud %s file in %s.", Constant.TIMELINE_FUSION_OPS_YAML_NAME,
                     cloud_file_path)
        return cloud_file_path
    # 检查本地默认文件
    local_file_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(__file__)))),
                                   Constant.DEFAULT_RULE_PATH, Constant.TIMELINE_FUSION_OPS_YAML_NAME)
    if not os.path.exists(local_file_path):
        # 若本地默认文件不存在, 则log异常信息并
        logger.error("The default local YAML file does not exist. Please check the YAML file in the default path %s.",
                     local_file_path)
    return local_file_path


class FusionOperatorDB:

    def __init__(self, cann_version=None, profiling_type=None, profiling_version=None):
        self.timeline_fusion_ops_yaml_path = os.path.normpath(get_timeline_fusion_ops_yaml_path())
        self.cann_version = cann_version or EnumParamsParser().get_default(Constant.CANN_VERSION)
        self.profiling_type = profiling_type or EnumParamsParser().get_default(Constant.PROFILING_TYPE_UNDER_LINE)
        self.profiling_version = profiling_version or EnumParamsParser().get_default(Constant.PROFILING_TYPE_UNDER_LINE)

        self._supported_version_dict = {}

        self.is_empty = False
        self.timeline_op_rule_handler = TimelineOpRuleHandler()
        self.fusion_operator = self._load_yaml(
            self.timeline_fusion_ops_yaml_path) if profiling_type == Constant.PYTORCH else {}

        self._dequeue_op_names = []
        self._aten_op_names = []
        self._optimizer_op_names = []
        self._dequeue_op_api_map = {}
        self._aten_op_api_map = {}
        self._optimizer_op_api_map = {}
        self._parse_db()

    @property
    def dequeue_op_names(self):
        return self._dequeue_op_names

    @property
    def aten_op_names(self):
        return self._aten_op_names

    @property
    def optimizer_op_names(self):
        return self._optimizer_op_names

    @property
    def dequeue_op_api_map(self):
        return self._dequeue_op_api_map

    @property
    def aten_op_api_map(self):
        return self._aten_op_api_map

    @property
    def optimizer_op_api_map(self):
        return self._optimizer_op_api_map

    def get_fusion_operator_with_unique_id(self, unique_id):
        if unique_id == Constant.TIMELINE_FUSION_OPS_INVALID_UNIQUE_ID:
            logger.warning("The specified unique id: %s is invalid.Please check whether the rule of the unique id "
                           "exists and modify the rule.", Constant.TIMELINE_FUSION_OPS_INVALID_UNIQUE_ID)
            return {}
        result_tmp_rule = self.timeline_op_rule_handler.get_tmp_timeline_op_rule_with_unique_id(unique_id)
        result_op_rule = OpRule(result_tmp_rule)
        return result_op_rule.get_final_rules()

    def regenerate_timeline_op_rule_with_unique_id(self, unique_id):
        self.fusion_operator.clear()
        logger.debug("Program try to regenerate the rule to version %s.", unique_id)
        self.fusion_operator = self.get_fusion_operator_with_unique_id(unique_id)
        self.regenerate_op_api_map_and_op_names()

    def regenerate_timeline_op_rule_with_version(self, cann_version=None, torch_version=None):
        cann_version = cann_version or self.cann_version
        torch_version = torch_version or self.profiling_version
        unique_id = self._get_unique_id_in_supported_version_dict(cann_version=cann_version,
                                                                  torch_version=torch_version)
        self.regenerate_timeline_op_rule_with_unique_id(unique_id)

    def regenerate_op_api_map_and_op_names(self):
        self._dequeue_op_names.clear()
        self._aten_op_names.clear()
        self._optimizer_op_names.clear()
        self._dequeue_op_api_map.clear()
        self._aten_op_api_map.clear()
        self._optimizer_op_api_map.clear()
        self._parse_db()

    def _is_version_supported(self, db_content):
        """校验当前版本是否被规则库中的版本支持, 保存版本支持信息数组, 按数组或字符串的可变方式保存"""
        if db_content is None:
            logger.warning(
                "The rule library is empty. Check the rule library file: %s",
                self.timeline_fusion_ops_yaml_path
            )
            return False
        for rule_dic in db_content:
            if not isinstance(rule_dic, dict) or rule_dic.get("unique_id") is None:
                continue
            cann_version_list = rule_dic.get("cann_version")
            torch_version_list = rule_dic.get("torch_version")
            if not cann_version_list or not torch_version_list:
                continue
            supported_version = [cann_version_list, torch_version_list]

            unique_id = rule_dic.get("unique_id")
            if unique_id < 0:
                logger.warning(
                    "The unique id: %s of the rule should be a positive integer. "
                    "Please check and modify the rule configuration in the YAML file： %s.",
                    unique_id, os.path.normpath(self.timeline_fusion_ops_yaml_path)
                )
            self._supported_version_dict[unique_id] = supported_version

        # 若解析timeline规则库的版本支持数组为空, 则存在问题
        if not self._supported_version_dict:
            logger.warning(
                "The rule library does not contain rules that support the current version. "
                "Check the rule library file: %s",
                self.timeline_fusion_ops_yaml_path
            )
            return False

        # 检验当前版本是否被规则库支持
        is_version_supported = self._is_version_supported_in_supported_version_dict()
        if not is_version_supported:
            # 若规则库不支持当前版本, 则log警告信息
            logger.warning("Unsupported versions: cann-%s and torch-%s, supported version list of ['cann', 'torch'] "
                           "is %s", self.cann_version, self.profiling_version, self._supported_version_dict.values())
        return is_version_supported

    def _is_version_supported_in_supported_version_dict(self, cann_version=None, torch_version=None):
        """校验当前版本是否存在在规则库中的版本支持字典中"""
        for _, supported_version in self._supported_version_dict.items():
            if self._is_version_supported_in_versions(supported_version, cann_version, torch_version):
                return True
        return False

    def _get_unique_id_in_supported_version_dict(self, cann_version=None, torch_version=None) -> int:
        """校验当前版本是否存在在规则库中的版本支持字典中, 在使用前请检查是否支持该版本"""
        for key_unique_id, supported_version in self._supported_version_dict.items():
            if self._is_version_supported_in_versions(supported_version, cann_version, torch_version):
                return key_unique_id
        return Constant.TIMELINE_FUSION_OPS_INVALID_UNIQUE_ID

    def _is_version_supported_in_versions(self, supported_version, cann_version=None, torch_version=None):
        """校验当前cann版本和torch版本是否存在在规则库中的版本支持数组的元素中"""
        cann_version_list = supported_version[0]
        if not isinstance(cann_version_list, list):
            cann_version_list = [cann_version_list]

        torch_version_list = supported_version[1]
        if not isinstance(torch_version_list, list):
            torch_version_list = [torch_version_list]

        cann_version = cann_version or self.cann_version
        torch_version = torch_version or self.profiling_version

        if (cann_version in cann_version_list) and (torch_version in torch_version_list):
            return True
        return False

    def _parse_db(self):
        """生成输出的规则库"""
        self._parse(Constant.ATEN)
        self._parse(Constant.DEQUEUE)
        self._parse(Constant.OPTIMIZER)

    def _parse(self, mode):
        """生成输出的规则库中指定部分， 如aten, Optimizer等"""
        op_info = self.fusion_operator.get(mode, []) or []
        for ops in op_info:
            for npu_api, op_combined in ops.items():
                if not isinstance(op_combined, list):
                    self._parse_in_list(mode, op_combined, npu_api)
                for _op_combined in op_combined:
                    self._parse_in_list(mode, _op_combined, npu_api)

    def _parse_in_list(self, mode, op_combined, npu_api):
        """生成输出的规则库中具体部分， 如{silu: torch_npu.npu_silu/torch_npu.contrib.module.SiLU}等"""
        if not isinstance(op_combined, str):
            logger.warning("Error type in yaml: %s", op_combined)
            return
        mode_str = mode.lower()
        getattr(self, f"{mode_str}_op_names", []).extend(op_combined.split("-"))

        new_npu_api = npu_api
        pre_npu_api = getattr(self, f"{mode_str}_op_api_map", {}).get(op_combined)
        if pre_npu_api:
            new_npu_api = f"{pre_npu_api}/{npu_api}"
        getattr(self, f"{mode_str}_op_api_map", {})[op_combined] = new_npu_api
        logger.debug("Output rule: %s: %s: %s: %s ", mode, op_combined, new_npu_api, op_combined.split("-"))

    def _load_yaml(self, file_path):
        """生成timeline规则库"""
        logger.debug("Try to use the following yaml file as timeline ops rule: %s.", os.path.abspath(file_path))
        # 若文件不存在，则报错, 并返回空字典
        if not os.path.exists(file_path):
            logger.warning("Path: '%s' does not exist, please specific existed path of "
                           "fusion operators yaml file by setting env '%s'",
                           os.path.abspath(file_path), Constant.ADVISOR_RULE_PATH)
            self.is_empty = True
            return {}

        logger.debug("The rule yaml file is successfully found in path: %s", os.path.abspath(file_path))

        db_content = FileManager.read_yaml_file(file_path)

        if not self._is_version_supported(db_content):
            self.is_empty = True
            return {}

        logger.debug("The rule library supports the current environment version.")

        # 获取所有版本timeline规则库
        self.timeline_op_rule_handler.set_db_content(db_content)

        # 获取所需版本规则
        unique_id = self._get_unique_id_in_supported_version_dict()
        logger.debug("Program is using version %s of the rule.", unique_id)
        result_op_rule = self.get_fusion_operator_with_unique_id(unique_id)
        if result_op_rule and len(result_op_rule) > 0:
            return result_op_rule

        logger.warning(
            "Failed to load fusion operators database, skip analyze timeline for affinity api,"
            " please refer to database yaml %s to customize your yaml.",
            self.timeline_fusion_ops_yaml_path
        )
        self.is_empty = True
        return {}
