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

"""Read-only analysis commands preserve the input database and focus state."""

import json
import sqlite3
from contextlib import closing
from pathlib import Path

import pytest
from typer.testing import CliRunner

from pt_snap_cli.cli import app


@pytest.fixture
def example_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.delenv("PT_SNAP_DB_PATH", raising=False)
    path = tmp_path / "snapshot.pkl.db"
    mib = 1048576
    with closing(sqlite3.connect(path)) as conn, conn:
        conn.executescript("""
            CREATE TABLE dictionary (`table` TEXT, `column` TEXT, `key` TEXT, `value` TEXT);
            CREATE TABLE trace_entry_0 (
                id INTEGER PRIMARY KEY, action INTEGER, address INTEGER, size INTEGER,
                stream INTEGER, allocated INTEGER, active INTEGER, reserved INTEGER,
                callstack TEXT
            );
            CREATE TABLE block_0 (
                id INTEGER PRIMARY KEY, address INTEGER, size INTEGER,
                requestedSize INTEGER, state INTEGER, allocEventId INTEGER, freeEventId INTEGER
            );
            """)
        # Allocate 2+6 MiB, request a deferred 2 MiB free, then allocate another
        # 2 MiB. Earliest allocated/reserved peaks differ from the active peak.
        conn.executemany(
            "INSERT INTO trace_entry_0 VALUES (?, ?, ?, ?, 0, ?, ?, ?, ?)",
            [
                (9, 0, 100, 2 * mib, 2 * mib, 2 * mib, 8 * mib, "first"),
                (10, 0, 200, 6 * mib, 8 * mib, 8 * mib, 16 * mib, "second"),
                (11, 1, 100, 2 * mib, 6 * mib, 8 * mib, 16 * mib, "free"),
                (12, 0, 300, 2 * mib, 8 * mib, 10 * mib, 16 * mib, "third"),
            ],
        )
        conn.executemany(
            "INSERT INTO block_0 VALUES (?, ?, ?, ?, ?, ?, -1)",
            [
                (1, 100, 2 * mib, 2 * mib, 0, 9),
                (2, 200, 6 * mib, 6 * mib, 1, 10),
                (3, 300, 2 * mib, 2 * mib, 1, 12),
            ],
        )
    return path


def test_read_only_commands_reach_report(example_db: Path) -> None:
    commands = [
        ["overview", str(example_db), "--json"],
        ["query", str(example_db), "--device", "0", "--template-use", "memory_peak", "--json"],
        ["report", "peak-memory", str(example_db), "--device", "0"],
    ]
    before = example_db.read_bytes()
    results = [CliRunner().invoke(app, command) for command in commands]
    assert len(results) == 3
    assert all(result.exit_code == 0 for result in results), [result.output for result in results]
    overview = json.loads(results[0].stdout)
    assert overview["import_metadata"]["status"] == "unavailable"
    assert overview["import_metadata"]["reason"] == "metadata_missing"
    expected_peak = {
        "peak_allocated": 8388608,
        "peak_allocated_event_id": 10,
        "peak_active": 10485760,
        "peak_active_event_id": 12,
        "peak_reserved": 16777216,
        "peak_reserved_event_id": 10,
    }
    assert json.loads(results[1].stdout)["rows"] == [expected_peak]
    assert "Peak memory report" in results[2].stdout
    assert "Event ID: 12" in results[2].stdout
    assert "Active memory by callstack:" in results[2].stdout
    assert "100.0000%" in results[2].stdout
    assert example_db.read_bytes() == before
    assert not (example_db.parent / ".pt-snap").exists()
