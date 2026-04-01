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
import logging
import os

from msprof_analyze.prof_common.constant import Constant


def get_log_level():
    log_level = os.getenv(Constant.MSPROF_ANALYZE_LOG_LEVEL, Constant.DEFAULT_LOG_LEVEL).upper()
    if not hasattr(logging, log_level):
        raise AttributeError(f"module 'logging' has no attribute '{log_level}', "
                             f"supported log level: {', '.join(Constant.SUPPORTED_LOG_LEVEL)}")
    return log_level


def get_logger() -> logging.Logger:
    logger_name = "msprof-analyze"
    if logger_name in logging.Logger.manager.loggerDict:
        return logging.getLogger(logger_name)

    logger = logging.getLogger(logger_name)
    logger.propagate = False
    logger.setLevel(get_log_level())

    handler = logging.StreamHandler()
    formatter = logging.Formatter(
        fmt="[%(asctime)s][%(levelname)s][%(filename)s:%(lineno)d] %(message)s",
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    return logger
