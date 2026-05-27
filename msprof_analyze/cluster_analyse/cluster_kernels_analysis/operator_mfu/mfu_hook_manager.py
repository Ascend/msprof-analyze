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

import importlib
import json
import os
import sys
import threading
import time
import traceback
from typing import Any, Callable, Optional

from msprof_analyze.cluster_analyse.cluster_kernels_analysis.operator_mfu.npu_flop_registry import (
    get_flop_func,
    get_npu_flop_targets,
)
from msprof_analyze.prof_common.logger import get_logger

logger = get_logger()

_MFU_FLOPS_DOMAIN = "mfu_flops"
_MFU_RECORD_ENV = "MFU_RECORD"
_MFU_OUTPUT_DIR_ENV = "MFU_OUTPUT_DIR"
_MFU_OUTPUT_FILE = "mfu_flops_data.json"


def is_mfu_enabled() -> bool:
    val = os.environ.get(_MFU_RECORD_ENV, "1")
    enabled = val.strip().lower() not in ("0", "false", "off", "no")
    logger.info(f"[MFU] Switch check: env {_MFU_RECORD_ENV}={val!r}, enabled={enabled}")
    return enabled


def _resolve_target(target: str):
    if ':' not in target:
        logger.warning(f"[MFU] Invalid target format '{target}', expected 'module.path:attr.path'")
        return None, None

    module_path, attr_path = target.split(':', 1)

    try:
        module_obj = importlib.import_module(module_path)
        logger.debug(f"[MFU] Resolved target module: {module_path}")
    except ImportError as e:
        logger.warning(f"[MFU] Cannot import module '{module_path}': {e}")
        return None, None

    obj = module_obj
    attrs = attr_path.split('.')
    for i, attr in enumerate(attrs):
        if not hasattr(obj, attr):
            traversed = '.'.join(attrs[:i])
            logger.warning(f"[MFU] '{traversed}' has no attribute '{attr}' in target '{target}'")
            return None, None
        obj = getattr(obj, attr)

    parent = module_obj
    for attr in attrs[:-1]:
        parent = getattr(parent, attr)

    logger.debug(f"[MFU] Resolved target '{target}' -> parent={parent}, attr={attrs[-1]}")
    return parent, attrs[-1]


def _build_target_ops_from_registry() -> dict[str, tuple[Any, str]]:
    targets = get_npu_flop_targets()
    if not targets:
        logger.warning("[MFU] No NPU FLOPs targets registered, nothing to hook")
        return {}

    logger.info(f"[MFU] Building target ops from registry: {list(targets.keys())}")
    target_ops = {}
    for op_name, target in targets.items():
        parent, attr_name = _resolve_target(target)
        if parent is not None and attr_name is not None:
            target_ops[op_name] = (parent, attr_name)
            logger.info(f"[MFU] Target resolved: {op_name} -> {target}")
        else:
            logger.warning(f"[MFU] Target resolve failed: {op_name} -> {target}")

    return target_ops


def _find_existing_refs(original_func: Callable, attr_name: str):
    refs = []
    for mod_name, mod in sys.modules.items():
        if mod is None:
            continue
        try:
            ref = getattr(mod, attr_name, None)
        except Exception:
            continue
        if ref is original_func:
            refs.append((mod, attr_name))
    if refs:
        logger.debug(f"[MFU] Found {len(refs)} existing refs for '{attr_name}': "
                     f"{[(m.__name__ if hasattr(m, '__name__') else str(m), a) for m, a in refs]}")
    return refs


class MFUHookManager:
    _local = threading.local()
    _original_funcs: dict[str, Callable] = {}
    _patched_targets: dict[str, Any] = {}
    _extra_refs: dict[str, list[tuple[Any, str]]] = {}
    _installed = False
    _hook_call_count: dict[str, int] = {}
    _flops_records: list[dict] = []
    _flops_lock = threading.Lock()
    _flops_total: dict[str, int] = {}

    @classmethod
    def install(cls, target_ops: Optional[dict[str, tuple[Any, str]]] = None):
        logger.info("[MFU] MFUHookManager.install() called")
        if cls._installed:
            logger.warning("[MFU] MFUHookManager already installed, skipping")
            return

        if not is_mfu_enabled():
            logger.info("[MFU] MFU recording is disabled by env switch, install skipped")
            return

        if target_ops is None:
            target_ops = _build_target_ops_from_registry()

        if not target_ops:
            logger.warning("[MFU] No target ops to hook, install skipped")
            return

        logger.info(f"[MFU] Installing hooks for {len(target_ops)} operators: {list(target_ops.keys())}")

        for op_name, (module_obj, attr_name) in target_ops.items():
            original = getattr(module_obj, attr_name, None)
            if original is None:
                logger.warning(f"[MFU] Cannot find {attr_name} in {module_obj}, skipping hook for {op_name}")
                continue

            logger.info(f"[MFU] Hooking {op_name}: {module_obj}.{attr_name} "
                        f"(original={original}, id={id(original)})")
            wrapped = cls._make_wrapper(op_name, original)
            setattr(module_obj, attr_name, wrapped)
            cls._original_funcs[op_name] = original
            cls._patched_targets[op_name] = (module_obj, attr_name)
            cls._hook_call_count[op_name] = 0

            extra = _find_existing_refs(original, attr_name)
            cls._extra_refs[op_name] = []
            for ref_mod, ref_attr in extra:
                if ref_mod is module_obj and ref_attr == attr_name:
                    continue
                setattr(ref_mod, ref_attr, wrapped)
                cls._extra_refs[op_name].append((ref_mod, ref_attr))
                logger.info(f"[MFU] Patched extra ref: {ref_mod}.{ref_attr} for {op_name}")

            if hasattr(original, 'out') and callable(original.out):
                out_op_name = f"{op_name}__out"
                original_out = original.out
                logger.info(f"[MFU] Hooking {out_op_name}: {module_obj}.{attr_name}.out "
                            f"(original_out={original_out}, id={id(original_out)})")
                wrapped_out = cls._make_wrapper(op_name, original_out)
                setattr(original, 'out', wrapped_out)
                cls._original_funcs[out_op_name] = original_out
                cls._patched_targets[out_op_name] = (original, 'out')
                cls._hook_call_count[out_op_name] = 0
                logger.info(f"[MFU] Hooked .out variant for {op_name}")

        cls._installed = True
        hooked = list(cls._patched_targets.keys())
        extra_count = sum(len(v) for v in cls._extra_refs.values())
        logger.info(f"[MFU] MFUHookManager installed successfully, "
                    f"hooked ops: {hooked}, extra refs patched: {extra_count}")

    @classmethod
    def install_from_env(cls):
        logger.info("[MFU] MFUHookManager.install_from_env() called")
        if not is_mfu_enabled():
            logger.info("[MFU] MFU recording is disabled, skipping hook installation")
            return
        cls.install()

    @classmethod
    def uninstall(cls):
        logger.info("[MFU] MFUHookManager.uninstall() called")
        if not cls._installed:
            logger.info("[MFU] Not installed, nothing to uninstall")
            return

        try:
            cls.flush_flops_to_file()
        except Exception as e:
            logger.warning(f"[MFU] Failed to flush FLOPs data on uninstall: {e}")

        for op_name, (module_obj, attr_name) in cls._patched_targets.items():
            original = cls._original_funcs.get(op_name)
            if original is not None:
                setattr(module_obj, attr_name, original)
                logger.debug(f"[MFU] Restored {op_name}: {module_obj}.{attr_name}")

        for op_name, refs in cls._extra_refs.items():
            original = cls._original_funcs.get(op_name)
            if original is not None:
                for ref_mod, ref_attr in refs:
                    setattr(ref_mod, ref_attr, original)

        call_summary = {op: cnt for op, cnt in cls._hook_call_count.items() if cnt > 0}
        flops_summary = dict(cls._flops_total)
        cls._original_funcs.clear()
        cls._patched_targets.clear()
        cls._extra_refs.clear()
        cls._hook_call_count.clear()
        cls._flops_records.clear()
        cls._flops_total.clear()
        cls._installed = False
        logger.info(f"[MFU] MFUHookManager uninstalled. Hook call summary: {call_summary}, "
                    f"FLOPs summary: {flops_summary}")

    @classmethod
    def is_installed(cls) -> bool:
        return cls._installed

    @classmethod
    def _make_wrapper(cls, op_name: str, original_func: Callable) -> Callable:
        def wrapper(*args, **kwargs):
            if getattr(cls._local, 'in_hook', False):
                return original_func(*args, **kwargs)

            cls._local.in_hook = True
            flops = None
            rf_ctx = None
            try:
                flop_func = get_flop_func(op_name)
                if flop_func is not None:
                    try:
                        flops = flop_func(*args, **kwargs)
                        if flops is not None and flops >= 0:
                            logger.debug(f"[MFU] {op_name}: computed FLOPs={flops}")
                            rf_ctx = cls._enter_record_function(flops, op_name)
                            cls._record_flops(op_name, flops, args, kwargs)
                    except Exception as e:
                        logger.warning(f"[MFU] {op_name}: Failed to compute FLOPs: {e}\n"
                                       f"{traceback.format_exc()}")
                else:
                    logger.warning(f"[MFU] {op_name}: No FLOPs formula registered")

                result = original_func(*args, **kwargs)

                cls._hook_call_count[op_name] = cls._hook_call_count.get(op_name, 0) + 1
                call_count = cls._hook_call_count[op_name]
                if call_count <= 5 or call_count % 100 == 0:
                    logger.info(f"[MFU] {op_name}: hook called (count={call_count}), "
                                f"FLOPs={flops}")

                return result
            finally:
                if rf_ctx is not None:
                    cls._exit_record_function(rf_ctx, op_name)
                cls._local.in_hook = False

        wrapper.__name__ = f"mfu_hooked_{op_name}"
        wrapper.__qualname__ = f"mfu_hooked_{op_name}"
        wrapper.__wrapped__ = original_func
        return wrapper

    @classmethod
    def _record_flops(cls, op_name: str, flops: int, args: tuple, kwargs: dict):
        try:
            shapes = []
            for a in args:
                if hasattr(a, 'shape'):
                    shapes.append(list(a.shape))
                elif isinstance(a, (list, tuple)):
                    shapes.append(str(a)[:100])
            record = {
                "op_name": op_name,
                "flops": flops,
                "timestamp": time.time(),
                "shapes": shapes,
            }
            with cls._flops_lock:
                cls._flops_records.append(record)
                cls._flops_total[op_name] = cls._flops_total.get(op_name, 0) + flops
            logger.debug(f"[MFU] Recorded FLOPs: {op_name}={flops}, total={cls._flops_total[op_name]}")
        except Exception as e:
            logger.debug(f"[MFU] Failed to record FLOPs: {e}")

    @classmethod
    def get_flops_summary(cls) -> dict:
        with cls._flops_lock:
            return {
                "total_flops_by_op": dict(cls._flops_total),
                "total_flops": sum(cls._flops_total.values()),
                "call_count_by_op": dict(cls._hook_call_count),
                "total_calls": sum(cls._hook_call_count.values()),
                "record_count": len(cls._flops_records),
            }

    @classmethod
    def flush_flops_to_file(cls, output_dir: str = ""):
        if not output_dir:
            output_dir = os.environ.get(_MFU_OUTPUT_DIR_ENV, "/workspace")
        os.makedirs(output_dir, exist_ok=True)
        pid = os.getpid()
        output_path = os.path.join(output_dir, f"mfu_flops_data_pid{pid}.json")
        with cls._flops_lock:
            data = {
                "mfu_flops_data": cls._flops_records,
                "summary": {
                    "pid": pid,
                    "total_flops_by_op": dict(cls._flops_total),
                    "total_flops": sum(cls._flops_total.values()),
                    "call_count_by_op": dict(cls._hook_call_count),
                    "total_calls": sum(cls._hook_call_count.values()),
                },
            }
        with open(output_path, 'w') as f:
            json.dump(data, f, indent=2)
        logger.info(f"[MFU] FLOPs data flushed to {output_path}, "
                    f"total_flops={data['summary']['total_flops']}, "
                    f"total_calls={data['summary']['total_calls']}")
        return output_path

    @classmethod
    def _enter_record_function(cls, flops: int, op_name: str = ""):
        label = f"{_MFU_FLOPS_DOMAIN}:{flops}:{op_name}"
        try:
            import torch_npu
            stream = torch_npu.npu.current_stream()
            range_id = torch_npu.npu.mstx.range_start(label, stream)
            logger.info(f"[MFU] mstx.range_start: {label}, range_id={range_id}")
            return ("mstx", range_id)
        except ImportError:
            logger.info("[MFU] torch_npu.npu.mstx not available, trying mstx")
        except Exception as e:
            logger.info(f"[MFU] torch_npu.npu.mstx.range_start failed: {e}")
        try:
            import mstx
            range_id = mstx.range_start(label)
            logger.info(f"[MFU] mstx.range_start (fallback): {label}, range_id={range_id}")
            return ("mstx_raw", range_id)
        except ImportError:
            logger.info("[MFU] mstx not available, trying torch.profiler")
        except Exception as e:
            logger.info(f"[MFU] mstx.range_start failed: {e}")
        try:
            import torch.profiler
            ctx = torch.profiler.record_function(label)
            ctx.__enter__()
            logger.info(f"[MFU] record_function enter: {label}")
            return ("torch", ctx)
        except Exception as e:
            logger.info(f"[MFU] torch.profiler.record_function not available: {e}")
            return None

    @classmethod
    def _exit_record_function(cls, ctx, op_name: str = ""):
        if ctx is None:
            return
        try:
            ctx_type, ctx_obj = ctx
            if ctx_type == "mstx":
                import torch_npu
                torch_npu.npu.mstx.range_end(ctx_obj)
                logger.info(f"[MFU] mstx.range_end: {op_name}")
            elif ctx_type == "mstx_raw":
                import mstx
                mstx.range_end(ctx_obj)
                logger.info(f"[MFU] mstx.range_end (fallback): {op_name}")
            elif ctx_type == "torch":
                ctx_obj.__exit__(None, None, None)
                logger.info(f"[MFU] record_function exit: {op_name}")
        except Exception as e:
            logger.info(f"[MFU] record_function exit failed for {op_name}: {e}")
