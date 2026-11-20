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

"""Read-only v1/v2 callstack schema compatibility for packaged templates."""

from __future__ import annotations

import hashlib
import sqlite3
from contextlib import closing
from pathlib import Path

import pytest

from pt_snap_cli.context import Context
from pt_snap_cli.core.analysis.query_service import QueryService
from pt_snap_cli.query.config import QueryTemplate
from pt_snap_cli.query.executor import QueryExecutionError, QueryExecutor
from pt_snap_cli.query.registry import QueryRegistry, _load_all_templates, get_query

pytestmark = pytest.mark.usefixtures("owned_service_instances")


@pytest.fixture(autouse=True)
def _reload_query_templates() -> None:
    QueryRegistry.reset()
    _load_all_templates()


_BLOCKS = [
    (-10, 0xA000, 8192, 8000, 1, -1, -1),
    (1, 0x1000, 1024, 1000, 1, 1, -1),
    (2, 0x2000, 2048, 2000, 0, 2, 3),
    (4, 0x4000, 4096, 4000, 1, 4, -1),
    (5, 0x5000, 512, 500, 1, 5, -1),
]
_EVENTS = [
    (1, 2, 0x1000, 1024, 0, 1024, 1024, 4096, "train.py:10"),
    (2, 2, 0x2000, 2048, 0, 3072, 3072, 4096, "freed.py:20"),
    (3, 3, 0x2000, 2048, 0, 1024, 1024, 8192, "free.py:30"),
    (4, 2, 0x4000, 4096, 0, 5120, 5120, 8192, "after.py:40"),
    (5, 2, 0x5000, 512, 0, 5632, 5632, 8192, None),
]


def _fingerprint(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    return digest, path.stat().st_mtime_ns


def _create_dictionary(conn: sqlite3.Connection) -> None:
    conn.execute("CREATE TABLE dictionary (`table` TEXT, `column` TEXT, `key` TEXT, `value` TEXT)")


def _create_block_table(conn: sqlite3.Connection, device_id: int = 0) -> None:
    conn.execute(f"""
        CREATE TABLE block_{device_id} (
            id INTEGER PRIMARY KEY,
            address INTEGER,
            size INTEGER,
            requestedSize INTEGER,
            state INTEGER,
            allocEventId INTEGER,
            freeEventId INTEGER
        )
        """)
    conn.executemany(
        f"""
        INSERT INTO block_{device_id}
          (id, address, size, requestedSize, state, allocEventId, freeEventId)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        _BLOCKS,
    )


def _insert_metadata(conn: sqlite3.Connection, import_format_version: int) -> None:
    conn.execute("""
        CREATE TABLE pt_snap_metadata (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            metadata_schema_version INTEGER NOT NULL,
            import_format_version INTEGER NOT NULL,
            source_sha256 TEXT NOT NULL,
            source_size INTEGER NOT NULL,
            source_name TEXT NOT NULL,
            requested_device INTEGER,
            importer_name TEXT NOT NULL,
            importer_version TEXT NOT NULL,
            completed_at TEXT NOT NULL
        )
        """)
    conn.execute(
        """
        INSERT INTO pt_snap_metadata (
            id, metadata_schema_version, import_format_version, source_sha256,
            source_size, source_name, requested_device, importer_name,
            importer_version, completed_at
        ) VALUES (1, 1, ?, ?, 1, 'snapshot.pkl', NULL, 'pt-snap-cli', '0.2.0',
                  '2026-01-01T00:00:00+00:00')
        """,
        (import_format_version, "a" * 64),
    )


def create_v1_db(
    path: Path,
    *,
    metadata_version: int | None = None,
    extra_device: bool = False,
) -> Path:
    conn = sqlite3.connect(str(path))
    _create_dictionary(conn)
    devices = [0, 1] if extra_device else [0]
    for device_id in devices:
        conn.execute(f"""
            CREATE TABLE trace_entry_{device_id} (
                id INTEGER PRIMARY KEY,
                action INTEGER,
                address INTEGER,
                size INTEGER,
                stream INTEGER,
                allocated INTEGER,
                active INTEGER,
                reserved INTEGER,
                callstack TEXT
            )
            """)
        conn.executemany(
            f"""
            INSERT INTO trace_entry_{device_id}
              (id, action, address, size, stream, allocated, active, reserved, callstack)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            _EVENTS,
        )
        _create_block_table(conn, device_id)
    if metadata_version is not None:
        _insert_metadata(conn, metadata_version)
    conn.commit()
    conn.close()
    return path


def create_v2_db(path: Path, *, metadata_version: int | None = None) -> Path:
    conn = sqlite3.connect(str(path))
    _create_dictionary(conn)
    conn.execute("CREATE TABLE callstack (id INTEGER PRIMARY KEY, callstack TEXT)")
    texts = ["train.py:10", "freed.py:20", "free.py:30", "after.py:40"]
    conn.executemany(
        "INSERT INTO callstack (id, callstack) VALUES (?, ?)",
        list(enumerate(texts)),
    )
    conn.execute("""
        CREATE TABLE trace_entry_0 (
            id INTEGER PRIMARY KEY,
            action INTEGER,
            address INTEGER,
            size INTEGER,
            stream INTEGER,
            allocated INTEGER,
            active INTEGER,
            reserved INTEGER,
            callstackId INTEGER
        )
        """)
    conn.executemany(
        """
        INSERT INTO trace_entry_0
          (id, action, address, size, stream, allocated, active, reserved, callstackId)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [(*event[:-1], None if event[-1] is None else texts.index(event[-1])) for event in _EVENTS],
    )
    _create_block_table(conn)
    if metadata_version is not None:
        _insert_metadata(conn, metadata_version)
    conn.commit()
    conn.close()
    return path


def _execute(db_path: Path, name: str, params: dict | None = None) -> list[dict]:
    context = Context(db_path)
    try:
        return QueryExecutor(context).execute_template(name, params or {}, device_id=0)
    finally:
        context.close()


@pytest.fixture
def v1_db(tmp_path: Path) -> Path:
    return create_v1_db(tmp_path / "v1.db")


@pytest.fixture
def v2_db(tmp_path: Path) -> Path:
    return create_v2_db(tmp_path / "v2.db")


def test_packaged_callstack_templates_declare_both_variants() -> None:
    for name in ("event", "callstack_analysis", "active_memory_callstack_at_event"):
        template = get_query(name)
        assert template is not None
        assert set(template.query_variants) == {"v1", "v2"}
        assert "callstackId" in template.query_variants["v2"]
        assert "callstackId" not in template.query_variants["v1"]


def test_event_results_match_across_v1_and_v2(v1_db: Path, v2_db: Path) -> None:
    v1_rows = _execute(v1_db, "event", {"order_by": "id", "order_dir": "ASC"})
    v2_rows = _execute(v2_db, "event", {"order_by": "id", "order_dir": "ASC"})
    assert [row["id"] for row in v1_rows] == [1, 2, 3, 4, 5]
    assert [row["callstack"] for row in v1_rows] == [row["callstack"] for row in v2_rows]
    assert v1_rows[0]["callstack"] == "train.py:10"
    assert v1_rows[-1]["callstack"] is None


def test_callstack_analysis_aggregates_match_across_layouts(v1_db: Path, v2_db: Path) -> None:
    params = {"min_count": 1, "min_size": 0}
    v1_rows = _execute(v1_db, "callstack_analysis", params)
    v2_rows = _execute(v2_db, "callstack_analysis", params)
    assert [(row["callstack"], row["alloc_count"], row["total_size"]) for row in v1_rows] == [
        (row["callstack"], row["alloc_count"], row["total_size"]) for row in v2_rows
    ]
    assert [row["callstack"] for row in v1_rows] == [
        "after.py:40",
        "free.py:30",
        "freed.py:20",
        "train.py:10",
    ]


def test_active_memory_callstack_groups_match_across_layouts(v1_db: Path, v2_db: Path) -> None:
    params = {"event_id": 5, "include_static": True, "top_n": -1}
    v1_rows = _execute(v1_db, "active_memory_callstack_at_event", params)
    v2_rows = _execute(v2_db, "active_memory_callstack_at_event", params)
    assert {row["callstack"]: row["size_bytes"] for row in v1_rows} == {
        row["callstack"]: row["size_bytes"] for row in v2_rows
    }
    by_callstack = {row["callstack"]: row for row in v1_rows}
    assert by_callstack["[static] allocEventId=-1, freeEventId=-1"]["size_bytes"] == 8192
    assert by_callstack["after.py:40"]["size_bytes"] == 4096
    assert by_callstack["[missing callstack]"]["requested_bytes"] == 500


@pytest.fixture(params=["v1", "v2"])
def missing_callstack_db(request: pytest.FixtureRequest, tmp_path: Path) -> Path:
    """Include every missing-link shape alongside real and synthetic groups."""
    layout = request.param
    create = create_v1_db if layout == "v1" else create_v2_db
    path = create(tmp_path / f"missing-{layout}.db")
    with closing(sqlite3.connect(path)) as conn, conn:
        conn.execute("DELETE FROM block_0")
        conn.execute("DELETE FROM trace_entry_0")
        # Empty text, NULL text, NULL ID, dangling ID, and missing alloc event.
        texts = ["", None, None, None, "train.py:10", " ", "[missing callstack]"]
        if layout == "v1":
            conn.executemany(
                "INSERT INTO trace_entry_0 (id, callstack) VALUES (?, ?)",
                enumerate(texts, start=1),
            )
        else:
            conn.execute("DELETE FROM callstack")
            conn.executemany(
                "INSERT INTO callstack (id, callstack) VALUES (?, ?)",
                [(1, ""), (2, None), (5, texts[4]), (6, texts[5]), (7, texts[6])],
            )
            conn.executemany(
                "INSERT INTO trace_entry_0 (id, callstackId) VALUES (?, ?)",
                [(1, 1), (2, 2), (3, None), (4, 404), (5, 5), (6, 6), (7, 7)],
            )
        conn.executemany(
            "INSERT INTO block_0 (id, size, requestedSize, allocEventId, freeEventId) VALUES (?, ?, ?, ?, ?)",
            [
                (1, 100, 90, 1, -1),
                (2, 200, 180, 2, -1),
                (3, 300, 270, 3, -1),
                (4, 400, 360, 4, -1),
                (5, 500, 450, 8, -1),  # No trace row for alloc event 8.
                (6, 600, 540, 5, -1),
                (7, 700, 630, 5, -1),  # Same real callstack aggregates.
                (8, 10, 9, 6, -1),  # Whitespace is not empty text.
                (9, 20, 18, 7, -1),  # Literal label is not missing text.
                (10, 50, 45, -1, -1),
                (11, 70, 63, -1, 20),
            ],
        )
    return path


@pytest.mark.parametrize("include_static", [True, False])
@pytest.mark.parametrize("top_n", [-1, 1])
def test_missing_callstacks_merge_before_ranking_and_preserve_totals(
    missing_callstack_db: Path, include_static: bool, top_n: int
) -> None:
    rows = _execute(
        missing_callstack_db,
        "active_memory_callstack_at_event",
        {"event_id": 10, "include_static": include_static, "top_n": top_n},
    )
    dynamic = [row for row in rows if row["category"] == "dynamic_live_at_event"]
    assert len(dynamic) == (4 if top_n == -1 else 1)
    missing = dynamic[0]
    assert missing["callstack"] == "[missing callstack]"
    assert (missing["block_count"], missing["size_bytes"], missing["requested_bytes"]) == (
        5,
        1500,
        1350,
    )
    if top_n == -1:
        assert dynamic[1]["callstack"] == "train.py:10"
        assert dynamic[1]["block_count"] == 2
        assert dynamic[1]["size_bytes"] == 1300
        assert [row["callstack"] for row in dynamic[2:]] == ["[missing callstack]", " "]
    assert {row["category"] for row in rows} == (
        {"dynamic_live_at_event", "static", "preexisting_live_at_event"}
        if include_static
        else {"dynamic_live_at_event"}
    )
    expected_size = (2830 if top_n == -1 else 1500) + (120 if include_static else 0)
    expected_requested = (2547 if top_n == -1 else 1350) + (108 if include_static else 0)
    expected_count = (9 if top_n == -1 else 5) + (2 if include_static else 0)
    assert sum(row["size_bytes"] for row in rows) == expected_size
    assert sum(row["requested_bytes"] for row in rows) == expected_requested
    assert sum(row["block_count"] for row in rows) == expected_count
    for row in rows:
        assert row["percent_of_active_blocks"] == round(row["size_bytes"] * 100 / expected_size, 4)
    assert sum(row["percent_of_active_blocks"] for row in rows) == pytest.approx(100, abs=0.0002)


def test_active_memory_v2_keeps_nonempty_callstack_ids_separate(v2_db: Path) -> None:
    with closing(sqlite3.connect(v2_db)) as conn, conn:
        conn.execute("INSERT INTO callstack (id, callstack) VALUES (99, 'train.py:10')")
        conn.execute("UPDATE trace_entry_0 SET callstackId = 99 WHERE id = 4")
    rows = _execute(v2_db, "active_memory_callstack_at_event", {"event_id": 5, "top_n": -1})
    normal = [row for row in rows if row["callstack"] == "train.py:10"]
    assert [(row["size_bytes"], row["block_count"]) for row in normal] == [(4096, 1), (1024, 1)]


def test_missing_callstack_filter_and_page_keep_sql_denominator(missing_callstack_db: Path) -> None:
    params = {"event_id": 10, "min_size": 200, "include_static": False, "top_n": -1}
    result = QueryService().execute_query(
        "active_memory_callstack_at_event", params=params, db_path=missing_callstack_db, max_rows=1
    )
    assert result.returned == 1
    assert result.has_more is True
    missing = result.rows[0]
    assert missing["callstack"] == "[missing callstack]"
    assert (missing["size_bytes"], missing["requested_bytes"], missing["block_count"]) == (
        1400,
        1260,
        4,
    )
    # The normal 1300-byte group remains in the denominator, beyond max_rows.
    assert missing["percent_of_active_blocks"] == round(1400 * 100 / 2700, 4)


def test_v1_callstack_analysis_pagination_and_total(v1_db: Path) -> None:
    result = QueryService().execute_query(
        "callstack_analysis",
        params={"min_count": 1, "min_size": 0},
        db_path=v1_db,
        max_rows=2,
        exact_total=True,
    )
    assert result.total == 4
    assert result.returned == 2
    assert result.has_more is True
    assert result.total_is_exact is True
    assert [row["callstack"] for row in result.rows] == ["after.py:40", "free.py:30"]


def test_v2_callstack_analysis_v2_groups_full_text_and_real_actions(v2_db: Path) -> None:
    context = Context(v2_db)
    sql = QueryExecutor(context).render(
        get_query("callstack_analysis"),
        {"min_count": 1, "min_size": 0, "limit": -1},
        device_id=0,
    )
    assert "GROUP BY c.callstack" in sql
    assert "t.id >= 0" in sql
    assert "GROUP BY callstackId" not in sql
    assert get_query("callstack_analysis").semantics_version == 2
    context.close()


def test_v1_callstack_analysis_groups_by_text(v1_db: Path) -> None:
    context = Context(v1_db)
    sql = QueryExecutor(context).render(
        get_query("callstack_analysis"),
        {"min_count": 1, "min_size": 0, "limit": -1},
        device_id=0,
    )
    assert "GROUP BY callstack" in sql
    assert "callstackId" not in sql
    context.close()


def test_query_and_focus_do_not_write_v1_database(v1_db: Path) -> None:
    before = _fingerprint(v1_db)
    QueryService().execute_query("event", db_path=v1_db, params={"limit": 1})
    Context(v1_db)
    assert _fingerprint(v1_db) == before


@pytest.mark.parametrize("metadata_version", [None, 1])
def test_v1_layout_detected_with_or_without_metadata(tmp_path: Path, metadata_version: int | None) -> None:
    db_path = create_v1_db(tmp_path / "legacy.db", metadata_version=metadata_version)
    assert Context(db_path).callstack_layout == "v1"


@pytest.mark.parametrize("metadata_version", [None, 2, 3])
def test_v2_layout_detected_with_or_without_metadata(tmp_path: Path, metadata_version: int | None) -> None:
    db_path = create_v2_db(tmp_path / "current.db", metadata_version=metadata_version)
    assert Context(db_path).callstack_layout == "v2"


def test_multi_device_v1_layout_is_consistent(tmp_path: Path) -> None:
    db_path = create_v1_db(tmp_path / "multi.db", extra_device=True)
    ctx = Context(db_path)
    assert ctx.device_ids == [0, 1]
    assert ctx.callstack_layout == "v1"
    rows = QueryExecutor(ctx).execute_template("event", {"id": 1}, device_id=1)
    assert rows[0]["callstack"] == "train.py:10"


def test_metadata_conflict_fails_only_variant_templates(tmp_path: Path) -> None:
    db_path = create_v1_db(tmp_path / "conflict.db", metadata_version=2)
    ctx = Context(db_path)
    assert ctx.callstack_layout is None
    assert ctx.callstack_layout_error is not None
    assert "import_format_version is 2" in ctx.callstack_layout_error
    executor = QueryExecutor(ctx)
    with pytest.raises(QueryExecutionError, match="import_format_version is 2"):
        executor.execute_template("event", device_id=0)
    executor.register_template(QueryTemplate(name="plain_size", query="SELECT size FROM {{ device_trace_table }}"))
    assert executor.execute_template("plain_size", device_id=0)[0]["size"] == 1024


def test_unknown_metadata_version_does_not_override_structure(tmp_path: Path) -> None:
    db_path = create_v2_db(tmp_path / "future.db", metadata_version=4)
    assert Context(db_path).callstack_layout == "v2"


def test_mixed_device_layouts_fail_only_variant_templates(tmp_path: Path) -> None:
    db_path = tmp_path / "mixed.db"
    conn = sqlite3.connect(str(db_path))
    _create_dictionary(conn)
    conn.execute("CREATE TABLE trace_entry_0 (id INTEGER PRIMARY KEY, callstack TEXT)")
    conn.execute("CREATE TABLE trace_entry_1 (id INTEGER PRIMARY KEY, callstackId INTEGER)")
    conn.execute("CREATE TABLE callstack (id INTEGER PRIMARY KEY, callstack TEXT)")
    conn.commit()
    conn.close()
    ctx = Context(db_path)
    assert ctx.device_ids == [0, 1]
    assert ctx.callstack_layout is None
    assert ctx.callstack_layout_error is not None
    assert "devices disagree" in ctx.callstack_layout_error
    executor = QueryExecutor(ctx)
    with pytest.raises(QueryExecutionError, match="devices disagree"):
        executor.execute_template("event", device_id=0)
    executor.register_template(QueryTemplate(name="plain_id", query="SELECT id FROM {{ device_trace_table }}"))
    assert executor.execute_template("plain_id", device_id=0) == []


def test_unknown_layout_errors_only_for_variant_templates(tmp_path: Path) -> None:
    db_path = tmp_path / "unknown.db"
    conn = sqlite3.connect(str(db_path))
    _create_dictionary(conn)
    conn.execute("CREATE TABLE trace_entry_0 (id INTEGER PRIMARY KEY, size INTEGER)")
    conn.commit()
    conn.close()

    ctx = Context(db_path)
    assert ctx.callstack_layout is None
    assert ctx.callstack_layout_error is None
    executor = QueryExecutor(ctx)
    with pytest.raises(QueryExecutionError, match="needs a v1 or v2 callstack layout"):
        executor.execute_template("event", device_id=0)
    executor.register_template(QueryTemplate(name="plain_size", query="SELECT size FROM {{ device_trace_table }}"))
    assert executor.execute_template("plain_size", device_id=0) == []


def test_unrecognized_structure_conflicts_with_metadata_version(tmp_path: Path) -> None:
    db_path = tmp_path / "unrecognized-meta.db"
    conn = sqlite3.connect(str(db_path))
    _create_dictionary(conn)
    conn.execute("CREATE TABLE trace_entry_0 (id INTEGER PRIMARY KEY, size INTEGER)")
    _insert_metadata(conn, 2)
    conn.commit()
    conn.close()

    ctx = Context(db_path)
    assert ctx.callstack_layout is None
    assert ctx.callstack_layout_error is not None
    assert "import_format_version is 2" in ctx.callstack_layout_error
    assert "unrecognized" in ctx.callstack_layout_error
    with pytest.raises(QueryExecutionError, match="import_format_version is 2"):
        QueryExecutor(ctx).execute_template("event", device_id=0)


def test_v2_layout_accepts_case_insensitive_callstack_table(tmp_path: Path) -> None:
    db_path = tmp_path / "Callstack.db"
    conn = sqlite3.connect(str(db_path))
    _create_dictionary(conn)
    conn.execute("CREATE TABLE Callstack (id INTEGER PRIMARY KEY, callstack TEXT)")
    conn.execute("CREATE TABLE trace_entry_0 (id INTEGER PRIMARY KEY, callstackId INTEGER)")
    conn.commit()
    conn.close()
    assert Context(db_path).callstack_layout == "v2"


def test_v1_layout_detects_case_insensitive_shared_table(tmp_path: Path) -> None:
    db_path = tmp_path / "v1-Callstack.db"
    conn = sqlite3.connect(str(db_path))
    _create_dictionary(conn)
    conn.execute("CREATE TABLE Callstack (id INTEGER PRIMARY KEY, callstack TEXT)")
    conn.execute("CREATE TABLE trace_entry_0 (id INTEGER PRIMARY KEY, callstack TEXT)")
    conn.commit()
    conn.close()
    ctx = Context(db_path)
    assert ctx.callstack_layout is None
    assert ctx.callstack_layout_error is not None
    assert "coexists" in ctx.callstack_layout_error
