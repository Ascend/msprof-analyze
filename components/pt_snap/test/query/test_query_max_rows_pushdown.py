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

"""End-to-end tests for the ``max_rows`` SQL pushdown that the executor
performs. These exercise the templates touched by issue #76
(``leak_detection`` and ``callstack_analysis``) to prove that ``max_rows``
reaches SQL as a ``LIMIT`` clause instead of being applied via Python
slicing in :class:`QueryService`.
"""

from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path

import pytest

from pt_snap_cli.config import Config
from pt_snap_cli.context import Context
from pt_snap_cli.core.analysis.query_service import QueryService
from pt_snap_cli.query.executor import QueryExecutor
from pt_snap_cli.query.registry import QueryRegistry, _load_all_templates

pytestmark = pytest.mark.usefixtures("owned_service_instances")


@pytest.fixture(autouse=True)
def _isolate_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Write project focus into a temp directory so the test run doesn't
    pollute the workspace root with a stray ``.pt-snap/focus.json``.
    """
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("PT_SNAP_DB_PATH", raising=False)


@pytest.fixture(autouse=True)
def _reload_registry() -> None:
    QueryRegistry.reset()
    _load_all_templates()


@pytest.fixture
def leak_db(tmp_path: Path) -> Path:
    db_path = tmp_path / "leak.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("CREATE TABLE dictionary (`table` TEXT, `column` TEXT, `key` TEXT, `value` TEXT)")
    conn.execute("""
        CREATE TABLE trace_entry_0 (
            id INTEGER PRIMARY KEY,
            size INTEGER
        )
    """)
    conn.execute("""
        CREATE TABLE block_0 (
            id INTEGER PRIMARY KEY,
            address INTEGER,
            size INTEGER,
            requestedSize INTEGER,
            state INTEGER,
            allocEventId INTEGER,
            freeEventId INTEGER
        )
    """)
    # Mix leaked blocks (freeEventId NULL/-1) with cleanly freed ones.
    rows = [(i, 0x1000 + i * 0x1000, 1024 * (i + 1), 1024 * (i + 1), 1, i + 1, -1) for i in range(10)]
    rows += [(20 + i, 0xA000 + i * 0x1000, 256, 256, 0, 100 + i, 100 + i + 1) for i in range(5)]
    conn.executemany(
        """
        INSERT INTO block_0
          (id, address, size, requestedSize, state, allocEventId, freeEventId)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
    )
    conn.commit()
    conn.close()
    return db_path


@pytest.fixture
def callstack_db(tmp_path: Path) -> Path:
    db_path = tmp_path / "callstack.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("CREATE TABLE dictionary (`table` TEXT, `column` TEXT, `key` TEXT, `value` TEXT)")
    conn.execute("""
        CREATE TABLE trace_entry_0 (
            id INTEGER PRIMARY KEY,
            size INTEGER,
            callstackId INTEGER
        )
    """)
    conn.execute("""
        CREATE TABLE callstack (
            id INTEGER PRIMARY KEY,
            callstack TEXT
        )
    """)
    # 6 callstacks with varying alloc counts so the ``min_count`` filter
    # actually has something to drop:
    #   * 4 callstacks have 10+ entries (pass min_count=5)
    #   * 2 callstacks have 4 entries each (fail min_count=5)
    rows: list[tuple[int, int, int]] = []
    callstacks = [
        ("train.py:10", 12),
        ("train.py:20", 11),
        ("model.py:30", 10),
        ("model.py:40", 10),
        ("noise.py:50", 4),
        ("noise.py:60", 4),
    ]
    conn.executemany(
        "INSERT INTO callstack (id, callstack) VALUES (?, ?)",
        [(index, text) for index, (text, _) in enumerate(callstacks)],
    )
    for index, (_, count) in enumerate(callstacks):
        for _ in range(count):
            rows.append((len(rows) + 1, 100, index))
    conn.executemany(
        "INSERT INTO trace_entry_0 (id, size, callstackId) VALUES (?, ?, ?)",
        rows,
    )
    conn.commit()
    conn.close()
    return db_path


def _execute_template(db_path: Path, name: str, params: dict) -> list[dict]:
    ctx = Context(db_path)
    executor = QueryExecutor(ctx)
    rows = executor.execute_template(name, params=params, device_id=0)
    ctx.close()
    return rows


class TestLeakDetectionMaxRowsPushdown:
    def test_default_returns_all_leaks(self, leak_db: Path) -> None:
        rows = _execute_template(leak_db, "leak_detection", {})
        assert len(rows) == 10

    def test_max_rows_appended_as_limit(self, leak_db: Path) -> None:
        """``max_rows`` must push down so SQL returns only N rows."""
        config = Config()
        config.write_project_focus(leak_db, device_id=0)

        result = QueryService().execute_query("leak_detection", max_rows=3)
        assert result.total == 3
        assert result.returned == 3
        assert result.has_more is True
        assert result.total_is_exact is False
        assert len(result.rows) == 3

        exact = QueryService().execute_query("leak_detection", max_rows=3, exact_total=True)
        assert exact.total == 10
        assert exact.returned == 3
        assert exact.has_more is True
        assert exact.total_is_exact is True

    def test_explicit_limit_param_pushes_down(self, leak_db: Path) -> None:
        """Users can still pass ``params['limit']`` directly to the
        template; the executor does not override a positive limit.
        """
        rows = _execute_template(leak_db, "leak_detection", {"limit": 4})
        assert len(rows) == 4

    def test_max_rows_zero_keeps_all_rows(self, leak_db: Path) -> None:
        config = Config()
        config.write_project_focus(leak_db, device_id=0)
        result = QueryService().execute_query("leak_detection", max_rows=0)
        assert result.total == 10


class TestCallstackAnalysisMaxRowsPushdown:
    def test_default_min_count_filters_noise(self, callstack_db: Path) -> None:
        rows = _execute_template(callstack_db, "callstack_analysis", {})
        # Default min_count=5 leaves the four real callstacks.
        assert [row["callstack"] for row in rows] == [
            "train.py:10",
            "train.py:20",
            "model.py:30",
            "model.py:40",
        ]

    def test_max_rows_pushes_down_to_limit(self, callstack_db: Path) -> None:
        config = Config()
        config.write_project_focus(callstack_db, device_id=0)
        result = QueryService().execute_query("callstack_analysis", max_rows=2)
        assert result.total == 2
        assert result.returned == 2
        assert result.has_more is True
        assert result.total_is_exact is False

    def test_min_size_filter_combines_with_limit(self, callstack_db: Path) -> None:
        rows = _execute_template(
            callstack_db,
            "callstack_analysis",
            {"min_size": 0, "min_count": 1, "limit": 2},
        )
        assert len(rows) == 2

    def test_missing_callstack_uses_placeholder(self, callstack_db: Path) -> None:
        with closing(sqlite3.connect(callstack_db)) as conn, conn:
            conn.execute(
                "INSERT INTO trace_entry_0 (id, size, callstackId) VALUES (?, ?, ?)",
                (100, 1, 99),
            )
            conn.commit()

        rows = _execute_template(
            callstack_db,
            "callstack_analysis",
            {"min_count": 1, "min_size": 0},
        )

        assert rows[-1]["callstack"] == "[missing callstack]"
