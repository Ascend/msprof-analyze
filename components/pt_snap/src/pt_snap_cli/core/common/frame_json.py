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

"""Strict JSON validation shared by optional ordered frame readers."""

# pylint: disable-next=useless-import-alias  # Public re-export, also explicit for static type checkers.
from pt_snap_cli.snapshot.util.frame_json import (
    _bounded_depth as _bounded_depth,
)

# pylint: disable-next=useless-import-alias  # Public re-export, also explicit for static type checkers.
from pt_snap_cli.snapshot.util.frame_json import (
    _finite_float as _finite_float,
)

# pylint: disable-next=useless-import-alias  # Public re-export, also explicit for static type checkers.
from pt_snap_cli.snapshot.util.frame_json import (
    _invalid_constant as _invalid_constant,
)
