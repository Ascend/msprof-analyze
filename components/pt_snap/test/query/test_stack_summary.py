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

"""Compact text must not compact evidence or collapse attribution identities."""

from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from dataclasses import asdict
from pathlib import Path

import pytest
from typer.testing import CliRunner

from pt_snap_cli.cli import app
from pt_snap_cli.core.analysis.query_service import QueryService
from pt_snap_cli.core.analysis.report_service import ReportService
from pt_snap_cli.query.registry import QueryRegistry, _load_all_templates

LONG_STACK = '训练.py:12 forward("模型🚀")\n' * 800


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("PT_SNAP_DB_PATH", raising=False)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    QueryRegistry.reset()
    _load_all_templates()
    yield
    QueryRegistry.reset()
    _load_all_templates()


@pytest.fixture(params=["v1", "v2"])
def stack_db(tmp_path, request):
    layout = request.param
    path = tmp_path / f"{layout}.db"
    texts = [LONG_STACK, LONG_STACK, "[missing callstack]", " ", "", None]
    with closing(sqlite3.connect(path)) as conn, conn:
        conn.execute("CREATE TABLE dictionary (`table`, `column`, `key`, `value`)")
        column = "callstack TEXT" if layout == "v1" else "callstackId INTEGER"
        conn.execute(
            "CREATE TABLE trace_entry_0 (id INTEGER PRIMARY KEY, action INTEGER, "
            "address INTEGER, size INTEGER, stream INTEGER, allocated INTEGER, "
            f"active INTEGER, reserved INTEGER, {column})"
        )
        if layout == "v2":
            conn.execute("CREATE TABLE callstack (id INTEGER PRIMARY KEY, callstack TEXT)")
            conn.executemany("INSERT INTO callstack VALUES (?, ?)", enumerate(texts, 1))
        for index, text in enumerate(texts + [None, None], 1):
            # 7: dangling callstack ID; 8: NULL ID; both are missing attribution.
            value = text if layout == "v1" else (index if index < 8 else None)
            conn.execute(
                "INSERT INTO trace_entry_0 VALUES (?, 4, ?, 100, 0, ?, ?, 10000, ?)",
                (index, index * 4096, index * 100, index * 100, value),
            )
        conn.execute(
            "CREATE TABLE block_0 (id INTEGER PRIMARY KEY, address INTEGER, "
            "size INTEGER, requestedSize INTEGER, state INTEGER, "
            "allocEventId INTEGER, freeEventId INTEGER)"
        )
        conn.executemany(
            "INSERT INTO block_0 VALUES (?, ?, ?, ?, 1, ?, ?)",
            [(i, i * 4096, i * 100, i * 90, i, -1) for i in range(1, 10)]
            + [(10, 40960, 1000, 900, -1, -1), (11, 45056, 1100, 990, -1, 1000)],
        )
    return path, layout


@pytest.mark.parametrize("budget", [0, 1, 7, 256])
@pytest.mark.parametrize(
    "template,params",
    [("event", {}), ("active_memory_callstack_at_event", {"event_id": 100, "top_n": -1})],
)
def test_summary_preserves_evidence_and_full_retrieval(stack_db, budget, template, params):
    path, layout = stack_db
    service = QueryService()
    try:
        full = service.execute_query(template, params, db_path=path, device_id=0)
        compact = service.execute_query(template, {**params, "stack_bytes": budget}, db_path=path, device_id=0)
        assert {k: v for k, v in asdict(full).items() if k != "rows"} == {
            k: v for k, v in asdict(compact).items() if k != "rows"
        }
        for original, summary in zip(full.rows, compact.rows, strict=True):
            assert {k: v for k, v in summary.items() if not k.startswith("stack_") and k != "callstack"} == {
                k: v for k, v in original.items() if k != "callstack"
            }
            assert not any(k.startswith("stack_") for k in original)
            text = original["callstack"]
            original_bytes = len(text.encode("utf-8")) if text is not None else 0
            assert summary["stack_original_bytes"] == original_bytes
            assert summary["stack_bytes"] == budget
            assert summary["stack_truncated"] == (original_bytes > budget)
            assert len((summary["callstack"] or "").encode("utf-8")) <= budget
            assert "�" not in (summary["callstack"] or "")
            if summary["stack_kind"] == "captured":
                fetched = service.execute_query(
                    "event", {"id": summary["stack_event_id"]}, db_path=path, device_id=0
                ).rows[0]
                assert fetched["callstack"] == text
                assert summary["stack_id"].startswith(layout + ":")
        assert len(json.dumps(compact.rows).encode()) < len(json.dumps(full.rows).encode()) / 10
    finally:
        service.close()


def test_group_identity_includes_layout_id_and_special_categories(stack_db):
    path, layout = stack_db
    service = QueryService()
    try:
        groups = service.execute_query(
            "active_memory_callstack_at_event",
            {"event_id": 100, "top_n": -1, "stack_bytes": 256},
            db_path=path,
            device_id=0,
        ).rows
        assert len({g["stack_id"] for g in groups}) == len(groups)
        assert {g["stack_kind"] for g in groups} == {
            "captured",
            "missing",
            "static",
            "preexisting_live_at_event",
        }
        long_groups = [g for g in groups if g["stack_original_bytes"] == len(LONG_STACK.encode())]
        assert len(long_groups) == (1 if layout == "v1" else 2)
        if layout == "v2":
            assert {g["stack_id"] for g in long_groups} == {"v2:id:1", "v2:id:2"}
        same_labels = [g for g in groups if g["callstack"] == "[missing callstack]"]
        assert len(same_labels) == 2
        assert {g["stack_kind"] for g in same_labels} == {"captured", "missing"}
        missing = next(g for g in same_labels if g["stack_kind"] == "missing")
        assert missing["block_count"] == 5  # empty, NULL text, dangling/NULL IDs, absent event
        assert missing["stack_event_id"] is None
    finally:
        service.close()


@pytest.mark.parametrize("exact_total", [False, True])
@pytest.mark.parametrize(
    "template,params",
    [
        ("event", {"limit": 3, "offset": 1}),
        ("active_memory_callstack_at_event", {"event_id": 100, "top_n": 2}),
    ],
)
def test_summary_preserves_incomplete_windows(stack_db, exact_total, template, params):
    path, _ = stack_db
    service = QueryService()
    try:
        full = service.execute_query(template, params, db_path=path, max_rows=2, exact_total=exact_total)
        compact = service.execute_query(
            template,
            {**params, "stack_bytes": 0},
            db_path=path,
            max_rows=2,
            exact_total=exact_total,
        )
        assert compact.truncated
        assert {k: v for k, v in asdict(full).items() if k != "rows"} == {
            k: v for k, v in asdict(compact).items() if k != "rows"
        }
    finally:
        service.close()


@pytest.mark.parametrize("metric", ["active", "allocated", "reserved"])
@pytest.mark.parametrize("limit", [1, 20], ids=["capped", "complete"])
@pytest.mark.parametrize("budget", [0, 7])
def test_report_uses_shared_summary_and_exposes_text_markers(stack_db, metric, limit, budget):
    path, _ = stack_db
    service = ReportService()
    try:
        full = asdict(service.peak_memory_report(path, device_id=0, metric=metric, limit=limit))
        compact = asdict(service.peak_memory_report(path, device_id=0, metric=metric, limit=limit, stack_bytes=budget))
        assert {k: v for k, v in compact.items() if k not in {"callstack_groups", "effective_params"}} == {
            k: v for k, v in full.items() if k not in {"callstack_groups", "effective_params"}
        }
        assert compact["effective_params"] == {**full["effective_params"], "stack_bytes": budget}
        assert compact["has_more"] is compact["truncated"] is (limit == 1)
        for original, summary in zip(full["callstack_groups"], compact["callstack_groups"], strict=True):
            assert {k: v for k, v in summary.items() if k != "callstack" and not k.startswith("stack_")} == {
                k: v for k, v in original.items() if k != "callstack"
            }
        args = [
            "report",
            "peak-memory",
            str(path),
            "--device",
            "0",
            "--metric",
            metric,
            "--limit",
            str(limit),
            "--stack-bytes",
            str(budget),
        ]
        result = CliRunner().invoke(app, args + ["--json"])
        assert result.exit_code == 0, result.output
        assert json.loads(result.output) == compact
        text = CliRunner().invoke(app, args)
        assert text.exit_code == 0, text.output
        assert "stack_truncated=True" in text.output
        assert f"stack_bytes={budget}" in text.output
        assert ("partial / possibly incomplete" in text.output) is (limit == 1)
        assert ("Full text: query event" in text.output) is any(
            row["stack_kind"] == "captured" for row in compact["callstack_groups"]
        )
    finally:
        service.close()


def test_332_long_events_reduce_bytes_without_dropping_rows(stack_db):
    path, layout = stack_db
    with closing(sqlite3.connect(path)) as conn, conn:
        conn.executemany(
            "INSERT INTO trace_entry_0 VALUES (?, 0, 0, 4096, 0, 0, 0, 4096, ?)",
            [(i, LONG_STACK if layout == "v1" else 1) for i in range(100, 432)],
        )
    service = QueryService()
    try:
        full = service.execute_query("event", {"action": 0, "limit": 1000}, db_path=path)
        compact = service.execute_query("event", {"action": 0, "limit": 1000, "stack_bytes": 256}, db_path=path)
        full_bytes = len(json.dumps(asdict(full), ensure_ascii=False).encode("utf-8"))
        compact_bytes = len(json.dumps(asdict(compact), ensure_ascii=False).encode("utf-8"))
        assert full.returned == compact.returned == 332
        assert compact.total_is_exact and not compact.truncated and not compact.has_more
        assert compact_bytes < full_bytes / 20
        print(f"{layout}: full={full_bytes} B compact={compact_bytes} B")
    finally:
        service.close()
