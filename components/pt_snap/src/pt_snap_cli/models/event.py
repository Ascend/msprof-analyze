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

"""Memory event data model."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Union

if TYPE_CHECKING:
    from pt_snap_cli.models._enums import EventType


@dataclass
class MemoryEvent:
    """Represents a memory event from PyTorch snapshot."""

    id: int
    action: EventType
    address: int
    size: int
    stream: int
    allocated: int
    active: int
    reserved: int
    callstack: Union[str, None] = None

    @property
    def is_virtual_event(self) -> bool:
        """Check if this is a virtual event (ID < 0)."""
        return self.id < 0

    @property
    def is_runtime_event(self) -> bool:
        """Check if this is a runtime event (ID >= 0)."""
        return self.id >= 0
