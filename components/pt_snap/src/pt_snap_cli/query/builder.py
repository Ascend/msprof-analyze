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

"""Query builder with fluent API for constructing SQL queries."""

from __future__ import annotations

from typing import Any, List, Tuple, Union

from pt_snap_cli.query.condition import Condition


class QueryBuilder:
    """Fluent API for building SQL queries."""

    def __init__(self):
        self._table: Union[str, None] = None
        self._columns: List[str] = ["*"]
        self._conditions: List[Condition] = []
        self._order_by: List[str] = []
        self._limit: Union[int, None] = None
        self._offset: Union[int, None] = None
        self._group_by: List[str] = []
        self._having: List[Condition] = []

    def from_table(self, table: str) -> QueryBuilder:
        """Set the table to query from.

        Args:
            table: Table name.

        Returns:
            Self for chaining.
        """
        self._table = table
        return self

    def columns(self, *cols: str) -> QueryBuilder:
        """Set the columns to select.

        Args:
            cols: Column names.

        Returns:
            Self for chaining.
        """
        self._columns = list(cols)
        return self

    def where(self, condition: Condition) -> QueryBuilder:
        """Add a WHERE condition.

        Args:
            condition: Condition to add.

        Returns:
            Self for chaining.
        """
        self._conditions.append(condition)
        return self

    def order_by(self, *columns: str, descending: bool = False) -> QueryBuilder:
        """Add ORDER BY clause.

        Args:
            columns: Column names to order by.
            descending: Whether to order in descending order.

        Returns:
            Self for chaining.
        """
        for col in columns:
            if descending:
                self._order_by.append(f"{col} DESC")
            else:
                self._order_by.append(col)
        return self

    def group_by(self, *columns: str) -> QueryBuilder:
        """Add GROUP BY clause.

        Args:
            columns: Column names to group by.

        Returns:
            Self for chaining.
        """
        self._group_by.extend(columns)
        return self

    def having(self, condition: Condition) -> QueryBuilder:
        """Add a HAVING condition.

        HAVING filters groups after aggregation. Should be used
        after a GROUP BY clause.

        Args:
            condition: Condition to add.

        Returns:
            Self for chaining.
        """
        self._having.append(condition)
        return self

    def limit(self, n: int) -> QueryBuilder:
        """Set LIMIT clause.

        Args:
            n: Maximum number of rows.

        Returns:
            Self for chaining.
        """
        self._limit = n
        return self

    def offset(self, n: int) -> QueryBuilder:
        """Set OFFSET clause.

        Args:
            n: Number of rows to skip.

        Returns:
            Self for chaining.
        """
        self._offset = n
        return self

    def build(self) -> Tuple[str, List[Any]]:
        """Build the SQL query.

        Returns:
            Tuple of (SQL string, list of parameters).

        Raises:
            ValueError: If table is not set.
        """
        if self._table is None:
            raise ValueError("Table must be set using from_table()")

        columns = ", ".join(self._columns)
        sql = f"SELECT {columns} FROM {self._table}"
        params: List[Any] = []

        if self._conditions:
            where_parts = []
            for cond in self._conditions:
                cond_sql, cond_params = cond.to_sql()
                where_parts.append(cond_sql)
                params.extend(cond_params)
            sql += " WHERE " + " AND ".join(f"({part})" for part in where_parts)

        if self._group_by:
            sql += " GROUP BY " + ", ".join(self._group_by)

        if self._having:
            having_parts = []
            for cond in self._having:
                cond_sql, cond_params = cond.to_sql()
                having_parts.append(cond_sql)
                params.extend(cond_params)
            sql += " HAVING " + " AND ".join(f"({part})" for part in having_parts)

        if self._order_by:
            sql += " ORDER BY " + ", ".join(self._order_by)

        if self._limit is not None:
            sql += f" LIMIT {self._limit}"

        if self._offset is not None:
            sql += f" OFFSET {self._offset}"

        return sql, params

    def reset(self) -> QueryBuilder:
        """Reset builder to initial state.

        Returns:
            Self for chaining.
        """
        self._table = None
        self._columns = ["*"]
        self._conditions = []
        self._order_by = []
        self._limit = None
        self._offset = None
        self._group_by = []
        self._having = []
        return self
