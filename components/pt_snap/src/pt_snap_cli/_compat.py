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

"""Small runtime shims for the host's Python 3.7 minimum."""

from itertools import zip_longest
from pathlib import Path
from typing import Iterable, Iterator, Tuple, TypeVar, cast

_T = TypeVar("_T")
_U = TypeVar("_U")


def zip_strict(first: Iterable[_T], second: Iterable[_U]) -> Iterator[Tuple[_T, _U]]:
    """Zip lazily and reject mismatched lengths rather than dropping values."""
    missing = object()
    for left, right in zip_longest(first, second, fillvalue=missing):
        if left is missing or right is missing:
            raise ValueError("zip() arguments have different lengths")
        yield cast(_T, left), cast(_U, right)


def unlink_missing_ok(path: Path) -> None:
    """Ignore a missing file, preserving all other filesystem failures."""
    try:
        path.unlink()
    except FileNotFoundError:
        pass
