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

import os
import threading
from functools import partial
from concurrent import futures
from collections import defaultdict

from msprof_analyze.prof_common.additional_args_manager import AdditionalArgsManager
from msprof_analyze.prof_common.constant import Constant
from msprof_analyze.prof_common.logger import get_logger, set_agent_mode, is_agent_mode

logger = get_logger()


class Context:
    """abstract base class"""

    ctx_map = None
    _mode = "base"

    def __init__(self):
        logger.info("context %s initialized.", self._mode)
        self._lock = threading.RLock()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        if exc_type is not None:
            logger.error("Failed to exit context: %s", exc_val)

    @classmethod
    def create_context(cls, mode=Constant.CONCURRENT_MODE):
        if cls.ctx_map is None:
            keys = [Constant.CONCURRENT_MODE]
            values = [ConcurrentContext]
            cls.ctx_map = dict(zip(keys, values))

        if mode not in cls.ctx_map:
            raise NotImplementedError("mode must be in {}".format(keys))

        return cls.ctx_map[mode]()

    def launch(self, func, *args, **kwargs):
        raise NotImplementedError

    def map(self, func, *iterables, **kwargs):
        raise NotImplementedError

    def wait(self, waitable):
        raise NotImplementedError

    def close(self):
        """release resources, implemented in subclasses"""


def init_subprocess(config_dict):
    AdditionalArgsManager().init(config_dict)
    if is_agent_mode():
        set_agent_mode()


class ConcurrentContext(Context):
    def __init__(self, executor=None):
        self._mode = Constant.CONCURRENT_MODE
        super().__init__()
        self._custom = executor is None
        config = {
            "force": AdditionalArgsManager().force,
        }
        self._executor = executor or futures.ProcessPoolExecutor(
            max_workers=os.cpu_count(), initializer=init_subprocess, initargs=(config,)
        )
        self.future_dict = defaultdict(list)

    def __enter__(self):
        if self._executor is None:
            raise RuntimeError("executor is None")
        return self

    def close(self):
        if self._custom:
            self._executor.shutdown(wait=True)
            self._executor = None

    def launch(self, func, *args, **kwargs):
        return self._executor.submit(func, *args, **kwargs).result()

    def map(self, func, *iterables, **kwargs):
        partial_func = partial(func, **kwargs)
        try:
            res = list(self._executor.map(partial_func, *iterables))
        except Exception as err:
            logger.error(err)
            return []
        return res

    def wait(self, waitable):
        return waitable

    def submit(self, name, func, *args, **kwargs):
        with self._lock:
            self.future_dict[name].append(self._executor.submit(func, *args, **kwargs))

    def wait_all_futures(self):
        for _, future_list in self.future_dict.items():
            for future in future_list:
                future.result()
