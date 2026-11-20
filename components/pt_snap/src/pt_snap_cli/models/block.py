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

"""Memory block data model."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Union

if TYPE_CHECKING:
    from pt_snap_cli.models._enums import BlockState


@dataclass
class MemoryBlock:
    """Represents a memory block from PyTorch snapshot."""

    id: int
    address: int
    size: int
    requested_size: int
    state: BlockState
    alloc_event_id: Union[int, None] = None
    free_event_id: Union[int, None] = None

    @property
    def is_historical_block(self) -> bool:
        """Check if this is a historical block (ID < 0)."""
        return self.id < 0

    @property
    def is_active(self) -> bool:
        """Check if this block is still active (not freed)."""
        return self.free_event_id is None or self.free_event_id == -1
