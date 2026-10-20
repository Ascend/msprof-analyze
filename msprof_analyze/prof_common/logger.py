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
import logging
import os
import tempfile
import time

from msprof_analyze.prof_common.constant import Constant

_agent_mode = False


def _create_formatter():
    """Create a standard log formatter"""
    return logging.Formatter(
        fmt="[%(asctime)s][%(levelname)s][%(filename)s:%(lineno)d] %(message)s", datefmt='%Y-%m-%d %H:%M:%S'
    )


def _get_or_create_file_handler():
    """Get or create a shared file handler for quiet mode logging"""
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
        raise AttributeError(
            f"module 'logging' has no attribute '{log_level}', "
            f"supported log level: {', '.join(Constant.SUPPORTED_LOG_LEVEL)}"
        )
    return log_level


def set_debug_mode(ctx, param, debug_mode):
    if not debug_mode:
        return
    logger = logging.getLogger("msprof-analyze")
    logger.setLevel(logging.DEBUG)
    for handler in logger.handlers:
        handler.setLevel(logging.DEBUG)


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
