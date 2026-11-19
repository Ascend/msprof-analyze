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

"""
SQLite 元数据管理模块

提供 SQLite 数据库的表结构定义、类型映射、表创建和数据插入等功能。
支持 Python 类型到 SQLite 类型的自动转换，以及表结构的元数据管理。
"""

import ast
import os.path
import sqlite3
import types
from typing import Any, Dict, Iterable, List, Union

from typing_extensions import get_args, get_origin

# 支持的 Python 类型映射
_PY_TYPE_TO_SQLITE = {
    int: "INTEGER",
    float: "REAL",
    str: "TEXT",
    bool: "INTEGER",  # SQLite 没有 BOOLEAN，用 0/1
    bytes: "BLOB",
}


def _map_py_type_to_sqlite(py_type: object) -> str:
    """将 Python 类型转换为 SQLite 类型"""
    origin = get_origin(py_type) or py_type
    if origin in _PY_TYPE_TO_SQLITE:
        return _PY_TYPE_TO_SQLITE[origin]
    # 处理 Optional[T] / T | None => T
    if origin is Union or origin is getattr(types, "UnionType", None):
        args = get_args(py_type)
        # pylint: disable-next=unidiomatic-typecheck  # Reject bool/subclasses: the contract requires exact scalar types.
        non_none = [t for t in args if t is not type(None)]
        if len(non_none) == 1:
            return _map_py_type_to_sqlite(non_none[0])
    # 默认 fallback
    return "TEXT"


def _sqlite_type_to_py_type(sqlite_type: str) -> type:
    """将 SQLite 声明类型映射为最可能的 Python 类型"""
    if not sqlite_type:
        return str  # 无类型默认为 TEXT
    upper = sqlite_type.upper()
    if "INT" in upper:
        return int
    if "CHAR" in upper or "CLOB" in upper or "TEXT" in upper:
        return str
    if "BLOB" in upper:
        return bytes
    if "REAL" in upper or "FLOA" in upper or "DOUB" in upper:
        return float
    # 兜底：可能是 NUMERIC 或自定义类型，按 TEXT 处理
    return str


def _parse_default_value(dflt_str: str) -> Any:
    """将 PRAGMA 返回的默认值字符串转为 Python 对象"""
    if dflt_str is None:
        return None

    # 尝试解析为字面量（支持数字、字符串、布尔、None）
    try:
        # 处理 SQLite 中的布尔：'1'/'0' 或 'true'/'false'（但 SQLite 实际存整数）
        if dflt_str == "1":
            return True
        elif dflt_str == "0":
            return False
        elif dflt_str.lower() in ("true", "false"):
            return dflt_str.lower() == "true"
        # 尝试用 ast.literal_eval 安全解析
        return ast.literal_eval(dflt_str)
    except (ValueError, SyntaxError):
        # 如果不是合法字面量，当作字符串处理（去掉外层引号）
        if dflt_str.startswith("'") and dflt_str.endswith("'"):
            return dflt_str[1:-1].replace("''", "'")
        elif dflt_str.startswith('"') and dflt_str.endswith('"'):
            return dflt_str[1:-1].replace('""', '"')
        else:
            return dflt_str


class SqliteColumn:
    """
    SQLite 表的列定义类。

    用于定义表中的单个列，包括列名、数据类型、约束条件等属性。

    Attributes:
        name: 列名
        data_type: Python 类型，会自动映射为 SQLite 类型
        primary_key: 是否为主键
        autoincrement: 是否自增（仅适用于 INTEGER 主键）
        not_null: 是否不允许 NULL
        unique: 是否唯一
        default: 默认值
        value_map: 值映射字典，用于插入时的值转换

    Examples:
        >>> col = SqliteColumn('id', int, primary_key=True, autoincrement=True)
        >>> col.to_sql_def()
        '`id` INTEGER PRIMARY KEY AUTOINCREMENT'

        >>> col = SqliteColumn('name', str, not_null=True, default='unknown')
        >>> col.to_sql_def()
        "`name` TEXT NOT NULL DEFAULT 'unknown'"
    """

    def __init__(
        self,
        name: str,
        data_type: object = str,
        primary_key: bool = False,  # 是否主键
        autoincrement: bool = False,  # 是否自增
        not_null: bool = False,  # 是否不可为空
        unique: bool = False,  # 是否唯一
        default: Union[Any, None] = None,  # 缺省值,
        value_map: Union[Dict[Any, Any], None] = None,
    ):
        if autoincrement and not primary_key:
            raise ValueError("autoincrement requires primary_key=True")
        if autoincrement and data_type is not int:
            raise ValueError("autoincrement only supported for INTEGER type")
        self.name = name
        self.data_type = data_type
        self.primary_key = primary_key
        self.autoincrement = autoincrement
        self.not_null = not_null
        self.unique = unique
        self.default = default
        self.value_map = value_map

    def _format_default(self) -> str:
        """格式化默认值为 SQL 字面量"""
        val = self.default
        if val is None:
            return "NULL"
        elif isinstance(val, bool):
            return "1" if val else "0"
        elif isinstance(val, str):
            # 转义单引号（简单处理）
            escaped = val.replace("'", "''")
            return f"'{escaped}'"
        elif isinstance(val, (int, float)):
            return str(val)
        else:
            # 兜底：转为字符串并加引号
            return f"'{str(val)}'"

    def to_sql_def(self) -> str:
        """
        生成列的 SQL 定义语句。

        Returns:
            str: 完整的列定义 SQL，如 "`id` INTEGER PRIMARY KEY AUTOINCREMENT"

        Examples:
            >>> col = SqliteColumn('id', int, primary_key=True)
            >>> col.to_sql_def()
            '`id` INTEGER PRIMARY KEY'
        """
        parts = [f"`{self.name}`", _map_py_type_to_sqlite(self.data_type)]

        if self.primary_key:
            parts.append("PRIMARY KEY")
        if self.autoincrement:
            parts.append("AUTOINCREMENT")
        if self.not_null:
            parts.append("NOT NULL")
        if self.unique:
            parts.append("UNIQUE")
        if self.default is not None:
            parts.append(f"DEFAULT {self._format_default()}")

        return " ".join(parts)


class SqliteTable:
    """
    SQLite 表的定义和管理类。

    用于定义表结构、创建表、插入数据等操作。

    Attributes:
        name: 表名
        column_dict: 列定义字典，键为列名，值为 SqliteColumn 对象
        _column_value_map: 列值映射字典，用于插入时的值转换

    Examples:
        >>> columns = [
        ...     SqliteColumn('id', int, primary_key=True, autoincrement=True),
        ...     SqliteColumn('name', str, not_null=True)
        ... ]
        >>> table = SqliteTable('users', columns)
        >>> print(table.to_sql_def())
        CREATE TABLE IF NOT EXISTS users (`id` INTEGER PRIMARY KEY AUTOINCREMENT, `name` TEXT NOT NULL);
    """

    name: str
    column_dict: Dict[str, SqliteColumn]
    _column_value_map: Dict[str, Dict[Any, Any]]

    def __init__(self, table_name: str, columns: Union[Iterable[SqliteColumn], None] = None):
        self.name = table_name
        self.column_dict = {}
        self._column_value_map = {}
        if columns:
            for column in columns:
                self.column_dict[column.name] = column
                if column.value_map:
                    self._column_value_map[column.name] = column.value_map

    def to_sql_def(self, delete_if_exists: bool = False) -> str:
        """
        生成创建表的 SQL 语句。

        Args:
            delete_if_exists: 是否先 DROP TABLE IF EXISTS，默认为 False

        Returns:
            str: 创建表的 SQL 语句

        Examples:
            >>> table.to_sql_def(delete_if_exists=True)
            'DROP TABLE IF EXISTS users;\\nCREATE TABLE users (...)'
        """
        column_defs = [col.to_sql_def() for _, col in self.column_dict.items()]
        create_sql = f"CREATE TABLE {self.name} ({', '.join(column_defs)});"

        if delete_if_exists:
            drop_sql = f"DROP TABLE IF EXISTS {self.name};"
            return f"{drop_sql}\n{create_sql}"
        else:
            # 使用 IF NOT EXISTS 更安全
            create_sql = create_sql.replace("CREATE TABLE", "CREATE TABLE IF NOT EXISTS", 1)
            return create_sql

    def create_table(self, conn: sqlite3.Connection, delete_if_exists: bool = False):
        """
        在数据库中创建表
        :param conn: sqlite3.Connection 对象
        :param delete_if_exists: 是否先删除已存在的表
        """
        sql = self.to_sql_def(delete_if_exists=delete_if_exists)
        conn.executescript(sql)  # 支持多条 SQL（如 DROP + CREATE）
        conn.commit()

    def create_index(self, conn: sqlite3.Connection, column_name: str):
        """
        创建索引
        :param conn: sqlite3.Connection 对象
        :param column_name: 列名
        :return:
        """
        conn.execute(f"CREATE INDEX IF NOT EXISTS idx_{self.name}_{column_name} ON {self.name} ({column_name});")
        conn.commit()

    def insert_record(self, conn: sqlite3.Connection, record: Dict[str, Any]):
        """
        插入单条记录。

        Args:
            conn: sqlite3.Connection 对象
            record: 记录字典，键为列名，值为列值

        Examples:
            >>> table.insert_record(conn, {'name': 'Alice', 'age': 30})
        """
        self.insert_records(conn, [record])

    def insert_records(self, conn: sqlite3.Connection, records: List[Dict[str, Any]]):
        """
        批量插入多条记录。

        Args:
            conn: sqlite3.Connection 对象
            records: 记录字典列表，每个字典的键为列名，值为列值

        Examples:
            >>> records = [
            ...     {'name': 'Alice', 'age': 30},
            ...     {'name': 'Bob', 'age': 25}
            ... ]
            >>> table.insert_records(conn, records)
        """
        if not records:
            return
        columns = SqliteTable.get_insert_columns_by_record(records[0])
        placeholders = SqliteTable.get_insert_placeholder_by_record(records[0])
        sql = f"INSERT INTO {self.name} ({', '.join(columns)}) VALUES ({placeholders})"  # nosec B608 # Internal writer schema supplies identifiers; record values are bound separately.
        values = self.get_insert_values_by_records(records)
        conn.executemany(sql, values)
        conn.commit()

    @staticmethod
    def get_insert_columns_by_record(record: Dict[str, Any]):
        """
        从记录字典中获取插入列名列表。

        Args:
            record: 记录字典

        Returns:
            List[str]: 列名列表（带反引号）
        """
        return [f"`{key}`" for key in record.keys()]

    @staticmethod
    def get_insert_placeholder_by_record(record: Dict[str, Any]):
        """
        生成插入语句的占位符字符串。

        Args:
            record: 记录字典

        Returns:
            str: 占位符字符串，如 "?, ?, ?"
        """
        return ", ".join(["?" for _ in record.keys()])

    def get_insert_values_by_records(self, records: List[Dict[str, Any]]):
        """
        从记录列表中提取插入值，应用值映射。

        Args:
            records: 记录字典列表

        Returns:
            List[Tuple]: 值元组列表，每个元组对应一条记录
        """
        if not records:
            return []
        # Resolve the per-column value maps once instead of per cell; batches of
        # snapshot rows are large enough that the per-cell lookup dominated.
        keys = list(records[0].keys())
        mapped = [(key, self._column_value_map.get(key)) for key in keys]
        if not any(value_map for _, value_map in mapped):
            return [tuple(record[key] for key in keys) for record in records]
        return [
            tuple(
                record[key] if value_map is None else value_map.get(record[key], record[key])
                for key, value_map in mapped
            )
            for record in records
        ]


class SqliteDB:
    """
    SQLite 数据库管理类。

    提供数据库连接、表创建、表结构查询等功能。

    Attributes:
        path: 数据库文件路径
        conn: sqlite3.Connection 对象
        table_cache: 表缓存字典，键为表名，值为 SqliteTable 对象
        with_dictionary_table: 是否创建字典表用于存储值映射

    Examples:
        >>> db = SqliteDB('/path/to/db.sqlite')
        >>> table = SqliteTable('users', [
        ...     SqliteColumn('id', int, primary_key=True),
        ...     SqliteColumn('name', str)
        ... ])
        >>> db.create_table(table)
    """

    path: str
    conn: sqlite3.Connection
    table_cache: Dict[str, SqliteTable]

    def __init__(self, path: str, auto_create: bool = True, with_dictionary_table: bool = False):
        self.path = os.path.realpath(path)
        if not os.path.exists(self.path):
            if not auto_create:
                raise FileNotFoundError(f"Db file not found: {self.path}.")
            dir_path = os.path.dirname(self.path)
            if not os.path.exists(dir_path):
                os.makedirs(dir_path, exist_ok=True)

        self.conn = sqlite3.connect(self.path)
        self.table_cache = {}
        self.with_dictionary_table = with_dictionary_table
        if self.with_dictionary_table:
            self._create_dictionary_table()

    def create_table(self, table: SqliteTable, delete_if_exists: bool = True):
        """
        在数据库中创建表，并缓存表结构。

        Args:
            table: SqliteTable 对象
            delete_if_exists: 是否先删除已存在的表，默认为 True

        Note:
            如果启用了 with_dictionary_table，会自动将值映射存储到字典表中。
        """
        table.create_table(self.conn, delete_if_exists)
        self.table_cache[table.name] = table
        if not self.with_dictionary_table:
            return
        dictionary_table = self.get_table_by_name("dictionary")
        for column_name, value_map in table._column_value_map.items():
            for key, value in value_map.items():
                dictionary_table.insert_record(
                    self.conn,
                    {"table": table.name, "column": column_name, "key": value, "value": key},
                )
        self.conn.commit()

    def delete_table(self, table_name: str):
        self.conn.execute(f"DROP TABLE IF EXISTS {table_name};")
        self.conn.commit()

    def _create_dictionary_table(self):
        _table_columns = [
            SqliteColumn(name="table"),
            SqliteColumn(name="column"),
            SqliteColumn(name="key"),
            SqliteColumn(name="value"),
        ]
        _dictionary_table = SqliteTable("dictionary", _table_columns)
        _dictionary_table.create_table(self.conn, delete_if_exists=True)
        self.table_cache[_dictionary_table.name] = _dictionary_table

    def is_table_exists(self, table_name: str) -> bool:
        """
        检查表是否存在。

        Args:
            table_name: 表名

        Returns:
            bool: 表是否存在

        Note:
            会优先检查缓存，如果缓存中不存在则查询数据库。
        """
        if table_name in self.table_cache:
            return True
        cursor = self.conn.cursor()
        cursor.execute(
            """
                       SELECT name
                       FROM sqlite_master
                       WHERE type = 'table'
                         AND name = ?
                       """,
            (table_name,),
        )
        exist = cursor.fetchone() is not None
        if exist:
            self.table_cache[table_name] = self.get_table_by_name(table_name)
        return exist

    def get_table_by_name(self, table_name: str) -> SqliteTable:
        """
        从数据库中读取表结构，还原为 SqliteTable 对象。

        Args:
            table_name: 表名

        Returns:
            SqliteTable: 表对象

        Raises:
            ValueError: 表不存在

        Note:
            会优先从缓存中获取，缓存中不存在时才查询数据库。
        """
        if table_name in self.table_cache:
            return self.table_cache[table_name]
        # 获取列信息
        cur = self.conn.execute(f"PRAGMA table_info({table_name});")
        rows = cur.fetchall()

        if not rows:
            raise ValueError(f"Table '{table_name}' does not exist.")
        table = SqliteTable(table_name)
        for row in rows:
            cid, name, type_affinity, notnull, dflt_value, pk = row

            py_type = _sqlite_type_to_py_type(type_affinity)
            default_val = _parse_default_value(dflt_value)

            # 检测是否为自增（仅当 INTEGER 主键且有 sqlite_sequence 记录）
            autoincrement = False
            if pk and py_type is int:
                # 检查是否存在 sqlite_sequence 表且包含该表
                seq_cur = self.conn.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table' AND name='sqlite_sequence';"
                )
                if seq_cur.fetchone():
                    seq_cur = self.conn.execute("SELECT 1 FROM sqlite_sequence WHERE name = ?;", (table_name,))
                    autoincrement = seq_cur.fetchone() is not None

            column = SqliteColumn(
                name=name,
                data_type=py_type,
                primary_key=bool(pk),
                autoincrement=autoincrement,
                not_null=bool(notnull),
                default=default_val,
                # 注意：UNIQUE、COLLATE 无法从 table_info 获取，需解析 CREATE SQL
            )
            table.column_dict[column.name] = column
        self.table_cache[table_name] = table
        return table
