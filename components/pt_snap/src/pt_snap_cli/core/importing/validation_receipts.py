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

"""Disposable, content-addressed validation receipts for repeated imports.

Receipts live outside datasets. They never substitute file timestamps for byte
hashes, and are only consulted inside an import operation. Bump VERSION whenever
the validation semantics change, independently of the package version.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path
from typing import Dict, Iterator, Union

from pt_snap_cli._compat import unlink_missing_ok

VERSION = 1
_ENABLED: ContextVar[bool] = ContextVar("import_validation_receipts", default=False)


@contextmanager
def import_receipts() -> Iterator[None]:
    token = _ENABLED.set(True)
    try:
        yield
    finally:
        _ENABLED.reset(token)


def _path(root: Path, scope: str) -> Union[Path, None]:
    if not receipts_enabled():
        return None
    key = hashlib.sha256(str(root).encode("utf-8")).hexdigest()
    try:
        return Path.home() / ".cache" / "pt-snap-cli" / f"validation-v{VERSION}" / f"{key}-{scope}.json"
    except (OSError, RuntimeError):
        return None


def import_validation_active() -> bool:
    """Import admission policy is independent of receipt/cache configuration."""
    return _ENABLED.get()


def receipts_enabled() -> bool:
    return _ENABLED.get() and os.environ.get("PT_SNAP_DATASET_CACHE") is None


def _encoded(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def load_receipt(root: Path, scope: str, fingerprint: str) -> Union[Dict[str, object], None]:
    path = _path(root, scope)
    if path is None:
        return None
    try:
        if path.is_symlink() or path.stat().st_size > 4096:
            return None
        envelope = json.loads(path.read_bytes())
        data = envelope["data"]
        if (
            envelope["sha256"] != hashlib.sha256(_encoded(data)).hexdigest()
            or data["fingerprint"] != fingerprint
            or not isinstance(data["payload"], dict)
        ):
            return None
        return data["payload"]
    except (OSError, ValueError, KeyError, TypeError, RecursionError):
        return None


def save_receipt(root: Path, scope: str, fingerprint: str, payload: Dict[str, object]) -> None:
    path = _path(root, scope)
    if path is None:
        return
    temporary: Union[Path, None] = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {"fingerprint": fingerprint, "payload": payload}
        raw = _encoded({"data": data, "sha256": hashlib.sha256(_encoded(data)).hexdigest()})
        # One bounded record per dataset/scope, atomically replaced on change.
        with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as file:
            temporary = Path(file.name)
            file.write(raw)
        os.replace(temporary, path)
    except OSError:
        # Read-only homes, full disks and stale receipts affect speed, not validity.
        pass
    finally:
        if temporary is not None:
            try:
                unlink_missing_ok(temporary)
            except OSError:
                pass
