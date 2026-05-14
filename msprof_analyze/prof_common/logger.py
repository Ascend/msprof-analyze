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
import tempfile
import time

from msprof_analyze.prof_common.constant import Constant

_agent_mode = False


def _create_formatter():
    """Create a standard log formatter"""
    return logging.Formatter(
        fmt="[%(asctime)s][%(levelname)s][%(filename)s:%(lineno)d] %(message)s",
        datefmt='%Y-%m-%d %H:%M:%S'
    )


def _get_or_create_file_handler():
    """Get or create a shared file handler for quiet mode logging"""
    root_logger = logging.getLogger()
    for handler in root_logger.handlers:
        if isinstance(handler, logging.FileHandler):
            return handler
    log_file = os.environ.get("MSPROF_ANALYZE_LOG_FILE")
    if not log_file:
        timestamp = int(time.time())
        log_file = os.path.join(tempfile.gettempdir(), f"msprof_analyze_{timestamp}.log")
        os.environ["MSPROF_ANALYZE_LOG_FILE"] = log_file
    handler = logging.FileHandler(log_file, encoding='utf-8')
    handler.setFormatter(_create_formatter())
    return handler


def _configure_agent_mode_logger(logger):
    """Configure logger for agent mode: remove console output and add file handler"""
    handlers_to_remove = [h for h in logger.handlers if isinstance(h, logging.StreamHandler)]
    for handler in handlers_to_remove:
        logger.removeHandler(handler)
    file_handler = _get_or_create_file_handler()
    if file_handler not in logger.handlers:
        logger.addHandler(file_handler)


def set_agent_mode():
    global _agent_mode
    _agent_mode = True
    for name in logging.Logger.manager.loggerDict:
        log = logging.getLogger(name)
        _configure_agent_mode_logger(log)


def is_agent_mode():
    return os.environ.get("AGENT_MODE") is not None


def get_log_level():
    log_level = os.getenv(Constant.MSPROF_ANALYZE_LOG_LEVEL, Constant.DEFAULT_LOG_LEVEL).upper()
    if not hasattr(logging, log_level):
        raise AttributeError(f"module 'logging' has no attribute '{log_level}', "
                             f"supported log level: {', '.join(Constant.SUPPORTED_LOG_LEVEL)}")
    return log_level


def get_logger() -> logging.Logger:
    logger_name = "msprof-analyze"
    if logger_name in logging.Logger.manager.loggerDict:
        logger = logging.getLogger(logger_name)
    else:
        logger = logging.getLogger(logger_name)
        logger.propagate = False
        logger.setLevel(get_log_level())
        handler = logging.StreamHandler()
        handler.setFormatter(_create_formatter())
        logger.addHandler(handler)
    if is_agent_mode():
        _configure_agent_mode_logger(logger)
    return logger
