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

"""Shared query/report options; resolution and validation stay in core."""

from typing import Optional

import typer
from typing_extensions import Annotated

MaxWorkRows = Annotated[
    Optional[int],
    typer.Option(
        "--max-work-rows",
        rich_help_panel="Dataset limits",
        help="Dataset cumulative fetched/output rows, positive integer (env: PT_SNAP_MAX_WORK_ROWS; default: 100000)",
    ),
]
MaxWorkBytes = Annotated[
    Optional[int],
    typer.Option(
        "--max-work-bytes",
        rich_help_panel="Dataset limits",
        help="Dataset cumulative serialized work bytes, positive integer (env: PT_SNAP_MAX_WORK_BYTES; default: 67108864); not RSS",
    ),
]
MaxScratchDBBytes = Annotated[
    Optional[int],
    typer.Option(
        "--max-scratch-db-bytes",
        rich_help_panel="Dataset limits",
        help="Dataset derived DB page bytes: 0 disables, otherwise 4096..4294967296 (env: PT_SNAP_MAX_SCRATCH_DB_BYTES; default: 536870912)",
    ),
]
