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

"""Issue #160: bounded leak windows replace earlier results, not offset pages."""

import json
import sqlite3
from contextlib import closing
from pathlib import Path

import pytest
from typer.testing import CliRunner

from pt_snap_cli.api import SnapshotAnalyzer
from pt_snap_cli.cli import app
from pt_snap_cli.core import TemplateRenderError

pytestmark = pytest.mark.usefixtures("owned_service_instances")

ROOT = Path(__file__).resolve().parents[1]
runner = CliRunner()
CANDIDATE_COUNT = 325
CANDIDATE_BYTES = sum(1024 * (1 + i % 3) for i in range(1, CANDIDATE_COUNT + 1))


@pytest.fixture
def leak_db(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("PT_SNAP_DB_PATH", raising=False)
    monkeypatch.delenv("PT_SNAP_QUERY_TIMEOUT", raising=False)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    path = tmp_path / "leak-window.db"
    with closing(sqlite3.connect(path)) as conn, conn:
        conn.executescript("""
            CREATE TABLE dictionary (`table` TEXT, `column` TEXT, `key` TEXT, `value` TEXT);
            CREATE TABLE trace_entry_0 (id INTEGER PRIMARY KEY, callstack TEXT);
            CREATE TABLE block_0 (
                id INTEGER PRIMARY KEY, address INTEGER, size INTEGER,
                allocEventId INTEGER, freeEventId INTEGER
            );
            INSERT INTO block_0 VALUES
                (-1, 1, 8192, -1, -1),
                (1000, 2, 8192, 1000, 1001),
                (1002, 3, 512, 1002, -1);
        """)
        conn.executemany(
            "INSERT INTO block_0 VALUES (?, ?, ?, ?, ?)",
            [(i, i * 4096, 1024 * (1 + i % 3), i, None if i % 2 else -1) for i in range(1, CANDIDATE_COUNT + 1)],
        )
    return path


def query_both(path, params, max_rows, exact_total=False):
    """Run the same real SQLite query through CLI JSON and the public API."""
    args = [
        "query",
        str(path),
        "--device",
        "0",
        "--template-use",
        "leak_detection",
        "--params",
        json.dumps(params),
        "-n",
        str(max_rows),
        "--json",
    ]
    if exact_total:
        args.append("--exact-total")
    result = runner.invoke(app, args)
    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    analyzer = SnapshotAnalyzer(db_path=path, device_id=0)
    try:
        api = analyzer.execute_query("leak_detection", params=params, max_rows=max_rows, exact_total=exact_total)
    finally:
        analyzer.invalidate_context_cache()
    for key in ("rows", "total", "returned", "total_is_exact", "has_more", "truncated"):
        assert payload[key] == api[key]
    return payload


@pytest.mark.parametrize("offset", [0, 100])
def test_leak_offset_is_rejected_by_cli_and_api(leak_db, offset):
    params = {"min_size": 1024, "limit": 100, "offset": offset}
    result = runner.invoke(
        app,
        [
            "query",
            str(leak_db),
            "--device",
            "0",
            "--template-use",
            "leak_detection",
            "--params",
            json.dumps(params),
            "--json",
        ],
    )
    assert result.exit_code == 1
    assert result.stdout == ""
    error = json.loads(result.stderr)["error"]
    assert error["code"] == "INVALID_PARAMETER"
    analyzer = SnapshotAnalyzer(db_path=leak_db, device_id=0)
    try:
        with pytest.raises(TemplateRenderError) as exc:
            analyzer.execute_query("leak_detection", params=params)
    finally:
        analyzer.invalidate_context_cache()
    assert error["message"] == str(exc.value)
    assert "Unknown parameter(s) for template 'leak_detection': offset" in str(exc.value)


@pytest.mark.parametrize("synchronize_limit", [False, True])
def test_exact_count_then_replace_window_after_fixing_explicit_limit(leak_db, synchronize_limit):
    params = {"min_size": 1024, "limit": 100}
    initial = query_both(leak_db, params, 100)
    assert initial["total"] == initial["returned"] == 100
    assert initial["total_is_exact"] is False
    assert initial["has_more"] is initial["truncated"] is True

    counted = query_both(leak_db, params, 100, exact_total=True)
    assert counted["total"] == CANDIDATE_COUNT
    assert counted["total_is_exact"] is True
    assert counted["returned"] == 100
    assert counted["rows"] == initial["rows"]

    capped = query_both(leak_db, params, counted["total"])
    assert capped["rows"] == initial["rows"]
    assert capped["has_more"] is capped["truncated"] is True
    assert capped["effective_params"]["limit"] == 100

    if synchronize_limit:
        params["limit"] = counted["total"]
    else:
        del params["limit"]
    complete = query_both(leak_db, params, counted["total"])
    assert complete["returned"] == complete["total"] == counted["total"]
    assert complete["has_more"] is complete["truncated"] is False
    assert complete["rows"][:100] == initial["rows"]  # Overlap, not a next page.
    assert {row["id"] for row in complete["rows"]} == set(range(1, CANDIDATE_COUNT + 1))
    assert sum(row["size"] for row in complete["rows"]) == CANDIDATE_BYTES


def test_empty_count_uses_positive_bounded_window(leak_db):
    empty = query_both(leak_db, {"min_size": 16384}, 100, exact_total=True)
    assert empty["total"] == empty["returned"] == 0
    assert empty["rows"] == []
    assert empty["total_is_exact"] is True
    assert empty["has_more"] is empty["truncated"] is False
    assert empty["effective_params"]["limit"] == 100


def test_exact_count_does_not_make_budget_limited_rows_complete(leak_db):
    sample = query_both(leak_db, {"min_size": 1024}, 20, exact_total=True)
    assert sample["total"] == CANDIDATE_COUNT
    assert sample["returned"] == 20
    assert sample["has_more"] is sample["truncated"] is True
    assert sum(row["size"] for row in sample["rows"]) < CANDIDATE_BYTES
