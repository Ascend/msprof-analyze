#!/usr/bin/env python3
"""
MFU Hook 安装脚本 - 用于在 vllm-ascend 推理进程中安装 MFU FLOPs 采集 hooks

使用方式:
  方式一: 作为 Python 模块导入后调用
    from mfu_hook_bootstrap import install_mfu, uninstall_mfu
    install_mfu()

  方式二: 通过 sitecustomize.py 自动加载
    将本文件放到 Python 的 site-packages 目录，
    然后在 sitecustomize.py 中添加:
      import mfu_hook_bootstrap

  方式三: 通过环境变量 PYTHONSTARTUP (仅交互模式)

  方式四: 直接在 vllm 启动脚本中 import
    python -c "import mfu_hook_bootstrap; mfu_hook_bootstrap.install_mfu()" && \
    vllm serve ...

环境变量:
  MFU_RECORD: 控制是否启用 MFU 采集 (默认: "1" 即启用)
              设为 "0" 或 "false" 或 "off" 可禁用
  MSPROF_ANALYZE_LOG_LEVEL: 日志级别 (默认: "INFO")
                             设为 "DEBUG" 可查看详细日志
"""

import os
import sys
import logging

_MFU_BOOTSTRAP_LOG_FMT = "[%(asctime)s][%(levelname)s][MFU-BOOT] %(message)s"


def _setup_bootstrap_logger():
    logger = logging.getLogger("mfu-bootstrap")
    if logger.handlers:
        return logger
    logger.setLevel(logging.DEBUG)
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter(_MFU_BOOTSTRAP_LOG_FMT, datefmt='%Y-%m-%d %H:%M:%S'))
    log_level = os.environ.get("MSPROF_ANALYZE_LOG_LEVEL", "INFO").upper()
    handler.setLevel(getattr(logging, log_level, logging.INFO))
    logger.addHandler(handler)
    logger.propagate = False
    return logger


_bootstrap_logger = _setup_bootstrap_logger()


def install_mfu():
    _bootstrap_logger.info("=" * 60)
    _bootstrap_logger.info("MFU Hook Bootstrap - install_mfu() called")
    _bootstrap_logger.info(f"Python: {sys.executable} ({sys.version})")
    _bootstrap_logger.info(f"PID: {os.getpid()}")
    _bootstrap_logger.info(f"CWD: {os.getcwd()}")
    _bootstrap_logger.info(f"MFU_RECORD env: {os.environ.get('MFU_RECORD', '(not set, default=1)')}")
    _bootstrap_logger.info(f"MSPROF_ANALYZE_LOG_LEVEL: {os.environ.get('MSPROF_ANALYZE_LOG_LEVEL', '(not set)')}")
    _bootstrap_logger.info("=" * 60)

    try:
        from msprof_analyze.cluster_analyse.cluster_kernels_analysis.operator_mfu import (
            install_mfu_hooks,
            is_mfu_enabled,
        )
        _bootstrap_logger.info(f"msprof-analyze imported successfully, MFU enabled={is_mfu_enabled()}")
    except ImportError as e:
        _bootstrap_logger.error(f"Failed to import msprof-analyze: {e}")
        _bootstrap_logger.error("Make sure msprof-analyze is installed: pip install msprof-analyze")
        return False

    if not is_mfu_enabled():
        _bootstrap_logger.info("MFU recording is disabled by MFU_RECORD env var, skipping")
        return True

    try:
        install_mfu_hooks()
        _bootstrap_logger.info("MFU hooks installed successfully")
    except Exception as e:
        _bootstrap_logger.error(f"Failed to install MFU hooks: {e}")
        import traceback
        _bootstrap_logger.error(traceback.format_exc())
        return False

    try:
        from msprof_analyze.cluster_analyse.cluster_kernels_analysis.operator_mfu.mfu_hook_manager import MFUHookManager
        if MFUHookManager.is_installed():
            _bootstrap_logger.info("MFUHookManager is installed and active")
        else:
            _bootstrap_logger.warning("MFUHookManager.install() was called but is_installed() returns False")
    except Exception as e:
        _bootstrap_logger.warning(f"Could not verify MFUHookManager status: {e}")

    return True


def uninstall_mfu():
    _bootstrap_logger.info("MFU Hook Bootstrap - uninstall_mfu() called")
    try:
        from msprof_analyze.cluster_analyse.cluster_kernels_analysis.operator_mfu import uninstall_mfu_hooks
        uninstall_mfu_hooks()
        _bootstrap_logger.info("MFU hooks uninstalled successfully")
    except ImportError as e:
        _bootstrap_logger.error(f"Failed to import msprof-analyze: {e}")
    except Exception as e:
        _bootstrap_logger.error(f"Failed to uninstall MFU hooks: {e}")


def check_environment():
    _bootstrap_logger.info("Checking MFU environment...")

    try:
        import torch_npu
        _bootstrap_logger.info(f"torch_npu: available, version={getattr(torch_npu, '__version__', 'unknown')}")
    except ImportError:
        _bootstrap_logger.warning("torch_npu: NOT available. MFU hooks require torch_npu for mstx APIs.")

    try:
        import torch
        _bootstrap_logger.info(f"torch: version={torch.__version__}")
    except ImportError:
        _bootstrap_logger.warning("torch: NOT available")

    try:
        import msprof_analyze
        _bootstrap_logger.info(f"msprof-analyze: version={getattr(msprof_analyze, '__version__', 'unknown')}")
    except ImportError:
        _bootstrap_logger.warning("msprof-analyze: NOT available")

    try:
        from msprof_analyze.cluster_analyse.cluster_kernels_analysis.operator_mfu.npu_flop_registry import (
            get_npu_flop_registry,
            get_npu_flop_targets,
        )
        registry = get_npu_flop_registry()
        targets = get_npu_flop_targets()
        _bootstrap_logger.info(f"FLOPs registry: {len(registry)} formulas registered")
        for name, func in registry.items():
            _bootstrap_logger.info(f"  - {name}: {func.__name__}")
        _bootstrap_logger.info(f"FLOPs hook targets: {targets}")
    except ImportError as e:
        _bootstrap_logger.warning(f"Cannot check FLOPs registry: {e}")

    try:
        import torch_npu
        if hasattr(torch_npu, 'npu') and hasattr(torch_npu.npu, 'mstx'):
            mstx = torch_npu.npu.mstx
            _bootstrap_logger.info(f"mstx API available: range_start={hasattr(mstx, 'range_start')}, "
                                   f"range_end={hasattr(mstx, 'range_end')}, "
                                   f"mark={hasattr(mstx, 'mark')}")
        else:
            _bootstrap_logger.warning("torch_npu.npu.mstx NOT available. "
                                     "MFU FLOPs recording requires mstx.range_start/range_end.")
    except ImportError:
        pass


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="MFU Hook Bootstrap Tool")
    parser.add_argument("action", choices=["install", "uninstall", "check"],
                        help="Action to perform")
    args = parser.parse_args()

    if args.action == "install":
        install_mfu()
    elif args.action == "uninstall":
        uninstall_mfu()
    elif args.action == "check":
        check_environment()
