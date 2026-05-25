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
from typing import Any, Callable

from msprof_analyze.cluster_analyse.cluster_kernels_analysis.operator_mfu.npu_flop_registry import get_flop_func
from msprof_analyze.prof_common.logger import get_logger

logger = get_logger()

_MFU_FLOPS_DOMAIN = "mfu_flops"


class MFUHookManager:
    _local = threading.local()
    _original_funcs: dict[str, Callable] = {}
    _patched_targets: dict[str, Any] = {}
    _installed = False

    @classmethod
    def install(cls, target_ops: dict[str, tuple[Any, str]]):
        if cls._installed:
            logger.warning("MFUHookManager already installed, skipping")
            return

        for op_name, (module_obj, attr_name) in target_ops.items():
            original = getattr(module_obj, attr_name, None)
            if original is None:
                logger.warning(f"Cannot find {attr_name} in {module_obj}, skipping hook for {op_name}")
                continue

            wrapped = cls._make_wrapper(op_name, original)
            setattr(module_obj, attr_name, wrapped)
            cls._original_funcs[op_name] = original
            cls._patched_targets[op_name] = (module_obj, attr_name)

        cls._installed = True
        logger.info(f"MFUHookManager installed, hooked ops: {list(cls._patched_targets.keys())}")

    @classmethod
    def uninstall(cls):
        if not cls._installed:
            return

        for op_name, (module_obj, attr_name) in cls._patched_targets.items():
            original = cls._original_funcs.get(op_name)
            if original is not None:
                setattr(module_obj, attr_name, original)

        cls._original_funcs.clear()
        cls._patched_targets.clear()
        cls._installed = False
        logger.info("MFUHookManager uninstalled")

    @classmethod
    def is_installed(cls) -> bool:
        return cls._installed

    @classmethod
    def _make_wrapper(cls, op_name: str, original_func: Callable) -> Callable:
        def wrapper(*args, **kwargs):
            if getattr(cls._local, 'in_hook', False):
                return original_func(*args, **kwargs)

            cls._local.in_hook = True
            try:
                result = original_func(*args, **kwargs)
                cls._record_flops(op_name, args, kwargs)
                return result
            finally:
                cls._local.in_hook = False

        wrapper.__name__ = f"mfu_hooked_{op_name}"
        wrapper.__qualname__ = f"mfu_hooked_{op_name}"
        wrapper.__wrapped__ = original_func
        return wrapper

    @classmethod
    def _record_flops(cls, op_name: str, args: tuple, kwargs: dict):
        flop_func = get_flop_func(op_name)
        if flop_func is None:
            logger.warning(f"No FLOPs formula registered for operator: {op_name}")
            return

        try:
            flops = flop_func(*args, **kwargs)
            if flops is not None and flops >= 0:
                cls._write_mstx_mark(flops)
            else:
                logger.warning(f"FLOPs formula for {op_name} returned invalid value: {flops}")
        except Exception as e:
            logger.warning(f"Failed to compute FLOPs for {op_name}: {e}")

    @classmethod
    def _write_mstx_mark(cls, flops: int):
        try:
            import torch_npu
            torch_npu.npu.mstx.mark(message=str(flops), domain=_MFU_FLOPS_DOMAIN)
        except ImportError:
            logger.warning("torch_npu not available, cannot write mstx mark")
        except Exception as e:
            logger.warning(f"Failed to write mstx mark: {e}")
