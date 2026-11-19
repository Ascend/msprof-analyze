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

"""Immutable public dataset limits, separate from one operation's mutable counters."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Union

from pt_snap_cli.core.common.errors import InvalidParameterError

DEFAULT_MAX_WORK_ROWS = 100_000
DEFAULT_MAX_WORK_BYTES = 64 * 1024 * 1024
DEFAULT_MAX_SCRATCH_DB_BYTES = 512 * 1024 * 1024
MIN_SCRATCH_DB_BYTES = 4096
MAX_SCRATCH_DB_BYTES = 4 * 1024**3


@dataclass(frozen=True)
class QueryLimits:
    """Dataset work/storage ceilings; never an unlimited-work or RSS setting.

    Rows and bytes must be positive integers. Scratch zero disables the derived
    disk database; otherwise its page ceiling must be between 4096 and 4 GiB.
    This object has no counters or deadline and can safely be reused.
    """

    max_work_rows: int = DEFAULT_MAX_WORK_ROWS
    max_work_bytes: int = DEFAULT_MAX_WORK_BYTES
    max_scratch_db_bytes: int = DEFAULT_MAX_SCRATCH_DB_BYTES

    def __post_init__(self) -> None:
        for name, value in (
            ("max_work_rows", self.max_work_rows),
            ("max_work_bytes", self.max_work_bytes),
        ):
            # pylint: disable-next=unidiomatic-typecheck  # Reject bool/subclasses: the contract requires exact scalar types.
            if type(value) is not int or value <= 0:
                raise InvalidParameterError(f"{name} must be a positive integer; got {value!r}.")
        value = self.max_scratch_db_bytes
        # pylint: disable-next=unidiomatic-typecheck  # Reject bool/subclasses: the contract requires exact scalar types.
        if type(value) is not int or not (value == 0 or MIN_SCRATCH_DB_BYTES <= value <= MAX_SCRATCH_DB_BYTES):
            raise InvalidParameterError(
                "max_scratch_db_bytes must be 0 (disabled) or an integer between "
                f"4096 and {MAX_SCRATCH_DB_BYTES} (4 GiB); got {value!r}."
            )

    @classmethod
    def resolve(
        cls,
        *,
        max_work_rows: Union[int, None] = None,
        max_work_bytes: Union[int, None] = None,
        max_scratch_db_bytes: Union[int, None] = None,
    ) -> QueryLimits:
        """Resolve each field: explicit value > environment > built-in default.

        Environment values are base-10 integers in bytes/rows, without suffixes.
        Missing or blank values use the default; invalid values fail before I/O.
        An explicit field ignores even an invalid corresponding environment value.
        """
        return cls(
            max_work_rows=_resolve_integer(max_work_rows, "PT_SNAP_MAX_WORK_ROWS", DEFAULT_MAX_WORK_ROWS),
            max_work_bytes=_resolve_integer(max_work_bytes, "PT_SNAP_MAX_WORK_BYTES", DEFAULT_MAX_WORK_BYTES),
            max_scratch_db_bytes=_resolve_integer(
                max_scratch_db_bytes,
                "PT_SNAP_MAX_SCRATCH_DB_BYTES",
                DEFAULT_MAX_SCRATCH_DB_BYTES,
            ),
        )


def resolve_query_limits(explicit: Union[QueryLimits, None]) -> QueryLimits:
    if explicit is None:
        return QueryLimits.resolve()
    if not isinstance(explicit, QueryLimits):
        raise InvalidParameterError("query_limits must be a QueryLimits instance or None.")
    return explicit


def _resolve_integer(explicit: Union[int, None], name: str, default: int) -> int:
    if explicit is not None:
        return explicit
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    if re.fullmatch(r"[+-]?[0-9]+", raw.strip()) is None:
        raise InvalidParameterError(f"{name} must be an integer, got {raw!r}.")
    try:
        return int(raw)
    except ValueError as exc:
        raise InvalidParameterError(f"{name} must be an integer, got {raw!r}.") from exc
