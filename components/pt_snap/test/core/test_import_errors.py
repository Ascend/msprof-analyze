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

"""Tests for snapshot import error types."""

from __future__ import annotations

from pt_snap_cli.core.common.errors import (
    ImportExecutionError,
    ImportToolMissingError,
    PtSnapCoreError,
    SnapshotFileInvalidError,
)


def test_import_tool_missing_error_is_pt_snap_core() -> None:
    assert issubclass(ImportToolMissingError, PtSnapCoreError)


def test_snapshot_file_invalid_error_is_pt_snap_core() -> None:
    assert issubclass(SnapshotFileInvalidError, PtSnapCoreError)


def test_import_execution_error_is_pt_snap_core() -> None:
    assert issubclass(ImportExecutionError, PtSnapCoreError)


def test_unsafe_pickle_error_is_unpickling_error() -> None:
    from pickle import UnpicklingError

    from pt_snap_cli.snapshot.representation import UnsafePickleError

    assert issubclass(UnsafePickleError, UnpicklingError)
