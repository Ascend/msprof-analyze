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

"""Opt-in text summaries; row selection and attribution are left intact."""

from __future__ import annotations

import hashlib
from typing import Dict, List, Union


def summarize_stacks(rows: List[Dict[str, object]], budget: int, layout: Union[str, None]) -> None:
    """Summarize each stack in place using UTF-8 bytes, not model tokens.

    SQL supplies the attribution kind, v2 ID and a representative event before
    display text is shortened. IDs are scoped to the same database/device.
    v1 groups by full text; v2 must never be identified by a text digest.
    """
    for row in rows:
        text = row.get("callstack")
        kind = row["stack_kind"]
        if kind == "captured":
            if layout == "v2":
                row["stack_id"] = f"v2:id:{row['stack_id']}"
            else:
                assert isinstance(text, str)  # nosec B101 # Internal invariant after validation; not an input security check.
                row["stack_id"] = "v1:sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()
        else:
            row["stack_id"] = f"category:{kind}"
        encoded = text.encode("utf-8") if isinstance(text, str) else b""
        row["stack_bytes"] = budget
        row["stack_original_bytes"] = len(encoded)
        row["stack_truncated"] = len(encoded) > budget
        if len(encoded) > budget:
            # Dropping an incomplete final code point preserves valid Unicode.
            # No ellipsis is appended: the flag, not an ambiguous label, marks loss.
            row["callstack"] = encoded[:budget].decode("utf-8", errors="ignore")
