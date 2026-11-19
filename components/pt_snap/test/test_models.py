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

"""Tests for models package exports."""

from pt_snap_cli.models import BlockState, EventType, MemoryBlock, MemoryEvent


class TestModelsExport:
    """Test models package exports."""

    def test_event_type_exported(self) -> None:
        """Test EventType is exported."""
        assert EventType is not None
        assert EventType.ALLOC == 4

    def test_block_state_exported(self) -> None:
        """Test BlockState is exported."""
        assert BlockState is not None
        assert BlockState.ACTIVE_ALLOCATED == 1

    def test_memory_event_exported(self) -> None:
        """Test MemoryEvent is exported."""
        assert MemoryEvent is not None
        event = MemoryEvent(
            id=1,
            action=EventType.ALLOC,
            address=0,
            size=0,
            stream=0,
            allocated=0,
            active=0,
            reserved=0,
        )
        assert event.id == 1

    def test_memory_block_exported(self) -> None:
        """Test MemoryBlock is exported."""
        assert MemoryBlock is not None
        block = MemoryBlock(
            id=-1,
            address=0,
            size=1024,
            requested_size=1000,
            state=BlockState.ACTIVE_ALLOCATED,
        )
        assert block.id == -1
