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

"""
计时器工具模块

提供函数执行时间测量的装饰器。
"""

import logging
import time
from functools import wraps
from typing import Any, Callable, Union


def timer(name: Union[str, None] = None, logger: Union[logging.Logger, None] = None):
    """
    函数执行时间计时装饰器。

    用于测量函数执行时间并输出结果。可以选择输出到 logger 或控制台。

    Args:
        name: 计时器名称，默认使用函数名
        logger: 日志记录器，如果提供则使用 logger.info 输出，否则使用 print

    Returns:
        Callable: 装饰器函数

    Examples:
        >>> from ..util import get_logger
        >>> logger = get_logger(__name__)

        >>> @timer()
        ... def slow_function():
        ...     time.sleep(1)
        slow_function took 1.0012 seconds

        >>> @timer(name="数据处理", logger=logger)
        ... def process_data():
        ...     time.sleep(0.5)
        2024-01-01 12:00:00 [ INFO ][ __main__ ]: 数据处理 took 0.5023 seconds
    """

    def decorator(func: Callable[..., Any]):
        _name = func.__name__ if not name else name

        @wraps(func)
        def wrapper(*args, **kwargs):
            start = time.perf_counter()
            result = func(*args, **kwargs)
            end = time.perf_counter()
            info = f"{_name} took {end - start:.4f} seconds"
            if logger:
                logger.info(info)
            else:
                print(info)
            return result

        return wrapper

    return decorator
