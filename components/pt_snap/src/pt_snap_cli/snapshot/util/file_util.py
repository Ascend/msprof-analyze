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
文件工具模块

提供文件和目录操作的实用函数，包括 pickle 文件的读写、文件和目录的校验等功能。
"""

import os
import pickle  # nosec B403 # Trusted snapshot format; restricted loader and consent boundary are documented.
from pathlib import Path
from typing import Any, Dict, Union


class UnsafePickleError(pickle.UnpicklingError):
    """Raised when unpickling requests a global outside the builtins allowlist."""


class SafeUnpickler(pickle.Unpickler):
    """Allow only builtins container and scalar types during unpickling."""

    ALLOWED_CLASSES = {
        "builtins": {
            "dict",
            "list",
            "tuple",
            "set",
            "str",
            "int",
            "float",
            "bool",
            "bytes",
        },
    }

    def find_class(self, module: str, name: str):
        if module in self.ALLOWED_CLASSES and name in self.ALLOWED_CLASSES[module]:
            return super().find_class(module, name)
        raise UnsafePickleError(
            f"Unsafe pickle: global '{module}.{name}' is not allowed. "
            "Only basic Python types are permitted for security."
        )


def load_pickle_to_dict(pickle_file: Path) -> Dict[Any, Any]:
    """
    从指定路径加载 pickle 文件，并确保其内容为 dict 类型。

    Args:
        pickle_file (Path): pickle 文件路径

    Returns:
        dict: 加载的字典数据

    Raises:
        FileNotFoundError: 文件不存在
        ValueError: 文件内容不是 dict 类型
        pickle.UnpicklingError: 反序列化失败（文件损坏或非 pickle 格式）
        UnsafePickleError: 请求了 allowlist 之外的全局对象
    """
    if not pickle_file.is_file():
        raise FileNotFoundError(f"Cannot found pickle file: {pickle_file}")

    try:
        with open(pickle_file, "rb") as f:
            data = SafeUnpickler(f).load()
    except UnsafePickleError:
        raise
    except pickle.UnpicklingError as exc:
        raise pickle.UnpicklingError(f"Cannot load pickle file: {pickle_file}: {exc}") from exc
    except Exception:
        # Preserve the established exception context and corrupt-pickle behavior.
        raise pickle.UnpicklingError(f"Cannot load pickle file: {pickle_file}")  # noqa: B904

    if not isinstance(data, dict):
        raise ValueError(f"The content of the pickle file is not of type dict, actual type: {type(data).__name__}")

    return data


def save_dict_to_pickle(data: Dict[Any, Any], path: Path, protocol: int = 4) -> None:
    """
    将字典保存为 pickle 文件。

    Args:
        data (dict): 要保存的字典
        path (Path): 保存路径（会自动创建父目录）
        protocol (int): 保存版本

    Raises:
        TypeError: data 不是 dict 类型
        OSError: 文件写入失败（如权限不足、磁盘满等）
    """
    if not isinstance(data, dict):
        raise TypeError(f"Only dict type is supported, but received: {type(data).__name__}")
    path.parent.mkdir(parents=True, exist_ok=True)  # 自动创建父目录

    try:
        with open(path, "wb") as f:
            pickle.dump(data, f, protocol=protocol)
    except OSError as e:
        raise OSError(f"Unable to write to file {path}: {e}") from e


def check_dir_valid(path: Union[str, Path], need_readable: bool = True, need_writable: bool = True) -> bool:
    """
    校验目录是否合法，默认要求可读可写。

    Args:
        path: 路径字符串或 pathlib.Path 对象
        need_readable: 是否要求可读，默认为 True
        need_writable: 是否要求可写，默认为 True

    Returns:
        bool: 目录是否合法且满足权限要求

    Examples:
        >>> check_dir_valid('/tmp', need_readable=True, need_writable=True)
        True
        >>> check_dir_valid('/nonexistent')
        False
    """
    _path = path if isinstance(path, Path) else Path(path)
    if not _path.is_dir():
        return False
    if need_readable and not os.access(_path, os.R_OK):
        return False
    if need_writable and not os.access(_path, os.W_OK):
        return False
    return True


def check_file_valid(path: Union[str, Path], need_readable: bool = True, need_writable: bool = False) -> bool:
    """
    校验文件是否合法，默认要求可读，不要求可写。

    Args:
        path: 路径字符串或 pathlib.Path 对象
        need_readable: 是否要求可读，默认为 True
        need_writable: 是否要求可写，默认为 False

    Returns:
        bool: 文件是否合法且满足权限要求

    Examples:
        >>> check_file_valid('/etc/passwd', need_readable=True, need_writable=False)
        True
        >>> check_file_valid('/nonexistent.txt')
        False
    """
    _path = path if isinstance(path, Path) else Path(path)
    if not _path.is_file():
        return False
    if need_readable and not os.access(_path, os.R_OK):
        return False
    if need_writable and not os.access(_path, os.W_OK):
        return False
    return True
