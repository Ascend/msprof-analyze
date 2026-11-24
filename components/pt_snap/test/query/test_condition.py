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

"""Tests for query condition classes."""

from pt_snap_cli.query.condition import (
    And,
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


class TestEqual:
    def test_to_sql(self):
        cond = Equal("size", 1024)
        sql, params = cond.to_sql()
        assert sql == "size = ?"
        assert params == [1024]

    def test_and_combination(self):
        cond1 = Equal("status", "active")
        cond2 = GreaterThan("size", 100)
        combined = cond1 & cond2
        sql, params = combined.to_sql()
        assert "(status = ?)" in sql
        assert "(size > ?)" in sql
        assert "AND" in sql
        assert params == ["active", 100]

    def test_or_combination(self):
        cond1 = Equal("status", "active")
        cond2 = Equal("status", "pending")
        combined = cond1 | cond2
        sql, params = combined.to_sql()
        assert "(status = ?)" in sql
        assert "OR" in sql
        assert params == ["active", "pending"]


class TestNotEqual:
    def test_to_sql(self):
        cond = NotEqual("status", "deleted")
        sql, params = cond.to_sql()
        assert sql == "status != ?"
        assert params == ["deleted"]

    def test_and_combination(self):
        cond1 = NotEqual("status", "deleted")
        cond2 = Equal("type", "malloc")
        combined = cond1 & cond2
        sql, params = combined.to_sql()
        assert "(status != ?)" in sql
        assert "(type = ?)" in sql
        assert "AND" in sql
        assert params == ["deleted", "malloc"]

    def test_or_combination(self):
        cond1 = NotEqual("status", "deleted")
        cond2 = Equal("status", "active")
        combined = cond1 | cond2
        sql, params = combined.to_sql()
        assert "OR" in sql
        assert params == ["deleted", "active"]


class TestGreaterThan:
    def test_to_sql(self):
        cond = GreaterThan("size", 1024)
        sql, params = cond.to_sql()
        assert sql == "size > ?"
        assert params == [1024]

    def test_and_combination(self):
        cond1 = GreaterThan("size", 1024)
        cond2 = LessThan("size", 4096)
        combined = cond1 & cond2
        sql, params = combined.to_sql()
        assert "(size > ?)" in sql
        assert "(size < ?)" in sql
        assert params == [1024, 4096]

    def test_or_combination(self):
        cond1 = GreaterThan("size", 1024)
        cond2 = Equal("size", 512)
        combined = cond1 | cond2
        sql, params = combined.to_sql()
        assert "OR" in sql
        assert params == [1024, 512]


class TestGreaterThanOrEqual:
    def test_to_sql(self):
        cond = GreaterThanOrEqual("size", 1024)
        sql, params = cond.to_sql()
        assert sql == "size >= ?"
        assert params == [1024]

    def test_and_combination(self):
        cond1 = GreaterThanOrEqual("size", 1024)
        cond2 = Equal("device", 0)
        combined = cond1 & cond2
        sql, params = combined.to_sql()
        assert "(size >= ?)" in sql
        assert "(device = ?)" in sql
        assert params == [1024, 0]

    def test_or_combination(self):
        cond1 = GreaterThanOrEqual("size", 1024)
        cond2 = LessThanOrEqual("size", 512)
        combined = cond1 | cond2
        sql, params = combined.to_sql()
        assert "OR" in sql
        assert params == [1024, 512]


class TestLessThan:
    def test_to_sql(self):
        cond = LessThan("size", 4096)
        sql, params = cond.to_sql()
        assert sql == "size < ?"
        assert params == [4096]

    def test_and_combination(self):
        cond1 = LessThan("size", 4096)
        cond2 = GreaterThan("size", 1024)
        combined = cond1 & cond2
        sql, params = combined.to_sql()
        assert "(size < ?)" in sql
        assert "(size > ?)" in sql
        assert params == [4096, 1024]

    def test_or_combination(self):
        cond1 = LessThan("size", 1024)
        cond2 = Equal("size", 8192)
        combined = cond1 | cond2
        sql, params = combined.to_sql()
        assert "OR" in sql
        assert params == [1024, 8192]


class TestLessThanOrEqual:
    def test_to_sql(self):
        cond = LessThanOrEqual("size", 4096)
        sql, params = cond.to_sql()
        assert sql == "size <= ?"
        assert params == [4096]

    def test_and_combination(self):
        cond1 = LessThanOrEqual("size", 4096)
        cond2 = NotEqual("device", 1)
        combined = cond1 & cond2
        sql, params = combined.to_sql()
        assert "(size <= ?)" in sql
        assert "(device != ?)" in sql
        assert params == [4096, 1]

    def test_or_combination(self):
        cond1 = LessThanOrEqual("size", 1024)
        cond2 = GreaterThan("size", 8192)
        combined = cond1 | cond2
        sql, params = combined.to_sql()
        assert "OR" in sql
        assert params == [1024, 8192]


class TestIn:
    def test_to_sql_single_value(self):
        cond = In("status", ["active"])
        sql, params = cond.to_sql()
        assert sql == "status IN (?)"
        assert params == ["active"]

    def test_to_sql_multiple_values(self):
        cond = In("status", ["active", "pending", "running"])
        sql, params = cond.to_sql()
        assert sql == "status IN (?, ?, ?)"
        assert params == ["active", "pending", "running"]

    def test_to_sql_int_values(self):
        cond = In("device_id", [0, 1, 2])
        sql, params = cond.to_sql()
        assert sql == "device_id IN (?, ?, ?)"
        assert params == [0, 1, 2]

    def test_and_combination(self):
        cond1 = In("status", ["active", "pending"])
        cond2 = Equal("device", 0)
        combined = cond1 & cond2
        sql, params = combined.to_sql()
        assert "(status IN (?, ?))" in sql
        assert "(device = ?)" in sql
        assert params == ["active", "pending", 0]

    def test_or_combination(self):
        cond1 = In("status", ["active", "pending"])
        cond2 = NotEqual("device", 1)
        combined = cond1 | cond2
        sql, params = combined.to_sql()
        assert "OR" in sql
        assert params == ["active", "pending", 1]

    def test_to_sql_empty_list(self):
        cond = In("status", [])
        sql, params = cond.to_sql()
        assert sql == "status IN ()"
        assert params == []


class TestLike:
    def test_to_sql(self):
        cond = Like("name", "%kernel%")
        sql, params = cond.to_sql()
        assert sql == "name LIKE ?"
        assert params == ["%kernel%"]

    def test_and_combination(self):
        cond1 = Like("name", "%kernel%")
        cond2 = GreaterThan("size", 1024)
        combined = cond1 & cond2
        sql, params = combined.to_sql()
        assert "(name LIKE ?)" in sql
        assert "(size > ?)" in sql
        assert params == ["%kernel%", 1024]

    def test_or_combination(self):
        cond1 = Like("name", "%kernel%")
        cond2 = Like("name", "%user%")
        combined = cond1 | cond2
        sql, params = combined.to_sql()
        assert "OR" in sql
        assert params == ["%kernel%", "%user%"]


class TestAnd:
    def test_empty_conditions(self):
        cond = And([])
        sql, params = cond.to_sql()
        assert sql == "1=1"
        assert params == []

    def test_single_condition(self):
        cond = And([Equal("a", 1)])
        sql, params = cond.to_sql()
        assert "(a = ?)" in sql
        assert params == [1]

    def test_multiple_conditions(self):
        cond = And(
            [
                Equal("a", 1),
                GreaterThan("b", 2),
                LessThan("c", 3),
            ]
        )
        sql, params = cond.to_sql()
        assert "(a = ?)" in sql
        assert "(b > ?)" in sql
        assert "(c < ?)" in sql
        assert "AND" in sql
        assert params == [1, 2, 3]

    def test_and_with_and(self):
        cond1 = And([Equal("a", 1)])
        cond2 = Equal("b", 2)
        combined = cond1 & cond2
        assert isinstance(combined, And)
        assert len(combined.conditions) == 2


class TestOr:
    def test_empty_conditions(self):
        cond = Or([])
        sql, params = cond.to_sql()
        assert sql == "1=1"
        assert params == []

    def test_multiple_conditions(self):
        cond = Or(
            [
                Equal("status", "active"),
                Equal("status", "pending"),
            ]
        )
        sql, params = cond.to_sql()
        assert "(status = ?)" in sql
        assert "OR" in sql
        assert params == ["active", "pending"]

    def test_or_with_or(self):
        cond1 = Or([Equal("a", 1)])
        cond2 = Equal("b", 2)
        combined = cond1 | cond2
        assert isinstance(combined, Or)
        assert len(combined.conditions) == 2


class TestComplexCombinations:
    def test_and_or_mixed(self):
        cond1 = Equal("a", 1)
        cond2 = GreaterThan("b", 2)
        cond3 = LessThan("c", 3)

        and_cond = cond1 & cond2
        or_cond = and_cond | cond3

        sql, params = or_cond.to_sql()
        assert "OR" in sql
        assert params == [1, 2, 3]

    def test_complex_nested(self):
        inner_and = And(
            [
                Equal("status", "active"),
                GreaterThan("size", 100),
            ]
        )
        inner_or = Or(
            [
                Equal("type", "malloc"),
                Equal("type", "cudaMalloc"),
            ]
        )
        combined = inner_and & inner_or

        sql, params = combined.to_sql()
        assert "AND" in sql
        assert len(params) == 4
