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

_npu_flop_registry: dict[str, tuple[Callable, bool, Optional[str]]] = {}


def register_npu_flop(target: Optional[str] = None, op_name: Optional[str] = None, is_default: bool = True):
    def decorator(func: Callable) -> Callable:
        resolved_name = op_name
        if resolved_name is None:
            if target is not None and ':' in target:
                resolved_name = target.split(':', 1)[1]
            else:
                resolved_name = func.__name__

        if resolved_name in _npu_flop_registry:
            existing_func, existing_is_default, existing_target = _npu_flop_registry[resolved_name]
            if is_default:
                logger.debug(f"[MFU] FLOPs registration skipped (default): {resolved_name}, "
                             f"existing target={existing_target}")
            else:
                if not existing_is_default:
                    logger.warning(f"[MFU] Overriding non-default FLOPs registration for {resolved_name}")
                _npu_flop_registry[resolved_name] = (func, is_default, target)
                logger.info(f"[MFU] FLOPs registered (override): {resolved_name} -> "
                            f"func={func.__name__}, target={target}")
        else:
            _npu_flop_registry[resolved_name] = (func, is_default, target)
            logger.info(f"[MFU] FLOPs registered: {resolved_name} -> "
                        f"func={func.__name__}, target={target}, is_default={is_default}")
        return func

    return decorator


def get_flop_func(op_name: str) -> Optional[Callable]:
    if op_name in _npu_flop_registry:
        func = _npu_flop_registry[op_name][0]
        logger.debug(f"[MFU] FLOPs formula found in npu registry: {op_name} -> {func.__name__}")
        return func

    try:
        from torch.utils.flop_counter import flop_registry as torch_flop_registry
        for key, func in torch_flop_registry.items():
            key_name = getattr(key, '__name__', None) or str(key)
            if key_name == op_name:
                logger.debug(f"[MFU] FLOPs formula found in torch registry: {op_name} -> {func}")
                return func
    except ImportError:
        logger.debug("[MFU] torch.utils.flop_counter not available for fallback lookup")

    logger.debug(f"[MFU] No FLOPs formula found for: {op_name}")
    return None


def get_npu_flop_registry() -> dict[str, Callable]:
    return {name: entry[0] for name, entry in _npu_flop_registry.items()}


def get_npu_flop_targets() -> dict[str, str]:
    return {name: entry[2] for name, entry in _npu_flop_registry.items() if entry[2] is not None}
