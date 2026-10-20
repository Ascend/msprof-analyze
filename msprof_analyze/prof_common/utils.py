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

import configparser
from email.utils import parseaddr
from typing import Dict, List
from urllib.parse import urlparse
from decimal import Decimal

from msprof_analyze.prof_common.logger import get_logger
from msprof_analyze.prof_common.path_manager import PathManager

logger = get_logger()


class SafeConfigReader:
    def __init__(self, config_file):
        self._validation_mapping = {'THRESHOLD': self.check_threshold, 'URL': self.check_url, 'EMAIL': self.check_email}
        self._config = configparser.RawConfigParser()
        self.read_config(config_file)

    def read_config(self, path):
        PathManager.check_input_file_path(path)
        PathManager.check_file_size(path)
        self._config.read(path)

    def get_config(self):
        return self._config

    def validate(self, required_sections: Dict = dict):
        for section, keys in required_sections.items():
            if section not in self._config:
                raise ValueError(f"Missing required section: {section}")
            if self._validation_mapping.get(section, None):
                self._validation_mapping.get(section)(section, keys)
            for key in keys:
                if key not in self._config[section]:
                    raise ValueError(f"Missing required key '{key}' in section '{section}'.")

    def check_threshold(self, section, keys: List):
        for key in keys:
            value = convert_to_float(self._config.get(section, key))
            if value < 0 or value > 1:
                raise ValueError(f"Threshold {value} is not between 0 and 1")

    def check_url(self, section, keys: List):
        for key in keys:
            url = self._config.get(section, key)
            parsed_url = urlparse(url)
            if not all([parsed_url.scheme, parsed_url.netloc]):
                raise ValueError(f"url {url} is not valid")

    def check_email(self, section, keys: List):
        for key in keys:
            email = self._config.get(section, key)
            if '@' not in parseaddr(email)[1]:  # parseaddr固定返回一个双元组，无越界风险
                raise ValueError(f"email {email} is not valid")


def convert_to_float(num):
    try:
        return float(num)
    except (ValueError, FloatingPointError):
        logger.error("Can not convert %s to float", num)
    return 0


def convert_to_int(num, default_value=0):
    try:
        return int(num)
    except (ValueError, NameError):
        logger.error("Can not convert %s to int", num)
    return default_value


def compute_ratio(dividend: float, divisor: float):
    if abs(divisor) < 1e-15:
        return 0
    else:
        return round(dividend / divisor, 4)


def convert_ns_to_us(ns_value):
    if ns_value is None:
        return None
    return round(ns_value * 0.001, 3)


def convert_ns_to_us_str(ns_value):
    if ns_value is None:
        return None
    return str(Decimal(ns_value) / Decimal(1000))
