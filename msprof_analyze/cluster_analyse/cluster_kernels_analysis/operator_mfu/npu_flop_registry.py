# Copyright (c) 2025, Huawei Technologies Co., Ltd.
# All rights reserved.
#
# Licensed under the Apache License, Version 2.0  (the "License");
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

import threading
from typing import Callable, Optional

from msprof_analyze.prof_common.logger import get_logger

logger = get_logger()

_npu_flop_registry: dict[str, Callable] = {}


def register_npu_flop(op_name: str):
    def decorator(func: Callable) -> Callable:
        if op_name in _npu_flop_registry:
            raise RuntimeError(f"Duplicate registration for {op_name}")
        _npu_flop_registry[op_name] = func
        return func

    return decorator


def get_flop_func(op_name: str) -> Optional[Callable]:
    if op_name in _npu_flop_registry:
        return _npu_flop_registry[op_name]

    try:
        from torch.utils.flop_counter import flop_registry as torch_flop_registry
        for key, func in torch_flop_registry.items():
            key_name = getattr(key, '__name__', None) or str(key)
            if key_name == op_name:
                return func
    except ImportError:
        pass

    return None


def get_npu_flop_registry() -> dict[str, Callable]:
    return dict(_npu_flop_registry)
