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

"""Tests for enum types."""

from pt_snap_cli.models._enums import BlockState, EventType


class TestEventType:
    """Test EventType enum."""

    def test_event_type_values(self) -> None:
        """Test EventType enum values are correct."""
        assert EventType.SEGMENT_MAP == 0
        assert EventType.SEGMENT_UNMAP == 1
        assert EventType.SEGMENT_ALLOC == 2
        assert EventType.SEGMENT_FREE == 3
        assert EventType.ALLOC == 4
        assert EventType.FREE_REQUESTED == 5
        assert EventType.FREE_COMPLETED == 6
        assert EventType.WORKSPACE_SNAPSHOT == 7

    def test_event_type_int_conversion(self) -> None:
        """Test EventType can be converted to int."""
        assert int(EventType.ALLOC) == 4
        assert EventType(4) == EventType.ALLOC

    def test_event_type_from_int(self) -> None:
        """Test creating EventType from integer."""
        event_type = EventType(0)
        assert event_type == EventType.SEGMENT_MAP


class TestBlockState:
    """Test BlockState enum."""

    def test_block_state_values(self) -> None:
        """Test BlockState enum values are correct."""
        assert BlockState.INACTIVE == -1
        assert BlockState.ACTIVE_PENDING_FREE == 0
        assert BlockState.ACTIVE_ALLOCATED == 1
        assert BlockState.UNKNOWN == 99

    def test_block_state_int_conversion(self) -> None:
        """Test BlockState can be converted to int."""
        assert int(BlockState.ACTIVE_ALLOCATED) == 1
        assert BlockState(1) == BlockState.ACTIVE_ALLOCATED

    def test_block_state_from_int(self) -> None:
        """Test creating BlockState from integer."""
        state = BlockState(-1)
        assert state == BlockState.INACTIVE
