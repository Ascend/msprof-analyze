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

"""Tests for query builder."""

import pytest

from pt_snap_cli.query.builder import QueryBuilder
from pt_snap_cli.query.condition import And, Equal, GreaterThan, In, Or


class TestQueryBuilder:
    def test_basic_select(self):
        builder = QueryBuilder()
        sql, params = builder.from_table("trace_entry_0").build()
        assert sql == "SELECT * FROM trace_entry_0"
        assert params == []

    def test_select_specific_columns(self):
        builder = QueryBuilder()
        sql, params = builder.from_table("trace_entry_0").columns("id", "address", "size").build()
        assert sql == "SELECT id, address, size FROM trace_entry_0"
        assert params == []

    def test_where_clause(self):
        builder = QueryBuilder()
        sql, params = builder.from_table("trace_entry_0").where(Equal("status", "active")).build()
        assert "WHERE" in sql
        assert "(status = ?)" in sql
        assert params == ["active"]

    def test_multiple_where_clauses(self):
        builder = QueryBuilder()
        sql, params = (
            builder.from_table("trace_entry_0")
            .where(Equal("status", "active"))
            .where(GreaterThan("size", 1024))
            .build()
        )
        assert "WHERE" in sql
        assert "(status = ?)" in sql
        assert "(size > ?)" in sql
        assert "AND" in sql
        assert params == ["active", 1024]

    def test_order_by(self):
        builder = QueryBuilder()
        sql, params = builder.from_table("trace_entry_0").order_by("size", descending=True).build()
        assert "ORDER BY size DESC" in sql

    def test_order_by_multiple(self):
        builder = QueryBuilder()
        sql, params = builder.from_table("trace_entry_0").order_by("status").order_by("size", descending=True).build()
        assert "ORDER BY status, size DESC" in sql

    def test_group_by(self):
        builder = QueryBuilder()
        sql, params = builder.from_table("trace_entry_0").group_by("eventType").build()
        assert "GROUP BY eventType" in sql

    def test_limit(self):
        builder = QueryBuilder()
        sql, params = builder.from_table("trace_entry_0").limit(100).build()
        assert "LIMIT 100" in sql

    def test_offset(self):
        builder = QueryBuilder()
        sql, params = builder.from_table("trace_entry_0").limit(100).offset(50).build()
        assert "LIMIT 100" in sql
        assert "OFFSET 50" in sql

    def test_full_query(self):
        builder = QueryBuilder()
        sql, params = (
            builder.from_table("trace_entry_0")
            .columns("id", "address", "size")
            .where(Equal("status", "active"))
            .where(GreaterThan("size", 1024))
            .order_by("size", descending=True)
            .limit(100)
            .build()
        )
        assert sql.startswith("SELECT id, address, size FROM trace_entry_0")
        assert "WHERE" in sql
        assert "ORDER BY size DESC" in sql
        assert "LIMIT 100" in sql
        assert params == ["active", 1024]

    def test_no_table_raises(self):
        builder = QueryBuilder()
        with pytest.raises(ValueError, match="Table must be set"):
            builder.build()

    def test_reset(self):
        builder = QueryBuilder()
        builder.from_table("trace_entry_0").where(Equal("a", 1)).limit(10)
        builder.reset()
        with pytest.raises(ValueError):
            builder.build()

    def test_in_condition(self):
        builder = QueryBuilder()
        sql, params = builder.from_table("trace_entry_0").where(In("eventType", ["alloc", "free"])).build()
        assert "eventType IN (?, ?)" in sql
        assert params == ["alloc", "free"]

    def test_combined_conditions(self):
        builder = QueryBuilder()
        cond = And(
            [
                Equal("status", "active"),
                Or(
                    [
                        Equal("type", "malloc"),
                        Equal("type", "cudaMalloc"),
                    ]
                ),
            ]
        )
        sql, params = builder.from_table("trace_entry_0").where(cond).build()
        assert "WHERE" in sql
        assert "AND" in sql
        assert "OR" in sql

    def test_having_clause(self):
        builder = QueryBuilder()
        sql, params = (
            builder.from_table("trace_entry_0").group_by("eventType").having(GreaterThan("COUNT(*)", 10)).build()
        )
        assert "GROUP BY eventType" in sql
        assert "HAVING" in sql
        assert "(COUNT(*) > ?)" in sql
        assert params == [10]

    def test_multiple_having_clauses(self):
        builder = QueryBuilder()
        sql, params = (
            builder.from_table("trace_entry_0")
            .group_by("eventType")
            .having(GreaterThan("COUNT(*)", 10))
            .having(GreaterThan("SUM(size)", 1024))
            .build()
        )
        assert "HAVING (COUNT(*) > ?) AND (SUM(size) > ?)" in sql
        assert params == [10, 1024]

    def test_full_query_with_having(self):
        builder = QueryBuilder()
        sql, params = (
            builder.from_table("trace_entry_0")
            .columns("eventType", "COUNT(*) as cnt")
            .where(Equal("action", "malloc"))
            .group_by("eventType")
            .having(GreaterThan("COUNT(*)", 5))
            .order_by("cnt", descending=True)
            .limit(10)
            .build()
        )
        assert sql.startswith("SELECT eventType, COUNT(*) as cnt FROM trace_entry_0")
        assert "WHERE" in sql
        assert "GROUP BY eventType" in sql
        assert "HAVING" in sql
        assert "ORDER BY cnt DESC" in sql
        assert "LIMIT 10" in sql
        assert params == ["malloc", 5]

    def test_reset_clears_having(self):
        builder = QueryBuilder()
        builder.from_table("t").group_by("c").having(GreaterThan("x", 1))
        builder.reset()
        sql, params = builder.from_table("t").build()
        assert "HAVING" not in sql
