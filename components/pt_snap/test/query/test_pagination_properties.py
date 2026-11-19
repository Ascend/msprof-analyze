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

"""Bounded properties for the existing standalone event/block page contract.

Every generated example owns its database, focus isolation and service lifetime.
The oracle sorts independent input records, not another query's returned rows.
"""

from __future__ import annotations

import copy
import sqlite3
from collections.abc import Iterator
from contextlib import closing, contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest
from hypothesis import example, given, settings
from hypothesis import strategies as st

from pt_snap_cli.core.analysis.query_service import QueryService
from pt_snap_cli.core.common.query_limits import QueryLimits
from pt_snap_cli.query import registry
from pt_snap_cli.query.config import QueryConfig

# Deterministic for a fixed Hypothesis version; failing examples are shrunk and
# print a reproduction blob. No example database or machine-speed deadline.
PROPERTY_SETTINGS = settings(max_examples=40, derandomize=True, database=None, deadline=None, print_blob=True)
RECORDS = st.lists(
    st.tuples(st.integers(-20, 100), st.integers(0, 4)),
    unique_by=lambda row: row[0],
    max_size=24,
)
LIMITS = st.one_of(st.just(-1), st.integers(0, 30))
ROW_CAPS = st.one_of(st.none(), st.integers(0, 30))


@contextmanager
def _query_database(records: list[tuple[int, int]]) -> Iterator[tuple[QueryService, Path]]:
    with TemporaryDirectory() as directory, pytest.MonkeyPatch.context() as monkeypatch:
        root = Path(directory)
        monkeypatch.chdir(root)
        monkeypatch.setattr(Path, "home", lambda: root)
        monkeypatch.delenv("PT_SNAP_DB_PATH", raising=False)
        monkeypatch.delenv("PT_SNAP_QUERY_TIMEOUT", raising=False)
        # Restore the exact original registry, including other tests' factories.
        # Only load the two actual packaged contracts being exercised here.
        monkeypatch.setattr(registry, "_registry", copy.deepcopy(registry._registry))
        for name in ("event", "block"):
            config = QueryConfig.load_yaml(registry.get_template_dir() / "basic" / f"{name}.yaml")
            registry.register_query(config.queries[name])

        db_path = root / "pages.db"
        with closing(sqlite3.connect(db_path)) as conn, conn:
            conn.execute("CREATE TABLE dictionary (`table` TEXT, `column` TEXT, `key` TEXT, `value` TEXT)")
            conn.execute(
                "CREATE TABLE trace_entry_0 (id INTEGER PRIMARY KEY, action INTEGER, "
                "address INTEGER, size INTEGER, stream INTEGER, allocated INTEGER, "
                "active INTEGER, reserved INTEGER, callstack TEXT)"
            )
            conn.execute(
                "CREATE TABLE block_0 (id INTEGER PRIMARY KEY, address INTEGER, size INTEGER, "
                "requestedSize INTEGER, state INTEGER, allocEventId INTEGER, freeEventId INTEGER)"
            )
            conn.executemany(
                "INSERT INTO trace_entry_0 VALUES (?, 4, 4096, ?, 0, 0, 0, 0, 'frame')",
                records,
            )
            conn.executemany(
                "INSERT INTO block_0 VALUES (?, 4096, ?, ?, 1, ?, -1)",
                [(event_id, size, size, event_id) for event_id, size in records],
            )
        before = db_path.read_bytes()
        with closing(QueryService(query_limits=QueryLimits())) as service:
            yield service, db_path
        assert db_path.read_bytes() == before
        assert not (root / ".pt-snap").exists()


@pytest.mark.parametrize("template", ["event", "block"])
@PROPERTY_SETTINGS
@given(
    records=RECORDS,
    offset=st.integers(0, 30),
    limit=LIMITS,
    max_rows=ROW_CAPS,
    direction=st.sampled_from(["ASC", "DESC"]),
    exact_total=st.booleans(),
)
@example(records=[], offset=0, limit=0, max_rows=None, direction="ASC", exact_total=False)
@example(
    records=[(7, 2), (-3, 2), (5, 2), (11, 0)],
    offset=1,
    limit=3,
    max_rows=1,
    direction="DESC",
    exact_total=True,
)
@example(
    records=[(7, 2), (-3, 2)],
    offset=0,
    limit=0,
    max_rows=3,
    direction="ASC",
    exact_total=True,
)
@example(
    records=[(7, 2), (-3, 2)],
    offset=4,
    limit=-1,
    max_rows=0,
    direction="ASC",
    exact_total=False,
)
def test_generated_pages_match_ordered_slice_and_completeness(
    template: str,
    records: list[tuple[int, int]],
    offset: int,
    limit: int,
    max_rows: int | None,
    direction: str,
    exact_total: bool,
) -> None:
    ordered = sorted(records, key=lambda row: (row[1], row[0]), reverse=direction == "DESC")
    available = ordered[offset:]
    # max_rows=0 disables the output cap; a template limit=0 is an empty page.
    caps = [limit] if limit >= 0 else []
    if max_rows is not None and max_rows > 0:
        caps.append(max_rows)
    cap = min(caps) if caps else len(available)
    expected = available[:cap]
    has_more = len(available) > len(expected)

    with _query_database(records) as (service, db_path):
        result = service.execute_query(
            template,
            db_path=db_path,
            device_id=0,
            params={"order_by": "size", "order_dir": direction, "offset": offset, "limit": limit},
            max_rows=max_rows,
            exact_total=exact_total,
        )

    assert [(row["id"], row["size"]) for row in result.rows] == expected
    assert result.returned == len(expected)
    assert result.has_more is has_more
    assert result.total == (len(records) if exact_total else len(expected))
    assert result.total_is_exact is (exact_total or (not has_more and offset == 0))
    assert result.truncated is (has_more or offset > 0 or (exact_total and len(records) > len(expected)))


@pytest.mark.parametrize("template", ["event", "block"])
@PROPERTY_SETTINGS
@given(
    records=RECORDS,
    page_size=st.integers(1, 12),
    max_rows=st.one_of(st.none(), st.integers(1, 12)),
    direction=st.sampled_from(["ASC", "DESC"]),
)
@example(records=[(5, 3), (1, 3), (8, 3), (2, 1)], page_size=2, max_rows=1, direction="DESC")
@example(records=[], page_size=1, max_rows=None, direction="ASC")
def test_generated_page_concatenation_matches_unlimited_query(
    template: str,
    records: list[tuple[int, int]],
    page_size: int,
    max_rows: int | None,
    direction: str,
) -> None:
    expected = sorted(records, key=lambda row: (row[1], row[0]), reverse=direction == "DESC")
    step = min(page_size, max_rows) if max_rows is not None else page_size
    common = {"order_by": "size", "order_dir": direction}
    with _query_database(records) as (service, db_path):
        whole = service.execute_query(template, params=common, db_path=db_path, device_id=0)
        pages = []
        # Arithmetic bounds, not has_more, control termination. Query the empty
        # trailing page too, so broken completeness cannot hide missing rows.
        for offset in range(0, len(records) + step, step):
            page = service.execute_query(
                template,
                params={**common, "offset": offset, "limit": page_size},
                db_path=db_path,
                device_id=0,
                max_rows=max_rows,
            )
            expected_page = expected[offset : offset + step]
            assert [(row["id"], row["size"]) for row in page.rows] == expected_page
            assert page.has_more is (offset + len(expected_page) < len(expected))
            pages.extend(page.rows)
        assert pages == whole.rows
        assert [(row["id"], row["size"]) for row in whole.rows] == expected
        assert len({row["id"] for row in pages}) == len(records)
        assert whole.total_is_exact is True
        assert whole.has_more is whole.truncated is False
