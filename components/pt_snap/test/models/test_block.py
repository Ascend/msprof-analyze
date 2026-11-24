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

"""Tests for MemoryBlock model."""

from pt_snap_cli.models import BlockState, MemoryBlock


class TestMemoryBlock:
    """Test MemoryBlock dataclass."""

    def test_memory_block_creation(self) -> None:
        """Test creating a MemoryBlock instance."""
        block = MemoryBlock(
            id=-1,
            address=0x10000,
            size=4096,
            requested_size=4000,
            state=BlockState.ACTIVE_ALLOCATED,
            alloc_event_id=1,
            free_event_id=None,
        )
        assert block.id == -1
        assert block.address == 0x10000
        assert block.size == 4096
        assert block.state == BlockState.ACTIVE_ALLOCATED

    def test_is_historical_block_negative_id(self) -> None:
        """Test is_historical_block returns True for negative ID."""
        block = MemoryBlock(
            id=-100,
            address=0x1000,
            size=1024,
            requested_size=1000,
            state=BlockState.INACTIVE,
        )
        assert block.is_historical_block is True

    def test_is_historical_block_positive_id(self) -> None:
        """Test is_historical_block returns False for positive ID."""
        block = MemoryBlock(
            id=1,
            address=0x1000,
            size=1024,
            requested_size=1000,
            state=BlockState.ACTIVE_ALLOCATED,
        )
        assert block.is_historical_block is False

    def test_is_active_no_free_event(self) -> None:
        """Test is_active returns True when no free event."""
        block = MemoryBlock(
            id=-1,
            address=0x1000,
            size=1024,
            requested_size=1000,
            state=BlockState.ACTIVE_ALLOCATED,
            free_event_id=None,
        )
        assert block.is_active is True

    def test_is_active_free_event_minus_one(self) -> None:
        """Test is_active returns True when free_event_id is -1."""
        block = MemoryBlock(
            id=-1,
            address=0x1000,
            size=1024,
            requested_size=1000,
            state=BlockState.ACTIVE_ALLOCATED,
            free_event_id=-1,
        )
        assert block.is_active is True

    def test_is_active_with_free_event(self) -> None:
        """Test is_active returns False when free_event_id is set."""
        block = MemoryBlock(
            id=-1,
            address=0x1000,
            size=1024,
            requested_size=1000,
            state=BlockState.INACTIVE,
            free_event_id=10,
        )
        assert block.is_active is False
