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

import hashlib
import sqlite3
from contextlib import closing
from pathlib import Path

import pytest

from pt_snap_cli.core.analysis.query_service import QueryService
from pt_snap_cli.core.common.errors import QueryExecutionError
from test.frame_tree_helpers import create_frame_tree_db


@pytest.fixture
def frame_db(tmp_path: Path) -> Path:
    return create_frame_tree_db(tmp_path / "frames.db")


def query(path: Path, name: str, params: dict, **kwargs):
    service = QueryService()
    try:
        return service.execute_query(name, params=params, db_path=path, **kwargs)
    finally:
        service.close()


def tree(path: Path, **params) -> list[dict[str, object]]:
    return query(path, "active_memory_frame_tree_at_event", {"event_id": 8, **params}).rows


def test_event_frames_preserve_original_order_and_reverse_only_on_request(frame_db: Path):
    original = query(frame_db, "event_frames", {"event_id": 1}).rows
    assert [(r["position"], r["filename"], r["name"]) for r in original] == [
        (0, "tensor.py", "a"),
        (1, "model.py", "forward"),
        (2, "train.py", "train"),
    ]
    reverse = query(frame_db, "event_frames", {"event_id": 1, "frame_order": "root_first"}).rows
    assert reverse == original[::-1]
    assert query(frame_db, "event_frames", {"event_id": 6}).rows == []
    assert query(frame_db, "event_frames", {"event_id": 999}).rows == []


def test_tree_conserves_bytes_counts_and_requested_memory_at_every_node(frame_db: Path):
    rows = tree(frame_db)
    assert rows[0]["node_id"] == "root"
    assert (rows[0]["size_bytes"], rows[0]["requested_bytes"], rows[0]["block_count"]) == (
        535,
        464,
        9,
    )
    assert sum(r["self_bytes"] for r in rows) == 535
    assert sum(r["self_requested_bytes"] for r in rows) == 464
    assert sum(r["self_block_count"] for r in rows) == 9
    for row in rows:
        children = [r for r in rows if r["parent_id"] == row["node_id"]]
        for total, own in [
            ("size_bytes", "self_bytes"),
            ("requested_bytes", "self_requested_bytes"),
            ("block_count", "self_block_count"),
        ]:
            assert row[total] == row[own] + sum(r[total] for r in children)
        assert row["percent_of_total"] == round(row["size_bytes"] * 100 / 535, 4)
    forward = [r for r in rows if r["name"] == "forward"]
    assert [(r["depth"], r["size_bytes"], r["self_bytes"]) for r in forward] == [
        (2, 375, 50),
        (3, 25, 25),
    ]
    leaves = [r for r in rows if r["name"] == "a"]
    assert sorted(r["size_bytes"] for r in leaves) == [75, 100]
    assert len({r["node_id"] for r in leaves}) == 2
    assert next(r for r in rows if r["node_id"] == "missing")["size_bytes"] == 5
    assert next(r for r in rows if r["node_id"] == "empty_callstack")["size_bytes"] == 10


def test_completion_boundary_and_filters_preserve_exact_denominator(frame_db: Path):
    after = tree(frame_db, event_id=10)
    # 100-byte dynamic and 30-byte preexisting allocations complete at 10;
    # the 888-byte allocation at 9 has now become live (without a stack).
    assert after[0]["size_bytes"] == 535 - 130 + 888
    filtered = tree(frame_db, include_static=False, min_size=50)
    assert filtered[0]["size_bytes"] == 425
    assert {r["category"] for r in filtered} == {"mixed", "dynamic_live_at_event"}
    empty = tree(frame_db, min_size=9999)
    assert len(empty) == 1
    assert empty[0]["node_id"] == "root" and empty[0]["parent_id"] is None
    assert empty[0]["size_bytes"] == empty[0]["requested_bytes"] == empty[0]["block_count"] == 0
    assert empty[0]["percent_of_total"] is None


def test_row_cap_is_explicit_and_does_not_recompute_total(frame_db: Path):
    result = query(frame_db, "active_memory_frame_tree_at_event", {"event_id": 8}, max_rows=2)
    assert result.truncated and result.has_more
    assert result.rows[0]["size_bytes"] == 535
    assert result.rows[1]["percent_of_total"] == round(375 * 100 / 535, 4)
    full = query(frame_db, "active_memory_frame_tree_at_event", {"event_id": 8}, exact_total=True)
    assert full.total == full.returned and full.total_is_exact and not full.truncated


def test_multi_device_analysis_is_read_only(frame_db: Path):
    before = hashlib.sha256(frame_db.read_bytes()).digest()
    first = query(frame_db, "active_memory_frame_tree_at_event", {"event_id": 8}, device_id=0)
    second = query(frame_db, "active_memory_frame_tree_at_event", {"event_id": 8}, device_id=1)
    assert first.rows == second.rows
    assert hashlib.sha256(frame_db.read_bytes()).digest() == before


@pytest.mark.parametrize(
    "damage",
    [
        "gap",
        "dangling_frame",
        "dangling_stack",
        "fractional_position",
        "tail",
        "all",
        "bad_line",
        "bad_name",
    ],
)
def test_corrupt_stack_links_preserve_occupancy_as_missing(frame_db: Path, damage: str):
    with closing(sqlite3.connect(frame_db)) as conn, conn:
        stack = conn.execute("SELECT callstackId FROM trace_entry_0 WHERE id=1").fetchone()[0]
        if damage == "gap":
            conn.execute("DELETE FROM callstack_frame WHERE callstackId=? AND position=1", (stack,))
        elif damage == "dangling_frame":
            conn.execute(
                "UPDATE callstack_frame SET frameId=999 WHERE callstackId=? AND position=0",
                (stack,),
            )
        elif damage == "fractional_position":
            conn.execute(
                "UPDATE callstack_frame SET position=0.5 WHERE callstackId=? AND position=1",
                (stack,),
            )
        elif damage == "tail":
            conn.execute("DELETE FROM callstack_frame WHERE callstackId=? AND position=2", (stack,))
        elif damage == "all":
            conn.execute("DELETE FROM callstack_frame WHERE callstackId=?", (stack,))
        elif damage in {"bad_line", "bad_name"}:
            column = "line" if damage == "bad_line" else "name"
            conn.execute(
                f"UPDATE frame SET {column}=? WHERE id=(SELECT frameId FROM callstack_frame WHERE callstackId=? AND position=0)",
                (0.5 if damage == "bad_line" else b"bad", stack),
            )
        else:
            conn.execute("DELETE FROM callstack WHERE id=?", (stack,))
    rows = tree(frame_db)
    assert rows[0]["size_bytes"] == 535
    expected_missing = 180 if damage in {"bad_line", "bad_name"} else 105
    assert next(r for r in rows if r["node_id"] == "missing")["size_bytes"] == expected_missing
    assert query(frame_db, "event_frames", {"event_id": 1}).rows == []
    for row in rows:
        children = [child for child in rows if child["parent_id"] == row["node_id"]]
        for total, own in [
            ("size_bytes", "self_bytes"),
            ("requested_bytes", "self_requested_bytes"),
            ("block_count", "self_block_count"),
        ]:
            assert row[total] == row[own] + sum(child[total] for child in children)


@pytest.mark.parametrize(
    "name,params",
    [("event_frames", {"event_id": 1}), ("active_memory_frame_tree_at_event", {"event_id": 8})],
)
def test_legacy_database_reports_actionable_reimport_error(frame_db: Path, name: str, params: dict):
    with closing(sqlite3.connect(frame_db)) as conn, conn:
        conn.execute("DROP TABLE callstack_frame")
        conn.execute("DROP TABLE frame")
    with pytest.raises(QueryExecutionError, match="Re-import the original snapshot"):
        query(frame_db, name, params)
    assert query(frame_db, "event", {"id": 1}).rows[0]["id"] == 1


def test_inline_text_database_retains_queries_but_cannot_supply_original_frames(tmp_path: Path):
    from test.query.test_callstack_schema_compat import create_v1_db

    path = create_v1_db(tmp_path / "inline.db")
    for name in ("event_frames", "active_memory_frame_tree_at_event"):
        with pytest.raises(QueryExecutionError, match="Re-import the original snapshot"):
            query(path, name, {"event_id": 1})
    assert query(path, "event", {"id": 1}).rows[0]["callstack"] == "train.py:10"


@pytest.mark.parametrize("name", ["event_frames"])
@pytest.mark.parametrize("slice_index", [None, 0])
def test_dataset_root_never_implicitly_selects_a_shard(tmp_path: Path, name: str, slice_index):
    from pt_snap_cli.core.dataset.dataset_support import DATASET_SUPPORT
    from test.test_dataset_focus import hashes, make_dataset

    root = make_dataset(tmp_path / "dataset")
    before = hashes(root)
    assert name not in DATASET_SUPPORT
    with pytest.raises(QueryExecutionError, match="support|standalone|available"):
        query(root, name, {"event_id": 1}, slice_index=slice_index)
    assert hashes(root) == before
