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

"""Query module for pt-snap."""

from pt_snap_cli.query.builder import QueryBuilder
from pt_snap_cli.query.condition import (
    And,
    Condition,
    Equal,
    GreaterThan,
    GreaterThanOrEqual,
    In,
    LessThan,
    LessThanOrEqual,
    Like,
    NotEqual,
    Or,
)
from pt_snap_cli.query.config import QueryConfig, QueryParameter, QueryTemplate
from pt_snap_cli.query.executor import QueryExecutor
from pt_snap_cli.query.mapper import ResultMapper
from pt_snap_cli.query.registry import QueryRegistry

__all__ = [
    "Condition",
    "Equal",
    "NotEqual",
    "GreaterThan",
    "GreaterThanOrEqual",
    "LessThan",
    "LessThanOrEqual",
    "In",
    "Like",
    "And",
    "Or",
    "QueryBuilder",
    "QueryConfig",
    "QueryParameter",
    "QueryTemplate",
    "QueryExecutor",
    "ResultMapper",
    "QueryRegistry",
]
