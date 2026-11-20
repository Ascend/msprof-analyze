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

"""Enum types for memory events and block states."""

from enum import IntEnum


class EventType(IntEnum):
    """Memory event types for PyTorch snapshot tracking."""

    SEGMENT_MAP = 0
    SEGMENT_UNMAP = 1
    SEGMENT_ALLOC = 2
    SEGMENT_FREE = 3
    ALLOC = 4
    FREE_REQUESTED = 5
    FREE_COMPLETED = 6
    WORKSPACE_SNAPSHOT = 7


class BlockState(IntEnum):
    """Memory block states."""

    INACTIVE = -1
    ACTIVE_PENDING_FREE = 0
    ACTIVE_ALLOCATED = 1
    UNKNOWN = 99
